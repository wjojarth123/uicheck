import asyncio
import uuid
from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field
import re
from urllib.parse import urljoin, urlparse
import json
import time
import os

import cohere
from playwright.async_api import async_playwright, Page, Browser

# Import the visualizer and interaction handler
from visualizer import ExplorationVisualizer
from interaction_handler import InteractionHandler

# Configuration
COHERE_API_KEY = "iT8fXcDqRdXwy0Xllasp7XtvxCO4SvhCRH6REgum"  # Replace with your actual key
MAX_AGENTS = 20  # Maximum number of concurrent browser agents
MAX_DEPTH = 3  # Maximum exploration depth
BROWSER_HEADLESS = True  # Set to False to see browsers
RESULTS_DIR = "exploration_results"  # Directory to store results
DEBUG = True  # Enable verbose logging
STRICT_DOMAIN = False  # Set to False to allow navigating to different domains/subdomains
TIMEOUT_MS = 30000  # Default timeout for page navigation and element interactions in milliseconds

@dataclass
class ExplorationAgent:
    id: str
    page: Page
    current_url: str
    visited_urls: Set[str] = field(default_factory=set)
    depth: int = 0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

class WebExplorer:
    def __init__(self):
        self.cohere_client = cohere.Client(COHERE_API_KEY)
        self.browser: Optional[Browser] = None
        self.agents: Dict[str, ExplorationAgent] = {}
        self.active_agents_count = 0
        self.domain_whitelist: Optional[str] = None
        self.all_visited_urls: Set[str] = set()
        self.exploration_queue = asyncio.Queue()
        
        # Initialize visualizer
        self.visualizer = ExplorationVisualizer(update_interval=3.0)
        self.visualizer.start()
        
        # Results storage
        os.makedirs(RESULTS_DIR, exist_ok=True)
        self.exploration_log = []
        
    async def initialize(self):
        """Initialize the playwright browser"""
        if DEBUG:
            print("Initializing Playwright browser...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=BROWSER_HEADLESS)
        if DEBUG:
            print(f"Browser initialized: {self.browser}")
    
    async def create_agent(self, url: str, parent_id: Optional[str] = None, depth: int = 0) -> Optional[str]:
        """Create a new exploration agent with its own browser page"""
        if self.active_agents_count >= MAX_AGENTS or depth > MAX_DEPTH:
            if DEBUG:
                print(f"Not creating agent: active={self.active_agents_count}/{MAX_AGENTS}, depth={depth}/{MAX_DEPTH}")
            return None
            
        if not self.browser:
            await self.initialize()
            
        # Create a new page
        page = await self.browser.new_page()
        
        # Set a normal browser viewport
        await page.set_viewport_size({"width": 1280, "height": 800})
        
        # Configure the page for more browser-like behavior
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
        })
        
        agent_id = str(uuid.uuid4())
        
        # Create the agent
        agent = ExplorationAgent(
            id=agent_id,
            page=page,
            current_url=url,
            depth=depth,
            parent_id=parent_id
        )
        
        self.agents[agent_id] = agent
        self.active_agents_count += 1
        
        # Add the agent to the parent's children if applicable
        if parent_id and parent_id in self.agents:
            self.agents[parent_id].children_ids.append(agent_id)
            
        # Add the task to the queue
        await self.exploration_queue.put(agent_id)
        
        # Update visualizer
        self.visualizer.update_agent(agent_id, {
            "url": url,
            "parent_id": parent_id,
            "depth": depth,
            "status": "active"
        })
        
        if DEBUG:
            print(f"Created agent {agent_id[:8]} for URL: {url}, depth: {depth}")
        
        return agent_id
    
    async def close_agent(self, agent_id: str):
        """Close a specific agent"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            await agent.page.close()
            del self.agents[agent_id]
            self.active_agents_count -= 1
            
            # Update visualizer
            self.visualizer.remove_agent(agent_id)
            
            if DEBUG:
                print(f"Closed agent {agent_id[:8]}")
    
    def is_same_domain(self, url: str) -> bool:
        """Check if URL is in the same domain as the whitelist"""
        if not self.domain_whitelist or not STRICT_DOMAIN:
            return True
            
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # For classmate.app, we'll allow any subdomain
        if self.domain_whitelist == "classmate.app":
            return domain == "classmate.app" or domain.endswith(".classmate.app")
            
        return domain == self.domain_whitelist
    
    async def explore_page(self, agent_id: str):
        """Explore a page using Cohere to decide next actions"""
        agent = self.agents[agent_id]
        
        try:
            # Navigate to the URL
            if DEBUG:
                print(f"Agent {agent_id[:8]} navigating to {agent.current_url}")
            
            await agent.page.goto(agent.current_url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            
            # Wait for a bit to let the page fully load
            await asyncio.sleep(2)
            
            # Mark as visited
            agent.visited_urls.add(agent.current_url)
            self.all_visited_urls.add(agent.current_url)
            
            # Log the visit
            self.exploration_log.append({
                "agent_id": agent_id,
                "url": agent.current_url,
                "parent_id": agent.parent_id,
                "depth": agent.depth,
                "timestamp": time.time()
            })
            
            # If this is the first page, set the domain whitelist
            if not self.domain_whitelist:
                parsed_url = urlparse(agent.current_url)
                self.domain_whitelist = parsed_url.netloc
                if DEBUG:
                    print(f"Set domain whitelist to: {self.domain_whitelist}")
            
            # Get the page content
            html_content = await agent.page.content()
            page_title = await agent.page.title()
            
            if DEBUG:
                print(f"Page title: {page_title}")
                print(f"Page content length: {len(html_content)} characters")
            
            # Take a screenshot
            screenshot_path = os.path.join(RESULTS_DIR, f"{agent_id}.png")
            await agent.page.screenshot(path=screenshot_path, full_page=True)
            
            # Save the HTML content for debugging
            html_path = os.path.join(RESULTS_DIR, f"{agent_id}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            # STEP 1: Interact with forms and interactive UI elements
            if DEBUG:
                print("Looking for form elements to interact with...")
            
            # Find form elements like text inputs, checkboxes, etc.
            form_elements = await InteractionHandler.analyze_form_elements(agent.page)
            
            # Let Cohere decide how to interact with them
            if form_elements:
                interactions = await InteractionHandler.interact_with_form_elements(
                    agent.page, form_elements, self.cohere_client
                )
                
                if interactions:
                    # Log the interactions
                    self.exploration_log.append({
                        "agent_id": agent_id,
                        "url": agent.current_url,
                        "form_interactions": interactions,
                        "timestamp": time.time()
                    })
                    
                    # Take another screenshot after form interactions
                    await agent.page.screenshot(
                        path=os.path.join(RESULTS_DIR, f"{agent_id}_after_form.png"), 
                        full_page=True
                    )
            
            # Find and interact with UI patterns like tabs, accordions, etc.
            ui_interactions = await InteractionHandler.find_and_interact_with_ui_patterns(agent.page)
            
            if ui_interactions:
                self.exploration_log.append({
                    "agent_id": agent_id,
                    "url": agent.current_url,
                    "ui_interactions": ui_interactions,
                    "timestamp": time.time()
                })
                
                # Take another screenshot after UI interactions
                await agent.page.screenshot(
                    path=os.path.join(RESULTS_DIR, f"{agent_id}_after_ui.png"), 
                    full_page=True
                )
            
            # STEP 2: Find available navigation links
            # First try to click any buttons or interactive elements with an href
            await self.click_interactive_elements(agent.page)
            
            # Then extract all links from the updated page
            if DEBUG:
                print(f"Extracting links from page...")
                
            links = await agent.page.evaluate("""() => {
                // Get all elements that can be navigation targets
                const elements = Array.from(document.querySelectorAll('a, [role="link"], button, [role="button"], [onclick]'));
                
                return elements.map(el => {
                    // For anchor tags, get href
                    let href = el.href || el.getAttribute('href') || '';
                    
                    // For buttons, check for click handlers or data attributes
                    if (!href && (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button')) {
                        href = el.dataset.href || el.dataset.url || el.dataset.link || '';
                    }
                    
                    // Get visible text
                    const isVisible = el.offsetParent !== null;
                    const rect = el.getBoundingClientRect();
                    const hasSize = rect.width > 0 && rect.height > 0;
                    
                    return {
                        href: href,
                        text: el.textContent.trim(),
                        isVisible: isVisible && hasSize,
                        tagName: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || '',
                        classes: el.className
                    };
                }).filter(link => link.href || link.isVisible); // Keep links with href or visible elements
            }""")
            
            if DEBUG:
                print(f"Found {len(links)} potential navigation elements")
            
            # Filter links to only include same-domain and unvisited
            valid_links = []
            for link in links:
                # Handle empty hrefs for buttons and other interactive elements
                href = link.get('href', '').strip()
                if not href and (link.get('tagName') == 'button' or link.get('role') == 'button'):
                    # For buttons without hrefs, create a synthetic URL for tracking
                    text = link.get('text', '').strip()
                    if text:
                        href = f"{agent.current_url}#button:{text.replace(' ', '_')}"
                
                # Skip elements with no useful href
                if not href:
                    continue
                
                # Make relative URLs absolute
                absolute_url = urljoin(agent.current_url, href)
                
                # Check domain constraints and visited status
                if (self.is_same_domain(absolute_url) and 
                    absolute_url not in self.all_visited_urls and
                    absolute_url not in agent.visited_urls):
                    valid_links.append({
                        'url': absolute_url,
                        'text': link.get('text', ''),
                        'visible': link.get('isVisible', False),
                        'element_type': link.get('tagName', '') + (f"[role={link.get('role', '')}]" if link.get('role') else '')
                    })
            
            if DEBUG:
                print(f"Filtered to {len(valid_links)} valid links for exploration")
                for i, link in enumerate(valid_links[:10]):  # Show first 10 only
                    print(f"  {i+1}. {link['url']} - {link['text']} ({link['element_type']})")
                if len(valid_links) > 10:
                    print(f"  ... and {len(valid_links) - 10} more links")
            
            # Try harder for classmate.app - check for navigation UI elements
            if len(valid_links) == 0 and "classmate.app" in agent.current_url:
                if DEBUG:
                    print("No standard links found. Trying to find interactive elements on classmate.app...")
                synthetic_links = await self.find_classmate_navigation(agent.page)
                valid_links.extend(synthetic_links)
                
                if DEBUG:
                    print(f"Found {len(synthetic_links)} interactive elements on classmate.app")
                    for i, link in enumerate(synthetic_links):
                        print(f"  {i+1}. {link['url']} - {link['text']}")
            
            # If no valid links, close this agent
            if not valid_links:
                if DEBUG:
                    print(f"No valid links found, closing agent {agent_id[:8]}")
                await self.close_agent(agent_id)
                return
            
            # STEP 3: Use Cohere to analyze the page and decide which links to explore
            prompt = f"""
            You are a web exploration agent tasked with discovering interesting content on websites.
            
            Current page: {agent.current_url}
            Page title: {page_title}
            Current exploration depth: {agent.depth}
            
            Here are the available links/elements you could explore:
            {[f"{i+1}. {link['url']} - {link['text']}" for i, link in enumerate(valid_links)]}
            
            Based on the page content and available links, decide:
            1. Which links look most interesting to explore? (Choose up to 3 links)
            2. Should I explore multiple paths or focus on a single path?
            3. Why are these links interesting? (Brief explanation)
            
            Respond in the following JSON format:
            {{
                "reasoning": "Brief explanation of your decision",
                "selected_links": [index numbers of links to explore, e.g. [1, 3, 5]],
                "branch_strategy": "single" or "multiple",
                "interesting_content": "Brief description of what's interesting on this page"
            }}
            
            ONLY respond with valid JSON. No other text.
            """
            
            # Save what we're sending to Cohere
            with open(os.path.join(RESULTS_DIR, f"{agent_id}_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)
            
            # Send to Cohere for analysis
            if DEBUG:
                print(f"Sending prompt to Cohere for analysis...")
                
            response = self.cohere_client.chat(
                message=prompt,
                model="command-r", 
                temperature=0.7
            )
            
            if DEBUG:
                print(f"Received response from Cohere")
            
            # Save the response from Cohere
            with open(os.path.join(RESULTS_DIR, f"{agent_id}_response.txt"), "w", encoding="utf-8") as f:
                f.write(response.text)
            
            # Extract the JSON response
            response_text = response.text
            json_match = re.search(r'({.*})', response_text, re.DOTALL)
            if not json_match:
                # Fallback: just explore the first link
                selected_indices = [1]  # 1-indexed
                branch_strategy = "single"
                reasoning = "Default exploration (no valid JSON found)"
                interesting_content = "Unknown"
                if DEBUG:
                    print(f"Could not parse JSON from response, using default values")
            else:
                try:
                    decision = json.loads(json_match.group(1))
                    selected_indices = decision.get("selected_links", [1])  # Default to first link (1-indexed)
                    branch_strategy = decision.get("branch_strategy", "single")
                    reasoning = decision.get("reasoning", "No reasoning provided")
                    interesting_content = decision.get("interesting_content", "Not specified")
                    if DEBUG:
                        print(f"Decision: selected_indices={selected_indices}, strategy={branch_strategy}")
                        print(f"Reasoning: {reasoning}")
                except Exception as e:
                    # Fallback on error
                    selected_indices = [1]  # 1-indexed
                    branch_strategy = "single"
                    reasoning = f"Error parsing JSON: {str(e)}"
                    interesting_content = "Unknown"
                    if DEBUG:
                        print(f"Error parsing JSON: {e}")
                        print(f"Raw response: {response_text}")
            
            # Log the decision
            self.exploration_log.append({
                "agent_id": agent_id,
                "url": agent.current_url,
                "decision": {
                    "selected_indices": selected_indices,
                    "branch_strategy": branch_strategy,
                    "reasoning": reasoning,
                    "interesting_content": interesting_content
                },
                "timestamp": time.time()
            })
            
            # Convert to 0-indexed
            selected_indices = [i-1 for i in selected_indices if 0 < i <= len(valid_links)]
            if not selected_indices and valid_links:
                selected_indices = [0]
                if DEBUG:
                    print(f"No valid indices selected, defaulting to first link")
            
            # Ensure we don't exceed MAX_DEPTH
            if agent.depth >= MAX_DEPTH:
                if DEBUG:
                    print(f"Max depth reached, closing agent {agent_id[:8]}")
                await self.close_agent(agent_id)
                return
                
            # Handle the branching strategy
            if branch_strategy == "multiple" and len(selected_indices) > 1:
                # First link is handled by current agent
                if selected_indices:
                    first_link = valid_links[selected_indices[0]]['url']
                    agent.current_url = first_link
                    if DEBUG:
                        print(f"Agent {agent_id[:8]} will explore {first_link}")
                    await self.exploration_queue.put(agent_id)
                
                # Create new agents for other links
                for idx in selected_indices[1:]:
                    if idx < len(valid_links):
                        new_url = valid_links[idx]['url']
                        if DEBUG:
                            print(f"Creating new agent for {new_url}")
                        await self.create_agent(new_url, agent_id, agent.depth + 1)
            else:
                # Single path: just update the current agent with the first selected link
                if selected_indices:
                    agent.current_url = valid_links[selected_indices[0]]['url']
                    if DEBUG:
                        print(f"Agent {agent_id[:8]} will explore single path: {agent.current_url}")
                    await self.exploration_queue.put(agent_id)
                else:
                    # No links selected, close this agent
                    if DEBUG:
                        print(f"No links selected, closing agent {agent_id[:8]}")
                    await self.close_agent(agent_id)
        
        except Exception as e:
            print(f"Error exploring {agent.current_url}: {e}")
            # Log the error
            self.exploration_log.append({
                "agent_id": agent_id,
                "url": agent.current_url,
                "error": str(e),
                "timestamp": time.time()
            })
            await self.close_agent(agent_id)
    
    async def click_interactive_elements(self, page: Page):
        """Click on interactive elements to reveal more content"""
        try:
            # Find buttons and interactive elements
            elements = await page.query_selector_all('button, [role="button"], [aria-expanded="false"]')
            
            if DEBUG and elements:
                print(f"Found {len(elements)} interactive elements to click")
            
            # Click each element (with some limits to avoid infinite loops)
            for i, element in enumerate(elements[:5]):  # Limit to first 5 elements
                try:
                    visible = await element.is_visible()
                    if visible:
                        text = await element.text_content()
                        if DEBUG:
                            print(f"Clicking element: {text.strip()}")
                        await element.click(timeout=TIMEOUT_MS)
                        # Wait briefly for content to load
                        await asyncio.sleep(0.5)
                except Exception as e:
                    if DEBUG:
                        print(f"Error clicking element: {e}")
        except Exception as e:
            if DEBUG:
                print(f"Error in click_interactive_elements: {e}")
    
    async def find_classmate_navigation(self, page: Page) -> List[Dict]:
        """Find navigation elements specifically for classmate.app"""
        synthetic_links = []
        
        try:
            # Find all nav elements, menu items, and buttons
            selectors = [
                'nav a', 'nav button', 
                '[role="navigation"] a', '[role="navigation"] button',
                '.sidebar a', '.sidebar button',
                '.menu a', '.menu button',
                'header a', 'header button',
                'button'
            ]
            
            for selector in selectors:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    try:
                        visible = await element.is_visible()
                        if visible:
                            text = await element.text_content()
                            text = text.strip()
                            if text:
                                # Create a synthetic URL for this UI element
                                synthetic_url = f"{page.url}#ui:{text.replace(' ', '_')}"
                                
                                synthetic_links.append({
                                    'url': synthetic_url,
                                    'text': text,
                                    'visible': True,
                                    'element_type': 'synthetic'
                                })
                    except Exception as e:
                        if DEBUG:
                            print(f"Error processing element: {e}")
        except Exception as e:
            if DEBUG:
                print(f"Error in find_classmate_navigation: {e}")
            
        return synthetic_links
    
    async def run(self, start_url: str):
        """Main method to start the exploration"""
        start_time = time.time()
        print(f"Starting exploration at: {start_url}")
        
        # Create the initial agent
        await self.create_agent(start_url)
        
        # Process the queue until it's empty
        while not self.exploration_queue.empty() or self.active_agents_count > 0:
            try:
                # Print status update
                print(f"Active agents: {self.active_agents_count}, Queue size: {self.exploration_queue.qsize()}, URLs visited: {len(self.all_visited_urls)}")
                
                # Get next agent from queue with timeout
                try:
                    agent_id = await asyncio.wait_for(self.exploration_queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    # If all agents are busy but queue is empty, wait
                    if self.active_agents_count > 0:
                        await asyncio.sleep(1)
                    continue
                
                # Skip if agent no longer exists
                if agent_id not in self.agents:
                    continue
                    
                # Process the agent
                await self.explore_page(agent_id)
                
            except Exception as e:
                print(f"Error in main loop: {e}")
        
        # Exploration complete
        end_time = time.time()
        duration = end_time - start_time
        
        # Save results
        self.save_results(start_url, duration)
        
        print(f"Exploration complete. Visited {len(self.all_visited_urls)} unique URLs in {duration:.2f} seconds.")
    
    def save_results(self, start_url: str, duration: float):
        """Save the exploration results"""
        # Save the exploration log
        results = {
            "start_url": start_url,
            "domain": self.domain_whitelist,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": duration,
            "urls_visited": len(self.all_visited_urls),
            "all_urls": list(self.all_visited_urls),
            "exploration_log": self.exploration_log
        }
        
        with open(os.path.join(RESULTS_DIR, "exploration_results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        
        # Save the final visualization
        self.visualizer.save_final_visualization(os.path.join(RESULTS_DIR, "exploration_tree.png"))
    
    async def cleanup(self):
        """Close all browser instances"""
        if self.browser:
            await self.browser.close()
        self.visualizer.stop()

async def main():
    """Main entry point"""
    # Start URL - replace with your target website
    start_url = "https://classmate.app"
    
    # Create Explorer
    explorer = WebExplorer()
    
    try:
        # Run exploration
        await explorer.run(start_url)
    except KeyboardInterrupt:
        print("Exploration stopped by user")
    finally:
        # Clean up resources
        await explorer.cleanup()

if __name__ == "__main__":
    asyncio.run(main())