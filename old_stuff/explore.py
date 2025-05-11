#!/usr/bin/env python3
"""
Web Explorer CLI
---------------
Command-line interface to run the WebExplorer on any website.
"""

import sys
import asyncio
import argparse
from grid import WebExplorer, MAX_AGENTS, MAX_DEPTH, BROWSER_HEADLESS, TIMEOUT_MS

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Explore websites with autonomous AI agents"
    )
    
    parser.add_argument(
        "url", 
        help="Starting URL for exploration (e.g. https://classmate.app)"
    )
    
    parser.add_argument(
        "--max-agents", 
        type=int, 
        default=MAX_AGENTS,
        help=f"Maximum number of concurrent agents (default: {MAX_AGENTS})"
    )
    
    parser.add_argument(
        "--max-depth", 
        type=int, 
        default=MAX_DEPTH,
        help=f"Maximum exploration depth (default: {MAX_DEPTH})"
    )
    
    parser.add_argument(
        "--visible", 
        action="store_true",
        help="Show browser windows (default: hidden)"
    )
    
    parser.add_argument(
        "--headless", 
        action="store_true",
        help="Hide browser windows (runs headless)"
    )
    
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=TIMEOUT_MS,
        help=f"Timeout for page navigation and element interactions in milliseconds (default: {TIMEOUT_MS})"
    )
    
    return parser.parse_args()

async def run_explorer(url, max_agents, max_depth, headless, timeout_ms):
    """Run the WebExplorer with the specified parameters"""
    # Override globals in grid.py
    import grid
    grid.MAX_AGENTS = max_agents
    grid.MAX_DEPTH = max_depth
    grid.BROWSER_HEADLESS = headless
    grid.TIMEOUT_MS = timeout_ms
    
    print(f"Note: Previous exploration results will be deleted")
    
    # Create and run explorer
    explorer = WebExplorer()
    try:
        await explorer.run(url)
    except KeyboardInterrupt:
        print("\nExploration stopped by user. Cleaning up...")
    finally:
        await explorer.cleanup()

def validate_url(url):
    """Validate the URL format"""
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url

def main():
    args = parse_args()
    
    # Validate URL
    url = validate_url(args.url)
    
    # Set up configuration
    max_agents = args.max_agents
    max_depth = args.max_depth
    headless = args.headless
    timeout_ms = args.timeout
    
    print(f"Starting exploration of {url}")
    print(f"Configuration: max_agents={max_agents}, max_depth={max_depth}, headless={headless}, timeout={timeout_ms}ms")
    print(f"Browser visibility: {'Hidden' if headless else 'Visible'}")
    print(f"Note: Previous exploration results will be deleted")
    
    try:
        # Run the explorer
        asyncio.run(run_explorer(url, max_agents, max_depth, headless, timeout_ms))
    except Exception as e:
        print(f"Error: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    # If no arguments are provided, use a default website that's friendly to crawling
    if len(sys.argv) == 1:
        sys.argv.append("https://en.wikipedia.org/wiki/Main_Page")
    
    sys.exit(main()) 