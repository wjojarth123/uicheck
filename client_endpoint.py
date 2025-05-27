#!/usr/bin/env python3

from flask import Flask, jsonify, request
import asyncio
import threading
import uuid
import os
import time
import base64
import networkx as nx
import hashlib
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from bs4 import BeautifulSoup
from color_analysis import get_color_palette, process_page_colors, get_site_color_metrics, reset_color_analysis_globals
from playwright.async_api import async_playwright
from font_processor import get_page_font_score, get_site_font_scores, reset_site_font_accumulators
from neural_score_processor import get_neural_score, initialize_neural_model
from alignment_processor import get_alignment_score

# Initialize Flask app
app = Flask(__name__)

# Load environment variables (for API keys)
load_dotenv()
initialize_neural_model()  # Initialize the neural model once at startup
# Removed OCR instance initialization, as it's now in font_processor.py

# Global variables
global_data = {
    "status": "idle",  # Can be 'idle', 'active', 'error'
    "current_url": "",  # The most recently visited URL
    "latest_screenshot_data": None,  # Base64 encoded image data
    "latest_screenshot_hash": "",  # Hash of the latest URL for frontend access
    "latest_color_palette": {},  # Color palette of the latest screenshot
    "latest_font_groups": {},  # Font size groups of the latest screenshot
    "map": {"nodes": [], "edges": []},
    "sitewide_metrics": {
        "neural": 0,
        "font": 0,
        "color": 0,
        "alignment": 0
    },
    "pages": [],
    "timestamp": time.time(),
    "recipients": []  # List of connection IDs that have received the current data
}
data_lock = threading.Lock()  # Lock for data access
sitemap_graph = nx.DiGraph()  # Initialize graph for the sitemap
browser_lock = threading.Lock()  # Lock for browser access
agent_running = False  # Flag to check if agent is running

async def record_activity(agent_obj):
    """Hook function that captures and records agent activity at each step"""
    global global_data
    print('--- ON_STEP_END HOOK ---')

    active_page = None
    if hasattr(agent_obj, 'browser_session') and agent_obj.browser_session and hasattr(agent_obj.browser_session, 'context') and agent_obj.browser_session.context:
        if agent_obj.browser_session.context.pages:
            active_page = agent_obj.browser_session.context.pages[-1]
    elif hasattr(agent_obj, 'page') and agent_obj.page:
        active_page = agent_obj.page
    elif hasattr(agent_obj, 'browser_context') and agent_obj.browser_context and agent_obj.browser_context.pages:
        active_page = agent_obj.browser_context.pages[-1]

    if not active_page:
        print("No active page found. Skipping this step.")
        return

    # Capture current page state
    website_html = await active_page.content()
    website_screenshot = await active_page.screenshot()
    current_url = active_page.url
    current_processing_timestamp = time.time()

    # Generate a hash of the current URL for a unique and short filename
    url_hash = hashlib.md5(current_url.encode('utf-8')).hexdigest()

    # Save HTML and screenshot
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("html", exist_ok=True)
    screenshot_path = f"screenshots/{url_hash}.png"
    html_path = f"html/{url_hash}.html"

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(website_html)

    # Save screenshot
    await active_page.screenshot(path=screenshot_path)

    # Parse HTML to extract hrefs
    soup = BeautifulSoup(website_html, "html.parser")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]

    # Add nodes and edges to the sitemap graph
    sitemap_graph.add_node(current_url, color="green")
    sitemap_graph.nodes[current_url]['timestamp'] = current_processing_timestamp
    for href in hrefs:
        sitemap_graph.add_node(href, color="yellow")
        sitemap_graph.add_edge(current_url, href)

    # Process page metrics for all 4 metrics
    page_color_data = process_page_colors(screenshot_path)
    page_actual_color_score = page_color_data['page_score']
    palette_info = page_color_data['palette_details']
    # palette_info = get_color_palette(screenshot_path) # This is now handled by process_page_colors
    page_font_score_data = get_page_font_score(screenshot_path) # Ensures accumulators are updated
    page_actual_font_score = page_font_score_data['font_score']
    neural_score = get_neural_score(screenshot_path)
    alignment_score = get_alignment_score(screenshot_path)

    # Process sitewide metrics
    site_color_data = get_site_color_metrics()
    site_font_data = get_site_font_scores() # No longer needs screenshots_dir
    
    # Calculate sitewide neural and alignment scores (average of all pages that have been scored)
    processed_nodes_data = [data for data in sitemap_graph.nodes.values() if 'neural_score' in data]
    
    if processed_nodes_data:
        sitewide_neural = sum(data.get('neural_score', 0) for data in processed_nodes_data) / len(processed_nodes_data)
        sitewide_alignment = sum(data.get('alignment_score', 0) for data in processed_nodes_data) / len(processed_nodes_data)
    else:
        sitewide_neural = 0
        sitewide_alignment = 0
        
    # Store metrics in graph
    sitemap_graph.nodes[current_url].update({
        'color_score': page_actual_color_score,
        'palette': palette_info,
        'font_score': page_actual_font_score,
        'grouped_font_sizes': page_font_score_data.get('grouped_font_sizes', {}),
        'neural_score': neural_score,
        'alignment_score': alignment_score,
        'screenshot_path': screenshot_path,
        'html_path': html_path
    })# Update global data with thread safety
    with data_lock:
        # Read screenshot bytes and encode to base64
        with open(screenshot_path, 'rb') as img_file:
            img_bytes = img_file.read()
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        # Update status and current URL
        global_data["status"] = "active"
        global_data["current_url"] = current_url
        global_data["latest_screenshot_data"] = img_base64
        global_data["latest_screenshot_hash"] = url_hash
        global_data["latest_color_palette"] = palette_info
        global_data["latest_font_groups"] = page_font_score_data.get('grouped_font_sizes', {})
        
        # Update map
        global_data["map"] = serialize_graph()
        
        # Update sitewide metrics
        print(f"Site font data {site_font_data}")
        global_data["sitewide_metrics"] = {
            "neural": sitewide_neural,
            "font": site_font_data.get('site_font_consistency_score', 0) if isinstance(site_font_data, dict) else 0,
            "color": site_color_data.get('site_color_score', 0) if isinstance(site_color_data, dict) else 0,
            "alignment": sitewide_alignment
        }
        
        # Find or update page in pages list
        page_data = {
            "url": current_url,
            "url_hash": url_hash,
            "timestamp": current_processing_timestamp,
            "metrics": {
                "neural": neural_score,
                "font": page_actual_font_score,
                "color": page_actual_color_score,
                "alignment": alignment_score
            }
        }
        
        # Update or add page
        page_found = False
        for i, page in enumerate(global_data["pages"]):
            if page["url"] == current_url:
                global_data["pages"][i] = page_data
                page_found = True
                break
        
        if not page_found:
            global_data["pages"].append(page_data)
        
        # Update timestamp and clear recipients
        global_data["timestamp"] = current_processing_timestamp
        global_data["recipients"] = []
    
    print(f"Updated global data for URL: {current_url}")
    print(f"Page metrics - Neural: {neural_score:.1f}, Font: {page_actual_font_score:.1f}, Color: {page_actual_color_score:.1f}, Alignment: {alignment_score:.1f}")

async def run_agent(task_description):
    """Run the Browser-Use agent with the recording hook"""
    global agent_running
    
    # Reset accumulators at the beginning of a new agent run
    reset_site_font_accumulators()
    reset_color_analysis_globals()

    with browser_lock:
        if agent_running:
            return {"status": "error", "message": "Agent already running"}
        agent_running = True
    
    try:
        async with async_playwright() as playwright:
            # Path to the default Edge browser executable
            edge_path = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"

            # Path to the user profile directory
            user_data_dir = "c:\\Users\\HP\\AppData\\Local\\Microsoft\\Edge\\User Data"

            # Launch Edge with the user's profile
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=edge_path,
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-client-side-phishing-detection',
                    '--disable-hang-monitor',
                    '--disable-ipc-flooding-protection',
                    '--disable-prompt-on-repost',
                    '--disable-sync',
                    '--no-first-run',
                ],
                viewport={'width': 1920, 'height': 1080},
            )

            page = await context.new_page()
            await page.goto("https://everfi.com")
            
            # Initialize the Gemini model
            llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp')


            agent = Agent(
                task=task_description if task_description else "go to everfi.com log in as a student, using my google account 100034323@mvla.net Complete a mental health lesson, and interact with the questions there, as if you were a student. Tools like hovering or scrolling are often useful", 
                llm=llm,
                page=page,
                context=context
            )

            async def agent_step(agent_obj):
                await record_activity(agent_obj)            # Run the agent
            print("Starting Browser-Use agent with Gemini model")
            await agent.run(
                on_step_end=agent_step,
                max_steps=30
            )
            
            # Keep the browser alive for further interactions
            print("Keeping the browser alive for further interactions.")
            await asyncio.sleep(3600)  # Keep the browser alive for 1 hour
    except Exception as e:
        print(f"Error running agent: {e}")
    finally:
        with browser_lock:
            agent_running = False

def serialize_graph():
    """Convert the networkx graph to a serializable format"""
    nodes = [{"id": n, "color": sitemap_graph.nodes[n].get("color", "yellow"), 
              "metrics": {
                  "color": sitemap_graph.nodes[n].get("color_score", 0.0),
                  "font": sitemap_graph.nodes[n].get("font_score", 0.0),
                  "neural": sitemap_graph.nodes[n].get("neural_score", 0.0),
                  "alignment": sitemap_graph.nodes[n].get("alignment_score", 0.0)
              },
              "grouped_font_sizes": sitemap_graph.nodes[n].get("grouped_font_sizes", {}),
              "palette": sitemap_graph.nodes[n].get("palette", {}),
              "timestamp": sitemap_graph.nodes[n].get("timestamp", 0)
             }
             for n in sitemap_graph.nodes()]
    edges = [{"source": u, "target": v} for u, v in sitemap_graph.edges()]
    return {"nodes": nodes, "edges": edges}

# API Endpoints
@app.route('/api/connect', methods=['POST'])
def connect():
    """Initialize connection and start agent with task"""
    data = request.get_json()
    task = data.get('task', '')
    
    # Generate connection ID
    connection_id = str(uuid.uuid4())
    
    # Start the agent in a separate thread if not already running
    with browser_lock:
        if not agent_running:
            agent_thread = threading.Thread(
                target=lambda: asyncio.run(run_agent(task))
            )
            agent_thread.daemon = True
            agent_thread.start()
    
    return jsonify({
        "connection_id": connection_id,
        "status": "connected",
        "message": "Connection established and agent started"
    })

@app.route('/api/data/<connection_id>', methods=['GET'])
def get_data(connection_id):
    """Get data for a specific connection with simplified long polling"""
    global global_data
    
    with data_lock:
        # Check if this connection has already received the current data
        if connection_id in global_data["recipients"]:
            # Connection has current data, wait for new data (up to 60 seconds)
            pass
        else:
            # Connection hasn't received current data, send it immediately
            global_data["recipients"].append(connection_id)
            return jsonify(global_data)
    
    # Wait for new data (up to 60 seconds)
    timeout = 60
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        time.sleep(1)  # Check every second
        
        with data_lock:
            # Check if recipients list was cleared (new data available)
            if connection_id not in global_data["recipients"]:
                global_data["recipients"].append(connection_id)
                return jsonify(global_data)
    
    # Timeout reached, return heartbeat
    return jsonify({"status": "waiting", "timestamp": time.time()})

if __name__ == "__main__":
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, threaded=True)
