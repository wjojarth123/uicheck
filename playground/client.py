#!/usr/bin/env python3

import asyncio
import requests
import os
import networkx as nx
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from pyobjtojson import obj_to_json
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, BrowserSession, BrowserProfile
from bs4 import BeautifulSoup
from color_analysis import get_page_color_score
import hashlib
from playwright.async_api import async_playwright

# Load environment variables (for API keys)
load_dotenv()

# Initialize a directed graph for the sitemap
sitemap_graph = nx.DiGraph()

async def record_activity(agent_obj):
    """Hook function that captures and records agent activity at each step"""
    print('--- ON_STEP_START HOOK ---')

    active_page = None
    if hasattr(agent_obj, 'browser_session') and agent_obj.browser_session and hasattr(agent_obj.browser_session, 'context') and agent_obj.browser_session.context:
        if agent_obj.browser_session.context.pages:
            active_page = agent_obj.browser_session.context.pages[-1]  # Get the last page in the context
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

    # Generate a hash of the current URL for a unique and short filename
    url_hash = hashlib.md5(current_url.encode('utf-8')).hexdigest()

    # Save HTML and screenshot
    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("html", exist_ok=True)
    screenshot_path = f"screenshots/{url_hash}.png"
    html_path = f"html/{url_hash}.html"

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(website_html)

    with open(screenshot_path, "wb") as screenshot_file:
        screenshot_file.write(website_screenshot)

    # Parse HTML to extract hrefs
    soup = BeautifulSoup(website_html, "html.parser")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]

    # Add nodes and edges to the sitemap graph
    sitemap_graph.add_node(current_url, color="green")
    for href in hrefs:
        sitemap_graph.add_node(href, color="yellow")
        sitemap_graph.add_edge(current_url, href)    # Get color score for the page
    color_data = get_page_color_score(screenshot_path)

    # Add the color data to the sitemap graph as node attributes
    sitemap_graph.nodes[current_url]['color_score'] = color_data["color_score"]
    sitemap_graph.nodes[current_url]['color_palette'] = color_data["palette"]

    print(f"Visited: {current_url}")
    print(f"Found hrefs: {hrefs}")
    print(f"Color score in screenshot: {color_data['color_score']:.1f}")

async def run_agent():
    """Run the Browser-Use agent with the recording hook"""
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

        # Prelaunch Playwright on everfi.com


        page = await context.new_page()
        await page.goto("https://everfi.com")
        # Initialize the Gemini model
        llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash-exp')


        agent = Agent(
            task="go to everfi.com log in as a student, using my google account 100034323@mvla.net Complete a mental health lesson, and interact with the questions there, as if you were a student. Tools like hovering or scrolling are often useful", 
            llm=llm,
            page=page
        )

        # Live update the sitemap in a second window
        plt.ion()  # Turn on interactive mode
        fig, ax = plt.subplots()

        def update_sitemap():
            ax.clear()
            colors = [sitemap_graph.nodes[node]['color'] for node in sitemap_graph]
            nx.draw(sitemap_graph, ax=ax, with_labels=True, node_color=colors, font_size=8)
            plt.draw()
            plt.pause(0.1)

        async def agent_step(agent_obj):
            await record_activity(agent_obj)
            update_sitemap()

        # Update the sitemap graph during the agent's execution
        try:
            print("Starting Browser-Use agent with Gemini model")
            await agent.run(
                on_step_start=agent_step,  # Pass the async function directly
                max_steps=30
            )
        except Exception as e:
            print(f"Error running agent: {e}")

        # Ensure the browser remains alive
        print("Keeping the browser alive for further interactions.")
        await asyncio.sleep(3600)  # Keep the browser alive for 1 hour

        plt.ioff()  # Turn off interactive mode

        # Keep the browser alive and visit all indexed hrefs
        visited_urls = set()
        hrefs_to_visit = list(sitemap_graph.nodes)
        total_colors = 0
        total_pages = 0

        while hrefs_to_visit:
            current_url = hrefs_to_visit.pop()
            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            try:
                print(f"Visiting: {current_url}")
                await page.goto(current_url)

                # Count unique colors on the page                screenshot_path = f"screenshots/{hashlib.md5(current_url.encode('utf-8')).hexdigest()}.png"
                await page.screenshot(path=screenshot_path)
                color_data = get_page_color_score(screenshot_path)
                total_colors += color_data["color_score"]
                total_pages += 1

                # Add hrefs from the current page to the list
                website_html = await page.content()
                soup = BeautifulSoup(website_html, "html.parser")
                new_hrefs = [a["href"] for a in soup.find_all("a", href=True) if a["href"] not in visited_urls]
                hrefs_to_visit.extend(new_hrefs)

                print(f"Color score on {current_url}: {color_data['color_score']:.1f}")
            except Exception as e:
                print(f"Error visiting {current_url}: {e}")        # Compute average color score per page
        avg_color_score_per_page = total_colors / total_pages if total_pages > 0 else 0
        print(f"Average color score per page: {avg_color_score_per_page:.1f}")

if __name__ == "__main__":
    # Run the agent
    asyncio.run(run_agent())
