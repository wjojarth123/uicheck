import os
import asyncio
import json
import random
import string
import hashlib
import sys
import traceback
import argparse
from playwright.async_api import async_playwright, TimeoutError, Page
from html_cleaner import clean_html_string
from functools import partial # For event handlers with instance methods

COOKIES_FILE = "cookies.json" # Define cookie file name
GET_XPATH_SCRIPT = """ 
function getXPath(element) {
    if (element && element.id) {
        return '//*[@id="' + element.id + '"]';
    }
    const paths = [];
    while (element && element.nodeType === Node.ELEMENT_NODE) {
        let index = 0;
        let sibling = element.previousSibling;
        while (sibling) {
            if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === element.nodeName) {
                index++;
            }
            sibling = sibling.previousSibling;
        }
        const tagName = element.nodeName.toLowerCase();
        const pathIndex = '[' + (index + 1) + ']';
        paths.unshift(tagName + pathIndex);
        element = element.parentNode;
    }
    return paths.length ? '/' + paths.join('/') : '';
}
window.getXPath = getXPath;
"""

def generate_unique_id(element_type, xpath, text="", class_name="", aria_label=""):
    type_prefix = ""
    if element_type in ["button", "submit"]:
        type_prefix = "bt"
    elif element_type in ["text", "email", "password", "search", "tel", "url", "number", "textarea"]:
        type_prefix = "in"
    elif element_type == "select":
        type_prefix = "sl"
    elif element_type == "link":
        type_prefix = "lk"
    elif element_type == "checkbox":
        type_prefix = "cb"
    elif element_type == "radio":
        type_prefix = "rd"
    else:
        type_prefix = element_type[:2].lower() if len(element_type) >= 2 else (element_type + "x").lower()
    
    middle_part_source = ""
    if text and text.strip():
        middle_part_source = text.strip()
    elif class_name and class_name.strip():
        middle_part_source = class_name.strip().split()[0]
    elif aria_label and aria_label.strip():
        middle_part_source = aria_label.strip()
    
    if middle_part_source:
        middle_part = ''.join(filter(str.isalnum, middle_part_source))[:3]
    else:
        middle_part = ''.join(random.choices(string.ascii_lowercase, k=3))
    
    middle_part = middle_part.lower().ljust(3, 'x')[:3]
    xpath_hash_suffix = hashlib.sha256(xpath.encode()).hexdigest()[:3]
    return f"{type_prefix}{middle_part}{xpath_hash_suffix}"

class HumanBrowser:
    """
    HumanBrowser - A class for interacting with web pages in a human-like manner.
    
    This class provides methods for automating web interactions using Playwright
    while simulating human-like behavior to avoid detection as a bot.
    
    Features:
    - Automatic detection of interactive elements (buttons, links, inputs, etc.)
    - Human-like clicking and typing with randomized delays
    - Modal dialog detection and dismissal
    - Multiple page/tab management
    - Cookie management
    - Command-line interface for interactive control
    - Ability to be imported and used in other Python code
    
    Args:
        start_url (str): Initial URL to navigate to upon launch
        user_data_dir (str, optional): Path to browser user data directory for persistent sessions
        executable_path (str, optional): Path to browser executable
        cookies_file (str, optional): Path to JSON file containing cookies to load
        start_paused (bool, optional): If True, element detection is paused until explicitly started
        headless (bool, optional): If True, browser runs in headless mode
        cli_mode (bool, optional): If True, parses command-line arguments

    Usage examples are provided in the module-level docstring.
    """
    def __init__(self, 
                 start_url="https://www.google.com", 
                 user_data_dir=None, 
                 executable_path=None, 
                 cookies_file=COOKIES_FILE, 
                 start_paused=True, # For library use, default to paused
                 headless=False,
                 cli_mode=False): # New flag to indicate if run from CLI
        self.start_url = start_url
        self.user_data_dir = user_data_dir
        self.executable_path = executable_path
        self.cookies_file_path = cookies_file # Renamed to avoid conflict with global
        self.headless = headless
        self._start_paused_init_val = start_paused # Store initial value before CLI override
        self._cli_mode = cli_mode

        if self._cli_mode:
            self._parse_cli_args() # Will override some of the above if provided via CLI
        else:
            # If not in CLI mode, use provided args or defaults
            self._start_paused = start_paused # Use the value passed to __init__
            self._processing_active = [not self._start_paused]

        self._playwright_instance = None
        self._browser_instance = None # For non-persistent context
        self._context_instance = None
        
        self._pages = []  
        self._page_urls = set() 
        self._active_page_index = 0

        self._visited_urls_for_processing = set() 
        self._page_elements_cache = {}  
        self._processing_active = [not self._start_paused] 

        self._initial_page_loaded_flag = [False] 
        self._playwright_owner = False # True if this instance started playwright

    def _parse_cli_args(self):
        parser = argparse.ArgumentParser(description="Human-like web interaction script with Playwright.")
        parser.add_argument("--start-paused", action="store_true", help="If set, element detection is paused until 'start' command.")
        parser.add_argument("--start-url", default=self.start_url, help="Initial URL.")
        
        # For persistent context:
        default_edge_user_data_win = r"C:\Users\HP\AppData\Local\Microsoft\Edge\User Data"
        default_edge_exe_win = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        
        parser.add_argument("--profile-dir", default=None, 
                            help=f"Path to user data directory for persistent context. If combined with --executable-path, uses persistent. Default for Edge: {default_edge_user_data_win}")
        parser.add_argument("--executable-path", default=None, 
                            help=f"Path to browser executable. If None, Playwright default. Default for Edge: {default_edge_exe_win}")
        
        parser.add_argument("--no-persistent", action="store_true", 
                            help="Launch a fresh browser instance (overrides profile-dir and specific executable for persistence).")
        parser.add_argument("--headless", action="store_true", help="Run headless.")

        cli_args = parser.parse_args()

        # Override instance attributes with CLI arguments if they were provided
        self.start_url = cli_args.start_url
        self.headless = cli_args.headless

        # Determine effective paths for persistence
        effective_user_data_dir = cli_args.profile_dir
        effective_executable_path = cli_args.executable_path

        if not cli_args.no_persistent: # If we want persistence
            if cli_args.profile_dir is None and cli_args.executable_path is None:
                # Default to Edge persistent if no specific paths given and not --no-persistent
                if os.path.exists(default_edge_exe_win) and os.path.exists(default_edge_user_data_win):
                    print("INFO (CLI): Defaulting to persistent Edge profile.")
                    effective_user_data_dir = default_edge_user_data_win
                    effective_executable_path = default_edge_exe_win
                else:
                    print("INFO (CLI): Default Edge profile/exe not found, will use fresh Playwright browser.")
                    effective_user_data_dir = None # Fallback to fresh
                    effective_executable_path = None
            elif cli_args.profile_dir and not cli_args.executable_path:
                # Profile dir given, but no exe, assume it's for default playwright browser if it can manage it
                # or try to find a default exe if it matches common ones
                if cli_args.profile_dir == default_edge_user_data_win and os.path.exists(default_edge_exe_win):
                    print(f"INFO (CLI): Using specified Edge profile dir with default Edge executable.")
                    effective_executable_path = default_edge_exe_win
                else: # Or let Playwright try to use the profile dir with its default chromium
                    print(f"WARN (CLI): Using profile dir '{cli_args.profile_dir}' with Playwright's default Chromium. This might create a new profile within that dir specifically for Playwright's Chromium version if it's not an Edge/Chrome profile dir.")
                    effective_executable_path = None # Let launch_persistent_context use its default browser for the user_data_dir
            elif not cli_args.profile_dir and cli_args.executable_path:
                # Executable given, but no profile dir for persistence. This implies a fresh profile with that exe.
                print(f"INFO (CLI): Using specified executable '{cli_args.executable_path}' with a fresh profile (persistence needs --profile-dir).")
                effective_user_data_dir = None # No persistence
        else: # --no-persistent flag is set
            print("INFO (CLI): --no-persistent flag set. Launching a fresh browser session.")
            effective_user_data_dir = None
            # If --no-persistent, but --executable-path is still given, use that for the fresh launch
            # If not, effective_executable_path remains None (Playwright default)

        # Update instance values with CLI parsed results
        self.user_data_dir = effective_user_data_dir
        self.executable_path = effective_executable_path
        self._start_paused = cli_args.start_paused
        self._processing_active = [not self._start_paused]
        
        print(f"DEBUG (HumanBrowser CLI): Command-line arguments parsed:")
        print(f"  Start URL: {self.start_url}")
        print(f"  User Data Dir: {self.user_data_dir}")
        print(f"  Executable Path: {self.executable_path}")
        print(f"  Headless: {self.headless}")
        print(f"  Start Paused: {self._start_paused}")

    async def _ensure_playwright_started(self):
        if not self._playwright_instance:
            print("DEBUG (HumanBrowser): Starting Playwright...")
            self._playwright_instance = await async_playwright().start()
            self._playwright_owner = True

    async def launch(self):
        """Initializes Playwright, launches browser, creates context, and loads initial page."""
        await self._ensure_playwright_started()
        
        launch_options = {"headless": self.headless}

        if self.user_data_dir and self.executable_path:
            print(f"INFO (HumanBrowser): Launching persistent context.")
            print(f"  User Data Dir: {self.user_data_dir}")
            print(f"  Executable: {self.executable_path}")
            try:
                self._context_instance = await self._playwright_instance.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    executable_path=self.executable_path,
                    **launch_options
                )
            except Exception as e_launch:
                print(f"FATAL ERROR (HumanBrowser): Could not launch persistent context: {e_launch}")
                traceback.print_exc()
                raise 
        elif self.executable_path:
            print(f"INFO (HumanBrowser): Launching browser with executable: {self.executable_path}")
            try:
                self._browser_instance = await self._playwright_instance.chromium.launch(
                    executable_path=self.executable_path, 
                    **launch_options
                )
                self._context_instance = await self._browser_instance.new_context()
            except Exception as e_launch:
                print(f"FATAL ERROR (HumanBrowser): Could not launch browser with executable: {e_launch}")
                traceback.print_exc()
                raise
        else: 
            print("INFO (HumanBrowser): Launching default Playwright browser.")
            try:
                self._browser_instance = await self._playwright_instance.chromium.launch(**launch_options)
                self._context_instance = await self._browser_instance.new_context()
            except Exception as e_launch:
                print(f"FATAL ERROR (HumanBrowser): Could not launch default browser: {e_launch}")
                traceback.print_exc()
                raise

        await self._load_cookies_from_file()
        
        # Set up event handlers for page load and other events
        self._context_instance.on("page", self._handle_new_page)

        initial_page_obj = None
        if self._context_instance.pages:
            initial_page_obj = self._context_instance.pages[0]
            print(f"DEBUG (HumanBrowser): Using existing page from context: {initial_page_obj.url}")
        else:
            initial_page_obj = await self._context_instance.new_page()
            print(f"DEBUG (HumanBrowser): Created new page in context: {initial_page_obj.url}")
        
        if initial_page_obj not in self._pages: self._pages.append(initial_page_obj)
        if initial_page_obj.url and initial_page_obj.url not in self._page_urls and initial_page_obj.url != "about:blank":
             self._page_urls.add(initial_page_obj.url)
        
        try:
            await initial_page_obj.add_init_script(GET_XPATH_SCRIPT)
        except Exception as e_init_script:
             print(f"WARN (HumanBrowser): Failed to add init script to initial page {initial_page_obj.url}: {e_init_script}")

        # Set up page load handler for the initial page
        initial_page_obj.on("load", lambda: asyncio.ensure_future(self.page_load_handler(initial_page_obj)))

        if self.start_url:
            print(f"INFO (HumanBrowser): Navigating initial page to {self.start_url}")
            try:
                await initial_page_obj.goto(self.start_url, wait_until="load")
                if initial_page_obj.url and initial_page_obj.url not in self._page_urls and initial_page_obj.url != "about:blank":
                     self._page_urls.add(initial_page_obj.url)
                print(f"DEBUG (HumanBrowser): Initial page navigated to: {initial_page_obj.url}")
            except Exception as e_goto:
                print(f"ERROR (HumanBrowser): Failed to navigate initial page to {self.start_url}: {e_goto}")
        
        self._initial_page_loaded_flag[0] = True
        self._active_page_index = self._pages.index(initial_page_obj) if initial_page_obj in self._pages else 0

        # Initial processing if not paused
        if self._processing_active[0]:
            print("INFO (HumanBrowser): Auto-starting element processing.")
            await self.process_page_content(initial_page_obj)

        return initial_page_obj 
        
    async def _handle_new_page(self, page):
        """Handle new page events from the context."""
        print(f"DEBUG (HumanBrowser): New page created: {page.url if page.url else 'about:blank'}")
        
        # Add to the page tracking
        if page not in self._pages:
            self._pages.append(page)
            print(f"DEBUG (HumanBrowser): Added new page to tracking list. Total: {len(self._pages)}")
        
        # Set up the page load handler
        page.on("load", lambda: asyncio.ensure_future(self.page_load_handler(page)))
        
        # Add the XPath script
        try:
            await page.add_init_script(GET_XPATH_SCRIPT)
        except Exception as e:
            print(f"WARN (HumanBrowser): Failed to add XPath script to new page: {e}")
    
    async def _load_cookies_from_file(self):
        if self.cookies_file_path and os.path.exists(self.cookies_file_path):
            print(f"INFO (HumanBrowser): Found {self.cookies_file_path}, attempting to load cookies...")
            try:
                with open(self.cookies_file_path, "r") as f:
                    cookies = json.load(f)
                if cookies:
                    await self._context_instance.add_cookies(cookies)
                    print(f"INFO (HumanBrowser): Successfully loaded {len(cookies)} cookies.")
            except Exception as e:
                print(f"ERROR (HumanBrowser): Could not load cookies from {self.cookies_file_path}: {e}")
        else:
            if self.cookies_file_path : print(f"INFO (HumanBrowser): Cookie file '{self.cookies_file_path}' not found.")

    async def close(self):
        print("INFO (HumanBrowser): Closing browser context and playwright connection if owned.")
        if self._context_instance:
            try: await self._context_instance.close()
            except Exception as e: print(f"DEBUG: Error closing context: {e}")
            self._context_instance = None
        if self._browser_instance: # Only if not using persistent context (where context is the browser)
            try: await self._browser_instance.close()
            except Exception as e: print(f"DEBUG: Error closing browser instance: {e}")
            self._browser_instance = None
        if self._playwright_instance and self._playwright_owner:
            try: await self._playwright_instance.stop()
            except Exception as e: print(f"DEBUG: Error stopping playwright: {e}")
            self._playwright_instance = None
        self._pages.clear()
        self._page_urls.clear()
        self._page_elements_cache.clear()
        
    async def detect_and_dismiss_modals(self, page):
        """Attempt to detect and dismiss any modal dialog overlays on the page."""
        print("DEBUG (HumanBrowser): Checking for modal dialogs...")
        modal_detected = False
        
        try:
            # Check for common "No thanks" buttons
            no_thanks_elems = await page.query_selector_all('text=/no,? thanks|i understand|not now|maybe later|dismiss|continue|not interested/i')
            for elem in no_thanks_elems:
                if await elem.is_visible():
                    print(f"INFO (HumanBrowser): Found 'No Thanks' type button, attempting to click...")
                    try:
                        await elem.click()
                        modal_detected = True
                        print("INFO (HumanBrowser): Clicked 'No Thanks' type button")
                        await asyncio.sleep(0.5)  # Brief pause after interaction
                    except Exception as e:
                        print(f"WARN (HumanBrowser): Failed to click 'No Thanks' button: {e}")

            # Check for common close buttons (×, X, Close)
            close_elems = await page.query_selector_all('button:has-text("×"), button:has-text("X"), button:has-text("Close"), [aria-label="Close"], [title="Close"]')
            for elem in close_elems:
                if await elem.is_visible():
                    print(f"INFO (HumanBrowser): Found close button, attempting to click...")
                    try:
                        await elem.click()
                        modal_detected = True
                        print("INFO (HumanBrowser): Clicked close button")
                        await asyncio.sleep(0.5)  # Brief pause after interaction
                    except Exception as e:
                        print(f"WARN (HumanBrowser): Failed to click close button: {e}")
            
            # Look for cookie consent buttons
            cookie_elems = await page.query_selector_all('text=/accept cookies|accept all|agree|consent|got it/i')
            for elem in cookie_elems:
                if await elem.is_visible():
                    print(f"INFO (HumanBrowser): Found cookie consent button, attempting to click...")
                    try:
                        await elem.click()
                        modal_detected = True
                        print("INFO (HumanBrowser): Clicked cookie consent button")
                        await asyncio.sleep(0.5)  # Brief pause after interaction
                    except Exception as e:
                        print(f"WARN (HumanBrowser): Failed to click cookie consent button: {e}")
                        
        except Exception as e:
            print(f"ERROR (HumanBrowser): Error while trying to dismiss modals: {e}")
            
        return modal_detected
        
    async def process_page_content(self, page, force_reprocess=False):
        """Process page content to identify interactive elements."""
        if not page or not page.url or page.url == "about:blank" or not self._processing_active[0]:
            return {}
            
        current_url = page.url
        
        # Skip URLs we've already processed, unless force_reprocess is True
        if current_url in self._visited_urls_for_processing and not force_reprocess:
            print(f"DEBUG (HumanBrowser): URL already processed: {current_url}")
            return self._page_elements_cache.get(current_url, {})
            
        print(f"INFO (HumanBrowser): Processing page content: {current_url}")
        
        try:
            # Check for and dismiss any modal dialogs first
            modal_dismissed = await self.detect_and_dismiss_modals(page)
            if modal_dismissed:
                # If we dismissed something, wait a moment and recheck the page
                await asyncio.sleep(1)
                
            # Wait for the page to stabilize
            await self._wait_for_page_stability(page)
            
            # Dictionary to store elements by ID
            elements_dict = {}
            
            # Process buttons (including submit inputs)
            buttons = await page.query_selector_all('button, input[type="submit"], input[type="button"]')
            for idx, button in enumerate(buttons):
                try:
                    if not await button.is_visible():
                        continue
                        
                    text = await button.text_content() or ""
                    text = text.strip()
                    
                    value_attr = await button.get_attribute("value") or ""
                    if not text and value_attr:
                        text = value_attr
                        
                    type_attr = await button.get_attribute("type") or ""
                    tag_name = await button.evaluate("el => el.tagName.toLowerCase()")
                    
                    # Determine element type
                    element_type = "button"
                    if tag_name == "input" and type_attr == "submit":
                        element_type = "submit"
                        
                    # Get additional attributes
                    class_name = await button.get_attribute("class") or ""
                    aria_label = await button.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await button.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    unique_id = generate_unique_id(element_type, xpath, text, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": element_type,
                        "text": text,
                        "xpath": xpath,
                        "tag_name": tag_name,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND {element_type}: {unique_id} - '{text or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing button element: {elem_err}")
            
            # Process links
            links = await page.query_selector_all('a, [role="link"]')
            for idx, link in enumerate(links):
                try:
                    if not await link.is_visible():
                        continue
                        
                    text = await link.text_content() or ""
                    text = text.strip()
                    
                    href = await link.get_attribute("href") or ""
                    
                    # Get additional attributes
                    class_name = await link.get_attribute("class") or ""
                    aria_label = await link.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await link.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    unique_id = generate_unique_id("link", xpath, text, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": "link",
                        "text": text,
                        "xpath": xpath,
                        "href": href,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND link: {unique_id} - '{text or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing link element: {elem_err}")
            
            # Process input fields
            inputs = await page.query_selector_all('input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea')
            for idx, input_field in enumerate(inputs):
                try:
                    if not await input_field.is_visible():
                        continue
                        
                    type_attr = await input_field.get_attribute("type") or "text"
                    name_attr = await input_field.get_attribute("name") or ""
                    placeholder = await input_field.get_attribute("placeholder") or ""
                    
                    # Get additional attributes
                    class_name = await input_field.get_attribute("class") or ""
                    aria_label = await input_field.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await input_field.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    unique_id = generate_unique_id(type_attr, xpath, placeholder or name_attr, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": type_attr,
                        "name": name_attr,
                        "placeholder": placeholder,
                        "xpath": xpath,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND input: {unique_id} - '{placeholder or name_attr or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing input element: {elem_err}")
            
            # Process select elements
            selects = await page.query_selector_all('select')
            for idx, select in enumerate(selects):
                try:
                    if not await select.is_visible():
                        continue
                        
                    name_attr = await select.get_attribute("name") or ""
                    
                    # Get additional attributes
                    class_name = await select.get_attribute("class") or ""
                    aria_label = await select.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await select.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    unique_id = generate_unique_id("select", xpath, name_attr, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": "select",
                        "name": name_attr,
                        "xpath": xpath,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND select: {unique_id} - '{name_attr or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing select element: {elem_err}")
            
            # Process checkboxes and radio buttons
            check_inputs = await page.query_selector_all('input[type="checkbox"], input[type="radio"]')
            for idx, check in enumerate(check_inputs):
                try:
                    if not await check.is_visible():
                        continue
                        
                    type_attr = await check.get_attribute("type") or ""
                    name_attr = await check.get_attribute("name") or ""
                    
                    # Get additional attributes
                    class_name = await check.get_attribute("class") or ""
                    aria_label = await check.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await check.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    unique_id = generate_unique_id(type_attr, xpath, name_attr, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": type_attr,
                        "name": name_attr,
                        "xpath": xpath,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND {type_attr}: {unique_id} - '{name_attr or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing checkbox/radio element: {elem_err}")
            
            # Process non-standard interactive elements (divs with click handlers, etc.)
            interactive_divs = await page.query_selector_all('div[role="button"], div[role="link"], div[onclick], div[data-identifier]')
            for idx, div in enumerate(interactive_divs):
                try:
                    if not await div.is_visible():
                        continue
                        
                    text = await div.text_content() or ""
                    text = text.strip()
                    
                    role = await div.get_attribute("role") or ""
                    data_id = await div.get_attribute("data-identifier") or ""
                    
                    # Determine element type based on role
                    element_type = "interactive"
                    if role == "button":
                        element_type = "button"
                    elif role == "link":
                        element_type = "link"
                    
                    # Get additional attributes
                    class_name = await div.get_attribute("class") or ""
                    aria_label = await div.get_attribute("aria-label") or ""
                    
                    # Get XPath
                    xpath = await div.evaluate("el => window.getXPath(el)")
                    
                    # Generate unique ID
                    display_text = text or data_id
                    unique_id = generate_unique_id(element_type, xpath, display_text, class_name, aria_label)
                    
                    # Store element in dictionary
                    elements_dict[unique_id] = {
                        "element_type": element_type,
                        "text": text,
                        "role": role,
                        "data_identifier": data_id,
                        "xpath": xpath,
                        "class_name": class_name,
                        "aria_label": aria_label
                    }
                    
                    print(f"FOUND {element_type}: {unique_id} - '{display_text or aria_label}'")
                    
                except Exception as elem_err:
                    print(f"Error processing interactive div: {elem_err}")
            
            # Mark this URL as processed
            self._visited_urls_for_processing.add(current_url)
            
            # Save elements to cache
            self._page_elements_cache[current_url] = elements_dict
            
            # Save HTML content and elements data to files (optional)
            # await self._save_page_data(page, current_url, elements_dict)
            
            print(f"INFO (HumanBrowser): Processed {len(elements_dict)} elements on page: {current_url}")
            return elements_dict
            
        except Exception as e:
            print(f"ERROR (HumanBrowser): Error processing page content: {e}")
            traceback.print_exc()
            return {}
            
    async def _wait_for_page_stability(self, page, timeout=10):
        """Wait for page to stabilize by monitoring HTML content."""
        print(f"DEBUG (HumanBrowser): Waiting for page stability...")
        
        try:
            last_html = None
            stable_start_time = None
            
            async def check_html_stability():
                nonlocal last_html, stable_start_time
                
                current_html = await page.content()
                
                if last_html == current_html:
                    if stable_start_time is None:
                        # First time we see stable HTML, start the timer
                        stable_start_time = asyncio.get_event_loop().time()
                        return False
                    else:
                        # HTML remained stable for 2 seconds
                        if asyncio.get_event_loop().time() - stable_start_time >= 2:
                            return True
                        return False
                else:
                    # HTML changed, reset stability timer
                    last_html = current_html
                    stable_start_time = None
                    return False
            
            # Poll until page is stable
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                stable = await check_html_stability()
                if stable:
                    print(f"DEBUG (HumanBrowser): Page stable after {asyncio.get_event_loop().time() - start_time:.1f} seconds")
                    return True
                await asyncio.sleep(0.5)
                
            print(f"WARN (HumanBrowser): Page stability timeout after {timeout} seconds")
            return False
            
        except Exception as e:
            print(f"ERROR (HumanBrowser): Error while waiting for page stability: {e}")
            return False
            
    async def handle_interaction(self, command, elements_dict=None):
        """Handle user interaction commands."""
        if not self._pages or self._active_page_index >= len(self._pages):
            print("ERROR (HumanBrowser): No active page available for interaction")
            return False
            
        active_page = self._pages[self._active_page_index]
        current_url = active_page.url
        
        # If elements_dict not provided, try to get from cache
        if elements_dict is None:
            elements_dict = self._page_elements_cache.get(current_url, {})
            if not elements_dict and self._processing_active[0]:
                # Process the page to get elements if processing is active
                elements_dict = await self.process_page_content(active_page)
                
        # Basic command parsing
        command = command.strip()
        cmd_parts = []
        
        # Handle quoted text in TYPE command (e.g., TYPE id "text with spaces")
        if command.upper().startswith("TYPE ") and '"' in command:
            # Extract element_id and quoted text
            match = command.split(maxsplit=1)[1].strip()
            if ' "' in match:
                element_id, quoted_part = match.split(' "', 1)
                if quoted_part.endswith('"'):
                    text = quoted_part[:-1]  # Remove trailing quote
                    cmd_parts = ["TYPE", element_id.strip(), text]
        
        # If not handling a quoted TYPE command, parse normally
        if not cmd_parts:
            cmd_parts = command.split(maxsplit=2)  # Split into action, target, and optional params
        
        if not cmd_parts:
            return False
            
        action = cmd_parts[0].upper()
        
        if action == "CLICK" and len(cmd_parts) >= 2:
            element_id = cmd_parts[1]
            if element_id not in elements_dict:
                print(f"ERROR (HumanBrowser): Element '{element_id}' not found on page.")
                return False
                
            element_info = elements_dict[element_id]
            xpath = element_info.get("xpath")
            
            if not xpath:
                print(f"ERROR (HumanBrowser): No XPath for element '{element_id}'.")
                return False
                
            print(f"INFO (HumanBrowser): Clicking element '{element_id}' ({element_info.get('text', 'no text')}) with XPath: {xpath}")
            
            try:
                # Try multiple strategies to click, in order of most to least reliable
                element = await active_page.query_selector(f"xpath={xpath}")
                if not element:
                    print(f"WARN (HumanBrowser): Could not find element with XPath: {xpath}")
                    return False
                    
                # Strategy 1: Hover then click (most natural)
                try:
                    await element.hover()
                    await asyncio.sleep(0.1)  # Brief pause after hover
                    await element.click()
                    print(f"INFO (HumanBrowser): Successfully clicked element '{element_id}' using hover+click.")
                    return True
                except Exception as e1:
                    print(f"WARN (HumanBrowser): Hover+click failed: {e1}")
                    
                # Strategy 2: Direct JavaScript click
                try:
                    await element.evaluate("el => el.click()")
                    print(f"INFO (HumanBrowser): Successfully clicked element '{element_id}' using JavaScript.")
                    return True
                except Exception as e2:
                    print(f"WARN (HumanBrowser): JavaScript click failed: {e2}")
                    
                # Strategy 3: Click with position
                try:
                    box = await element.bounding_box()
                    if box:
                        center_x = box['x'] + box['width'] / 2
                        center_y = box['y'] + box['height'] / 2
                        await active_page.mouse.click(center_x, center_y)
                        print(f"INFO (HumanBrowser): Successfully clicked element '{element_id}' using position.")
                        return True
                except Exception as e3:
                    print(f"WARN (HumanBrowser): Position click failed: {e3}")
                    
                # Strategy 4: Force click
                try:
                    await element.click(force=True)
                    print(f"INFO (HumanBrowser): Successfully clicked element '{element_id}' using force click.")
                    return True
                except Exception as e4:
                    print(f"ERROR (HumanBrowser): All click strategies failed for element '{element_id}'.")
                    raise Exception(f"Failed to click element '{element_id}': {e4}")
                    
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error clicking element '{element_id}': {e}")
                return False
                
        elif action == "TYPE" and len(cmd_parts) >= 3:
            element_id = cmd_parts[1]
            text = cmd_parts[2]
            
            if element_id not in elements_dict:
                print(f"ERROR (HumanBrowser): Element '{element_id}' not found on page.")
                return False
                
            element_info = elements_dict[element_id]
            xpath = element_info.get("xpath")
            
            if not xpath:
                print(f"ERROR (HumanBrowser): No XPath for element '{element_id}'.")
                return False
                
            print(f"INFO (HumanBrowser): Typing '{text}' into element '{element_id}' with XPath: {xpath}")
            
            try:
                # Find the element using XPath
                element = await active_page.query_selector(f"xpath={xpath}")
                if not element:
                    print(f"WARN (HumanBrowser): Could not find element with XPath: {xpath}")
                    return False
                
                # First, click the element to focus it
                await element.click()
                
                # Clear existing text (select all and delete)
                await active_page.keyboard.press("Control+A")
                await active_page.keyboard.press("Backspace")
                
                # Type text with human-like delays between keystrokes
                for char in text:
                    # Random delay between 50-200ms
                    delay = random.uniform(0.05, 0.2)
                    await active_page.keyboard.type(char)
                    await asyncio.sleep(delay)
                
                print(f"INFO (HumanBrowser): Successfully typed '{text}' into element '{element_id}'.")
                return True
                
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error typing into element '{element_id}': {e}")
                return False
                
        elif action == "HOVER" and len(cmd_parts) >= 2:
            element_id = cmd_parts[1]
            
            if element_id not in elements_dict:
                print(f"ERROR (HumanBrowser): Element '{element_id}' not found on page.")
                return False
                
            element_info = elements_dict[element_id]
            xpath = element_info.get("xpath")
            
            if not xpath:
                print(f"ERROR (HumanBrowser): No XPath for element '{element_id}'.")
                return False
                
            print(f"INFO (HumanBrowser): Hovering over element '{element_id}' with XPath: {xpath}")
            
            try:
                # Find the element using XPath
                element = await active_page.query_selector(f"xpath={xpath}")
                if not element:
                    print(f"WARN (HumanBrowser): Could not find element with XPath: {xpath}")
                    return False
                
                # Hover over the element
                await element.hover()
                
                print(f"INFO (HumanBrowser): Successfully hovered over element '{element_id}'.")
                return True
                
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error hovering over element '{element_id}': {e}")
                return False
                
        elif action == "BACKBTN":
            print(f"INFO (HumanBrowser): Clicking browser back button")
            
            try:
                await active_page.go_back()
                
                print(f"INFO (HumanBrowser): Successfully navigated back to: {active_page.url}")
                
                # Reprocess the page we navigated back to
                if self._processing_active[0]:
                    await self.process_page_content(active_page, force_reprocess=True)
                    
                return True
                
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error navigating back: {e}")
                return False
                
        elif action == "DISMISS":
            try:
                dismissed = await self.detect_and_dismiss_modals(active_page)
                if dismissed:
                    print("INFO (HumanBrowser): Successfully dismissed modal dialog(s).")
                else:
                    print("INFO (HumanBrowser): No modal dialogs detected.")
                return dismissed
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error dismissing modals: {e}")
                return False
                
        else:
            print(f"ERROR (HumanBrowser): Unknown command or invalid format: {command}")
            return False
        
    async def page_load_handler(self, page):
        """Handle events when a page loads."""
        if not page or not page.url or page.url == "about:blank":
            return
            
        current_url = page.url
        print(f"DEBUG (HumanBrowser): Page load detected: {current_url}")
        
        # Add page to tracking if not already there
        if page not in self._pages:
            self._pages.append(page)
            print(f"DEBUG (HumanBrowser): Added new page to tracking: {current_url}")
            
        # Update URL tracking
        if current_url and current_url not in self._page_urls and current_url != "about:blank":
            self._page_urls.add(current_url)
            
        # Add XPath script to the page
        try:
            await page.add_init_script(GET_XPATH_SCRIPT)
        except Exception as e:
            print(f"WARN (HumanBrowser): Failed to add XPath script to page: {e}")
            
        # Process the page if automatic processing is enabled
        if self._processing_active[0] and self._initial_page_loaded_flag[0]:
            try:
                await self.process_page_content(page)
            except Exception as e:
                print(f"ERROR (HumanBrowser): Error during automatic page processing: {e}")
                
    async def display_page_elements(self, page=None, brief=False):
        """Display interactive elements on the current page."""
        if page is None:
            page = await self.get_current_page()
            if not page:
                print("No active page available.")
                return False
        
        elements = await self.get_elements(page)
        if not elements:
            print("No interactive elements found on this page.")
            return False
            
        print(f"\nINTERACTIVE ELEMENTS ON PAGE: {page.url}")
        print("=" * 80)
        
        # Group elements by type
        grouped = {}
        for elem_id, elem_info in elements.items():
            elem_type = elem_info.get("element_type", "unknown")
            if elem_type not in grouped:
                grouped[elem_type] = []
            grouped[elem_type].append((elem_id, elem_info))
            
        # Show elements by type
        for elem_type, elems in grouped.items():
            print(f"\n{elem_type.upper()} elements:")
            print("-" * 40)
            
            for elem_id, elem_info in elems:
                # Determine display text based on element type
                if elem_type in ["button", "submit", "link"]:
                    display_text = elem_info.get("text", "")
                elif elem_type in ["text", "email", "password", "search", "tel", "url", "number", "textarea"]:
                    display_text = elem_info.get("placeholder", "") or elem_info.get("name", "")
                elif elem_type in ["select", "checkbox", "radio"]:
                    display_text = elem_info.get("name", "")
                else:
                    display_text = elem_info.get("text", "") or elem_info.get("aria_label", "")
                    
                aria = f" (aria: {elem_info.get('aria_label')})" if elem_info.get('aria_label') and not brief else ""
                
                # For brief display, show fewer details
                if brief:
                    print(f"  {elem_id}: {display_text or '[no text]'}")
                else:
                    print(f"  {elem_id}: {display_text or '[no text]'}{aria}")
                    if elem_type == "link" and elem_info.get("href"):
                        print(f"      href: {elem_info.get('href')}")
                        
        print("\nTo interact with elements:")
        print("  CLICK <id>      - Click on element")
        print("  TYPE <id> text  - Type text into element")
        print("  HOVER <id>      - Hover over element")
        print("=" * 80)
        return True

    async def run_interactive_shell(self):
        """Run the interactive command shell for browser control."""
        print("INFO (HumanBrowser): Starting interactive shell. Type 'help' for commands, 'exit' to quit.")
        
        active_page = self._pages[self._active_page_index] if self._pages else None
        if not active_page:
            print("ERROR: No active page available.")
            return
            
        # Show elements from the initial page if processing is active
        if self._processing_active[0]:
            await self.display_page_elements()
            
        while True:
            try:
                cmd = input(f"HumanBrowser [{self._active_page_index}] > ")
                cmd = cmd.strip()
                
                if not cmd:
                    continue
                    
                if cmd.lower() == 'exit':
                    print("Exiting interactive shell...")
                    break
                    
                if cmd.lower() == 'help':
                    print("Available commands:")
                    print("  exit         - Exit the interactive shell")
                    print("  help         - Show this help message")
                    print("  list         - List open pages")
                    print("  switch N     - Switch to page number N")
                    print("  goto URL     - Navigate to URL")
                    print("  start        - Start element processing")
                    print("  stop         - Stop element processing")
                    print("  elements     - Show interactive elements on current page")
                    print("  CLICK id     - Click on element with id")
                    print("  TYPE id text - Type text into element with id")
                    print("  HOVER id     - Hover over element with id")
                    print("  BACKBTN      - Click browser back button")
                    print("  DISMISS      - Try to dismiss any modal dialogs")
                    continue
                    
                if cmd.lower() == 'list':
                    print("Open pages:")
                    for i, page in enumerate(self._pages):
                        active_marker = "* " if i == self._active_page_index else "  "
                        print(f"{active_marker}[{i}] {page.url}")
                    continue
                    
                if cmd.lower() == 'elements':
                    await self.display_page_elements()
                    continue
                    
                if cmd.lower().startswith('switch '):
                    try:
                        page_num = int(cmd.split(' ')[1])
                        if 0 <= page_num < len(self._pages):
                            self._active_page_index = page_num
                            active_page = self._pages[self._active_page_index]
                            print(f"Switched to page {page_num}: {active_page.url}")
                            # Display elements for the page we switched to
                            if self._processing_active[0]:
                                await self.display_page_elements()
                        else:
                            print(f"Invalid page number. Use 'list' to see available pages.")
                    except (ValueError, IndexError):
                        print("Invalid switch command. Format: switch NUMBER")
                    continue
                    
                if cmd.lower().startswith('goto '):
                    url = cmd[5:].strip()
                    if url:
                        # Add protocol if missing
                        if not url.startswith(('http://', 'https://')):
                            url = f"https://{url}"
                            
                        print(f"Navigating to: {url}")
                        try:
                            await active_page.goto(url, wait_until="load")
                            print(f"Navigation complete: {active_page.url}")
                            # Process the page after navigation if enabled
                            if self._processing_active[0]:
                                await self.process_page_content(active_page)
                                # Display elements after successful navigation
                                await self.display_page_elements()
                        except Exception as e:
                            print(f"Navigation error: {e}")
                    continue
                    
                if cmd.lower() == 'start':
                    await self.start_element_processing()
                    # Display elements after starting processing
                    await self.display_page_elements()
                    continue
                    
                if cmd.lower() == 'stop':
                    await self.stop_element_processing()
                    continue
                
                # For other commands, try to handle as an interaction
                result = await self.handle_interaction(cmd)
                if result:
                    # After successful interaction, wait a moment for any page changes or new content
                    await asyncio.sleep(1.5)
                    # If processing is active, re-process the page and display elements
                    if self._processing_active[0]:
                        active_page = self._pages[self._active_page_index]
                        await self.process_page_content(active_page, force_reprocess=True)
                        await self.display_page_elements(brief=True)
                else:
                    print(f"Command '{cmd}' was not processed successfully.")
                
            except KeyboardInterrupt:
                print("\nKeyboard interrupt received. Exiting interactive shell...")
                break
            except Exception as e:
                print(f"Error in interactive shell: {e}")
                traceback.print_exc()
                
        return

    async def start_element_processing(self):
        """Start automatic element processing on page loads."""
        if self._processing_active[0]:
            print("INFO (HumanBrowser): Element processing is already active.")
            return
            
        self._processing_active[0] = True
        print("INFO (HumanBrowser): Element processing started.")
        
        # Process the current page if there is one
        if self._pages and len(self._pages) > self._active_page_index:
            active_page = self._pages[self._active_page_index]
            await self.process_page_content(active_page)
            
    async def stop_element_processing(self):
        """Stop automatic element processing on page loads."""
        if not self._processing_active[0]:
            print("INFO (HumanBrowser): Element processing is already inactive.")
            return
            
        self._processing_active[0] = False
        print("INFO (HumanBrowser): Element processing stopped.")
        
    async def get_current_page(self):
        """Get the current active page."""
        if not self._pages or self._active_page_index >= len(self._pages):
            return None
        return self._pages[self._active_page_index]
        
    async def get_elements(self, page=None, force_reprocess=False):
        """Get all detected elements for the given page or current page if None."""
        if page is None:
            page = await self.get_current_page()
            if not page:
                return {}
                
        current_url = page.url
        
        # If we need to process the page or haven't done so yet
        if (current_url not in self._page_elements_cache or 
            force_reprocess or 
            not self._page_elements_cache.get(current_url, {})):
            
            await self.process_page_content(page, force_reprocess=force_reprocess)
            
        return self._page_elements_cache.get(current_url, {})

# --- Main script execution ---
if __name__ == "__main__":
    async def main():
        # Create a HumanBrowser instance in CLI mode
        browser = HumanBrowser(cli_mode=True)
        
        try:
            # Launch the browser
            await browser.launch()
            
            # Run the interactive shell
            await browser.run_interactive_shell()
            
        except Exception as e:
            print(f"ERROR in main execution: {e}")
            traceback.print_exc()
        finally:
            # Ensure the browser is closed on exit
            await browser.close()
    
    # Run the async main function
    asyncio.run(main())

# Global functions that safely use the class implementation for backward compatibility
# These are provided so older code that imports these functions can still work
# by forwarding calls to a singleton HumanBrowser instance.

_global_human_browser_instance = None

async def _get_global_instance():
    """Lazy-initialize and return a global HumanBrowser instance for compatibility functions."""
    global _global_human_browser_instance
    if _global_human_browser_instance is None:
        print("WARN: Using global HumanBrowser instance created by compatibility function. Consider directly using HumanBrowser class instead.")
        _global_human_browser_instance = HumanBrowser()
        await _global_human_browser_instance.launch()
    return _global_human_browser_instance

async def detect_and_dismiss_modals(page):
    """Compatibility function that forwards to HumanBrowser.detect_and_dismiss_modals."""
    instance = await _get_global_instance()
    return await instance.detect_and_dismiss_modals(page)

async def process_page_content(page, visited_urls=None, force_reprocess=False):
    """Compatibility function that forwards to HumanBrowser.process_page_content."""
    instance = await _get_global_instance()
    # The visited_urls param is ignored since the instance maintains its own state
    return await instance.process_page_content(page, force_reprocess=force_reprocess)

async def handle_interaction(page, command, elements_dict=None):
    """Compatibility function that forwards to HumanBrowser.handle_interaction."""
    instance = await _get_global_instance()
    # Set the active page to the one provided
    if page not in instance._pages:
        instance._pages.append(page)
    instance._active_page_index = instance._pages.index(page)
    return await instance.handle_interaction(command, elements_dict)

# More documentation for users of the class

"""
HumanBrowser - A class for interacting with web pages in a human-like manner.

This class provides methods for automating web interactions using Playwright
while simulating human-like behavior to avoid detection as a bot.

Basic Usage:
-----------
```python
import asyncio
from human import HumanBrowser

async def run_example():
    # Create a HumanBrowser instance
    browser = HumanBrowser(
        start_url="https://example.com",
        start_paused=False  # Start with automatic element detection enabled
    )
    
    try:
        # Launch the browser
        await browser.launch()
        
        # Get the active page
        page = browser._pages[browser._active_page_index]
        
        # Process the page to detect interactive elements
        elements = await browser.process_page_content(page)
        
        # Print detected elements
        for element_id, element_info in elements.items():
            print(f"{element_id}: {element_info.get('element_type')} - {element_info.get('text', '')}")
        
        # Interact with elements
        await browser.handle_interaction("CLICK some_element_id")
        await browser.handle_interaction('TYPE input_id "Some text to type"')
        
    finally:
        # Always close the browser when done
        await browser.close()

# Run the example
asyncio.run(run_example())
```

Command-Line Usage:
-----------------
When run as a script, HumanBrowser provides an interactive shell for commanding
the browser. Available commands include:

- exit         - Exit the interactive shell
- help         - Show help message
- list         - List open pages
- switch N     - Switch to page number N
- goto URL     - Navigate to URL
- start        - Start element processing
- stop         - Stop element processing
- CLICK id     - Click on element with id
- TYPE id text - Type text into element with id
- HOVER id     - Hover over element with id
- BACKBTN      - Click browser back button
- DISMISS      - Try to dismiss any modal dialogs

To run in CLI mode:
```
python human.py [options]
```

Command-line options:
--start-paused        If set, element detection is paused until 'start' command
--start-url URL       Initial URL (default: https://www.google.com)
--profile-dir DIR     Path to user data directory for persistent context
--executable-path EXE Path to browser executable
--no-persistent       Launch a fresh browser instance
--headless            Run headless
"""

