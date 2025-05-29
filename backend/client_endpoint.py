#!/usr/bin/env python3
"""
Full replacement for client_endpoint.py – original functionality +:
- click logging & heat metric
- heat-map PNG
- systematic crawl of unvisited pages after agent task completes
"""

# ─────────────────────────────────────  Imports
from flask import Flask, jsonify, request
from flask_cors import CORS # ADDED: Import CORS
import asyncio, threading, uuid, os, time, base64, hashlib, io, json
import networkx as nx
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import numpy as np
import matplotlib
matplotlib.use("Agg")                    # headless rendering
import matplotlib.pyplot as plt
from types import SimpleNamespace
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import gaussian_filter   

# local helpers
from color_analysis import (process_page_colors, get_site_color_metrics,
                            reset_color_analysis_globals)
from font_processor import (get_page_font_score, get_site_font_scores,
                            reset_site_font_accumulators)
from neural_score_processor import get_neural_score, initialize_neural_model
from alignment_processor import get_alignment_score

# ─────────────────────────────────────  Flask
app = Flask(__name__)
CORS(app) # ADDED: Enable CORS for the entire app, or be more specific below
load_dotenv()
initialize_neural_model()               # Gemma once at start

# ─────────────────────────────────────  Globals & Locks
global_data = {
    "status": "idle",
    "current_url": "",
    "latest_screenshot_data": None,
    "latest_screenshot_hash": "",
    "latest_color_palette": {},
    "latest_font_groups": {},
    "map": {"nodes": [], "edges": []},
    "sitewide_metrics": {
        "neural": 0, "font": 0, "color": 0, "alignment": 0,
        "click_heat": 0.0                    # NEW
    },
    "pages": [],                            # each gets click_positions list
    "heatmap_image": "",                    # NEW
    "timestamp": time.time(),
    "recipients": []
}
data_lock        = threading.Lock()
browser_lock     = threading.Lock()
sitemap_graph    = nx.DiGraph()
agent_running    = False
click_heat_sum   = 0.0
click_count      = 0

# Global click tracking system
global_click_buffer = []                    # [{url, x, y, ts, processed}, ...]
global_click_lock = threading.Lock()
last_processed_url = ""

# ─────────────────────────────────────  Maths helpers
from math import exp
def click_heat(u: float, v: float) -> float:
    """Diffusion-style heat: hot at centre AND edges."""
    r       = ((u - .5)**2 + (v - .5)**2) ** .5
    d_edge  = min(u, v, 1-u, 1-v)
    return 10 * max(exp(-(r / .35)**2),
                    exp(-(d_edge / .12)**2))


CLICK_CMAP = LinearSegmentedColormap.from_list(
    "click_heat",
    ["#0046ff", "#1aff4a", "#ffef00", "#ff0011"],   # B  G   Y   R
)

def render_heatmap(grid: int = 256, sigma: float = 60) -> str:
    """
    Return a base-64 PNG of the accumulated clicks.

    grid   – resolution (NxN); higher = sharper image but a bit larger payload
    sigma  – Gaussian blur radius in *pixels* of that grid
    """
    # 1) density matrix --------------------------------------------------
    H = np.zeros((grid, grid), dtype=float)

    for page in global_data["pages"]:
        for c in page.get("click_positions", []):
            i = int(c["y_norm"] * (grid - 1))
            j = int(c["x_norm"] * (grid - 1))
            if 0 <= i < grid and 0 <= j < grid:
                H[i, j] += 1                      # add 1 hit at that cell

    if not H.any():               # no clicks yet
        return ""

    # 2) smooth into blobs ----------------------------------------------
    H = gaussian_filter(H, sigma=sigma, mode="nearest")

    # 3) normalise 0…1 for colour map -----------------------------------
    H /= H.max()

    # 4) draw ------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(3, 3), dpi=100)
    ax.imshow(H, cmap=CLICK_CMAP, origin="lower", interpolation="bilinear")
    ax.axis("off")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
# ─────────────────────────  helper to locate Playwright Page
async def _resolve_active_page(agent_obj):  # MODIFIED: Made async
    """Return the best-guess playwright.page or None, preferring focused and ready pages."""

    async def check_focus_and_ready(p_to_check):
        if p_to_check and hasattr(p_to_check, 'is_closed') and not p_to_check.is_closed():
            try:
                if hasattr(p_to_check, 'evaluate') and callable(p_to_check.evaluate):
                    # Check if the page has focus and is ready
                    has_focus = await p_to_check.evaluate("document.hasFocus()")
                    ready_state = await p_to_check.evaluate("document.readyState")
                    if has_focus and ready_state in ["complete", "interactive"]:
                        return True
            except Exception:
                pass
        return False

    # 1) explicit .page we passed to Agent
    # This is often the most reliable, check it first for focus.
    explicit_agent_page = getattr(agent_obj, "page", None)
    if await check_focus_and_ready(explicit_agent_page): # No need to check explicit_agent_page itself, check_focus does
        return explicit_agent_page

    # 2) browser_session wrappers (API changed a few times)
    bs = getattr(agent_obj, "browser_session", None)
    if bs:
        # Check direct attributes like "page" or "current_page"
        for attr_name in ("page", "current_page"):
            p = getattr(bs, attr_name, None)
            if await check_focus_and_ready(p):
                return p
        
        bs_pages_list = getattr(bs, "pages", [])
        if bs_pages_list:
            for p_item in reversed(bs_pages_list): # Check most recent first
                if await check_focus_and_ready(p_item):
                    return p_item

    # 3) bare playwright context
    ctx = getattr(agent_obj, "browser_context", None)
    if ctx:
        ctx_pages_list = getattr(ctx, "pages", [])
        if ctx_pages_list:
            for p_item in reversed(ctx_pages_list): # Check most recent first
                if await check_focus_and_ready(p_item):
                    return p_item

    # ---- Fallback to original-style logic if no focused page found ----
    # (Return the first available, non-closed page in a reasonable order of preference)

    if explicit_agent_page and hasattr(explicit_agent_page, 'is_closed') and not explicit_agent_page.is_closed():
        return explicit_agent_page

    if bs:
        for attr_name in ("page", "current_page"):
            p = getattr(bs, attr_name, None)
            if p and hasattr(p, 'is_closed') and not p.is_closed():
                return p
        bs_pages_list = getattr(bs, "pages", [])
        if bs_pages_list and len(bs_pages_list) > 0:
            last_page_in_bs = bs_pages_list[-1]
            if last_page_in_bs and hasattr(last_page_in_bs, 'is_closed') and not last_page_in_bs.is_closed():
                return last_page_in_bs

    if ctx:
        ctx_pages_list = getattr(ctx, "pages", [])
        if ctx_pages_list and len(ctx_pages_list) > 0:
            last_page_in_ctx = ctx_pages_list[-1]
            if last_page_in_ctx and hasattr(last_page_in_ctx, 'is_closed') and not last_page_in_ctx.is_closed():
                return last_page_in_ctx
            
    return None # Nothing suitable found
# ─────────────────────────────────────  Page recorder
async def record_activity(agent_obj):
    """Runs after EVERY step (and from crawler) – updates global_data."""
    global click_heat_sum, click_count, last_processed_url

    # ---- resolve active Playwright page (robust) -----------------------
    pg = await _resolve_active_page(agent_obj) # MODIFIED: Added await
    if pg is None:
        print("record_activity: cannot resolve page – skipping step.")
        return
    
    current_url = pg.url
    
    # ---- Process unassigned clicks from previous page -------------------
    unassigned_clicks = []
    with global_click_lock:
        for click in global_click_buffer:
            if not click.get("processed", False):
                # If this click happened before current URL change, assign to previous page
                if last_processed_url and click["url"] == last_processed_url:
                    unassigned_clicks.append(click)
                    click["processed"] = True
    
    # Apply unassigned clicks to the previous page in global_data
    if unassigned_clicks and last_processed_url:
        with data_lock:
            for page_entry in global_data["pages"]:
                if page_entry["url"] == last_processed_url:
                    for click in unassigned_clicks:
                        # Convert to our format and add heat calculation
                        vw, vh = 1920, 1080  # Default viewport size
                        u, v = click["x"]/vw, click["y"]/vh
                        h = click_heat(u, v)
                        click_record = {
                            "x": int(click["x"]), "y": int(click["y"]), 
                            "ts": click["ts"]/1000.0, "heat": round(h,4),
                            "x_norm": u, "y_norm": v
                        }
                        page_entry.setdefault("click_positions", []).append(click_record)
                        click_heat_sum += h
                        click_count += 1
                    break
        print(f"Applied {len(unassigned_clicks)} unassigned clicks to {last_processed_url}")
      # ---- click harvesting from global buffer (current page) -------------
    current_page_clicks = []
    with global_click_lock:
        for click in global_click_buffer:
            if not click.get("processed", False) and click["url"] == current_url:
                current_page_clicks.append(click)
                click["processed"] = True

    vwvh = pg.viewport_size or {"width": 1, "height": 1}   # property, no ()
    vw   = vwvh.get("width", 1)
    vh   = vwvh.get("height", 1)

    click_records = []
    for click in current_page_clicks:
        x, y, ts = click["x"], click["y"], click["ts"]
        print(f"Click at ({x}, {y}) on {current_url} @ {ts}")
        u, v = x/vw, y/vh
        h    = click_heat(u, v)
        click_records.append({"x":int(x),"y":int(y),"ts":ts/1000.0,
                              "heat":round(h,4),"x_norm":u,"y_norm":v})
        click_heat_sum += h
        click_count    += 1
    if click_count:
        site_avg = round((click_heat_sum / click_count), 4)
    else:
        site_avg = 0.0
        print("No clicks recorded yet, site avg heat = 0.0")

    # ---- capture DOM / screenshot / metrics ---------------------------
    html      = await pg.content()
    screenshot_bytes = await pg.screenshot()
    url       = current_url
    t_now     = time.time()
    url_hash  = hashlib.md5(url.encode()).hexdigest()

    # Persist files
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("html",        exist_ok=True)
    ss_path   = f"screenshots/{url_hash}.png"
    html_path = f"html/{url_hash}.html"
    with open(html_path, "w", encoding="utf-8") as f: f.write(html)
    with open(ss_path,  "wb")                      as f: f.write(screenshot_bytes)

    # Build/expand graph
    soup  = BeautifulSoup(html, "html.parser")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    sitemap_graph.add_node(url, color="green", timestamp=t_now)
    for h in hrefs:
        sitemap_graph.add_node(h, color="yellow")
        sitemap_graph.add_edge(url, h)

    # Metrics
    page_color       = process_page_colors(ss_path)
    font_score_data  = get_page_font_score(ss_path)
    neural_score     = get_neural_score(ss_path)
    alignment_score  = get_alignment_score(ss_path)

    # Store metrics on node
    sitemap_graph.nodes[url].update({
        "color_score": page_color["page_score"],
        "palette": page_color["palette_details"],
        "font_score": font_score_data["font_score"],
        "grouped_font_sizes": font_score_data["grouped_font_sizes"],
        "neural_score": neural_score,
        "alignment_score": alignment_score,
        "screenshot_path": ss_path,
        "html_path": html_path,
        "visited": True
    })

    # ---- SITE-WIDE aggregates -----------------------------------------
    site_color = get_site_color_metrics()
    site_font  = get_site_font_scores()
    visited_nodes = [d for d in sitemap_graph.nodes.values() if d.get("visited")]
    if visited_nodes:
        site_neural    = sum(n["neural_score"]    for n in visited_nodes)/len(visited_nodes)
        site_alignment = sum(n["alignment_score"] for n in visited_nodes)/len(visited_nodes)
    else:
        site_neural = site_alignment = 0

    # ---- Assemble per-page dict ---------------------------------------
    page_dict = {
        "url": url,
        "url_hash": url_hash,
        "timestamp": t_now,
        "metrics": {
            "neural": neural_score,
            "font":   font_score_data["font_score"],
            "color":  page_color["page_score"],
            "alignment": alignment_score
        },
        "click_positions": click_records          # NEW / may be empty
    }

    # ---- Thread-safe global update ------------------------------------
    with data_lock:
        # latest snapshot
        global_data.update({
            "status": "active",
            "current_url": url,
            "latest_screenshot_data": base64.b64encode(screenshot_bytes).decode(),
            "latest_screenshot_hash": url_hash,
            "latest_color_palette": page_color["palette_details"],
            "latest_font_groups":   font_score_data["grouped_font_sizes"],
            "map": serialize_graph(),
            "timestamp": t_now
        })

        # sitewide metrics
        global_data["sitewide_metrics"] = {
            "neural":    site_neural,
            "font":      site_font.get("site_font_consistency_score",0),
            "color":     site_color.get("site_color_score",0),
            "alignment": site_alignment,
            "click_heat": site_avg                       # NEW
        }

        # update / append page entry
        found = False
        for i, p in enumerate(global_data["pages"]):
            if p["url"] == url:
                # merge new clicks
                p.setdefault("click_positions", []).extend(click_records)
                p.update(page_dict)      # refresh metrics / timestamp
                global_data["pages"][i] = p
                found = True
                break
        if not found:
            page_dict.setdefault("click_positions", []).extend(click_records)
            global_data["pages"].append(page_dict)

        # heat-map PNG
        global_data["heatmap_image"] = render_heatmap()

        # clear recipients (trigger push)
        global_data["recipients"] = []

    # Update last processed URL for next iteration
    last_processed_url = current_url

    print(f"Recorded {url}")
    if click_records:
        print(f"  +{len(click_records)} new clicks, site avg heat={site_avg:.3f}")

# ─────────────────────────────────────  Post-task crawler
async def crawl_unvisited(context, page):
    """Visit every yellow node (unvisited) newest → oldest, scoring each."""
    while True:
        unvisited = [ (d["timestamp"], n)
                      for n, d in sitemap_graph.nodes(data=True)
                      if not d.get("visited") ]
        if not unvisited:
            break
        # newest first
        unvisited.sort(reverse=True)
        _, url = unvisited[0]
        try:
            await page.goto(url, timeout=45000)
            dummy = SimpleNamespace(page=page, browser_context=context)
            await record_activity(dummy)
        except Exception as e:
            print(f"Could not crawl {url}: {e}")
            sitemap_graph.nodes[url]["visited"] = True   # mark so we don’t loop

# ─────────────────────────────────────  Agent runner
async def run_agent(task_description: str):
    global agent_running
    reset_site_font_accumulators()
    reset_color_analysis_globals()

    with browser_lock:
        if agent_running:
            return
        agent_running = True

    try:
        async with async_playwright() as pw:
            edge_exe  = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            user_prof = r"C:\Users\HP\AppData\Local\Microsoft\Edge\User Data"

            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=user_prof,
                executable_path=edge_exe,
                headless=False,
                viewport={'width': 1920, 'height': 1080},
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-sync','--no-first-run'
                ]
            )            # ---- click listener for EVERY page / navigation  ---------------------
            await ctx.add_init_script("""
                window._globalClickCapture = function(e) {
                    const clickData = {
                        x: e.clientX,
                        y: e.clientY,
                        ts: Date.now(),
                        url: window.location.href,
                        processed: false
                    };
                    
                    // Use synchronous XMLHttpRequest to ensure click is captured before navigation
                    try {
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', 'http://localhost:5000/api/internal/click', false); // false = synchronous
                        xhr.setRequestHeader('Content-Type', 'application/json');
                        xhr.send(JSON.stringify(clickData));
                        console.log('UICHECK: Click captured synchronously');
                    } catch (error) {
                        console.error('UICHECK Click Sync Error:', error);
                        
                        // Fallback: try sendBeacon (best effort for page unload)
                        try {
                            if (navigator.sendBeacon) {
                                const formData = new FormData();
                                formData.append('data', JSON.stringify(clickData));
                                navigator.sendBeacon('http://localhost:5000/api/internal/click', formData);
                                console.log('UICHECK: Click sent via beacon');
                            }
                        } catch (beaconError) {
                            console.error('UICHECK Beacon Error:', beaconError);
                        }
                    }
                };
                document.addEventListener('click', window._globalClickCapture, true);
                
                // Also capture clicks on page unload as backup
                window.addEventListener('beforeunload', function() {
                    console.log('UICHECK: Page unloading');
                });
            """)

            pg = await ctx.new_page()

            await pg.goto("https://everfi.com")

            llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")
            agent = Agent(
                task=(task_description or
                      "go to everfi.com log in as a student …"),
                llm=llm,
                page=pg,
                context=ctx
            )

            async def step_hook(agent_obj):
                """Delay before running record_activity."""
                await asyncio.sleep(2)  # Introduce a 1-second delay
                await record_activity(agent_obj)

            print("Running agent task…")
            await agent.run(on_step_start=step_hook, max_steps=30)

            print("Agent finished. Crawling remaining pages…")
            await crawl_unvisited(ctx, pg)

            print("Crawl done – keeping browser alive 1 h.")
            await asyncio.sleep(3600)

    except Exception as e:
        print("Agent error:", e)
    finally:
        with browser_lock:
            agent_running = False

# ─────────────────────────────────────  Graph serialiser
def serialize_graph():
    nodes = [{
        "id": n,
        "color": d.get("color","yellow"),
        "metrics": {
            "color": d.get("color_score",0),
            "font":  d.get("font_score",0),
            "neural":d.get("neural_score",0),
            "alignment":d.get("alignment_score",0)
        },
        "grouped_font_sizes": d.get("grouped_font_sizes",{}),
        "palette": d.get("palette",{}),
        "timestamp": d.get("timestamp",0)
    } for n,d in sitemap_graph.nodes(data=True)]
    edges = [{"source":u,"target":v} for u,v in sitemap_graph.edges()]
    return {"nodes":nodes,"edges":edges}

# ─────────────────────────────────────  API
@app.route("/api/internal/click", methods=["POST", "OPTIONS"]) # ADDED: OPTIONS method
# @cross_origin() # MOVED: More general CORS(app) above is often simpler for development
def internal_click_handler():
    """Internal endpoint to receive clicks from browser JavaScript."""
    global global_click_buffer, global_click_lock

    if request.method == "OPTIONS":
        # Preflight request. Reply successfully:
        response = jsonify({"status": "ok"})
        # flask_cors should handle the necessary headers, 
        # but you could add them manually here if needed:
        # response.headers.add("Access-Control-Allow-Origin", "*")
        # response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        # response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
        return response    
    if request.method == "POST":
        try:
            # Handle both regular JSON and FormData from sendBeacon
            if request.content_type and 'application/json' in request.content_type:
                click_data = request.get_json(force=True)
            else:
                # Handle FormData from navigator.sendBeacon
                form_data = request.form.get('data')
                if form_data:
                    import json
                    click_data = json.loads(form_data)
                else:
                    # Try to get JSON data anyway
                    click_data = request.get_json(force=True)
            
            print(f"Received click: {click_data['x']}, {click_data['y']} on {click_data['url']}")
            
            # Ensure the lock is appropriate for the context (threading.Lock for Flask)
            with global_click_lock: # Assuming global_click_lock is a threading.Lock
                global_click_buffer.append(click_data)
            return jsonify({"status": "ok"})
        except Exception as e:
            print(f"Error handling POST click: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    # Should not happen with methods=["POST", "OPTIONS"]
    return jsonify({"status": "error", "message": "Method not allowed"}), 405

@app.route("/api/connect", methods=["POST"])
def connect():
    data = request.get_json(force=True)
    task = data.get("task","")
    conn_id = str(uuid.uuid4())

    # spin up agent if not running
    with browser_lock:
        if not agent_running:
            threading.Thread(
                target=lambda: asyncio.run(run_agent(task)),
                daemon=True
            ).start()

    return jsonify({"connection_id":conn_id,"status":"connected"})

@app.route("/api/data/<connection_id>", methods=["GET"])
def get_data(connection_id):
    with data_lock:
        if connection_id not in global_data["recipients"]:
            global_data["recipients"].append(connection_id)
            return jsonify(global_data)

    # simple long-poll loop (≤60 s)
    start = time.time()
    while time.time() - start < 60:
        time.sleep(1)
        with data_lock:
            if connection_id not in global_data["recipients"]:
                global_data["recipients"].append(connection_id)
                return jsonify(global_data)
    return jsonify({"status":"waiting","timestamp":time.time()})

# ─────────────────────────────────────  Main
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
