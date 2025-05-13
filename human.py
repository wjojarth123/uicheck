import os
import asyncio
import json
import random
import string
import hashlib
import sys
from playwright.async_api import async_playwright, TimeoutError
from html_cleaner import clean_html_string

# --- Helper function for generating unique IDs ---
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

# --- Helper function to detect and dismiss modals ---
async def detect_and_dismiss_modals(page):
    """
    Detect if there are any modal/popup dialogs visible on the page and try to dismiss them.
    Returns True if a modal was detected and dismissed, False otherwise.
    """
    print("Checking for modal popups...")
    
    # Common modal/popup selectors
    modal_selectors = [
        ".modal:visible", 
        "[role='dialog']:visible", 
        ".popup:visible", 
        ".overlay:visible",
        ".dialog:visible",
        "[aria-modal='true']",
        ".modal-container:visible",
        "#popup-container:visible"
    ]
    
    # Common close button selectors
    close_button_selectors = [
        ".modal-close", 
        ".close-button", 
        "button.close", 
        ".dismiss", 
        ".modal button[aria-label='Close']",
        "[data-dismiss='modal']",
        ".modal .close",
        ".popup .close",
        "button.dismiss",
        ".btn-close",
        ".modal-header .close",
        ".modal-dialog .close",
        "[aria-label='Close']:visible",
        "button:has(svg[aria-label='Close'])"
    ]
    
    # Check if any modals are visible
    modal_detected = False
    
    for selector in modal_selectors:
        try:
            modal = await page.query_selector(selector)
            if modal:
                modal_detected = True
                print(f"Modal detected with selector: {selector}")
                break
        except Exception:
            continue
    
    if not modal_detected:
        # Look for elements that might indicate a modal (by checking visibility and z-index)
        try:
            overlays = await page.evaluate("""
                () => {
                    const potentialOverlays = Array.from(document.querySelectorAll('div'))
                        .filter(el => {
                            const style = window.getComputedStyle(el);
                            const zIndex = parseInt(style.zIndex, 10);
                            const isVisible = style.display !== 'none' && 
                                            style.visibility !== 'hidden' && 
                                            style.opacity !== '0';
                            const isLarge = el.offsetWidth > window.innerWidth * 0.5 || 
                                          el.offsetHeight > window.innerHeight * 0.5;
                            return isVisible && zIndex > 100 && isLarge;
                        })
                        .map(el => {
                            const xpath = document.evaluate("", el, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                            return { xpath: window.getXPath(el) };
                        });
                    return potentialOverlays;
                }
            """)
            
            if overlays and len(overlays) > 0:
                modal_detected = True
                print(f"Detected {len(overlays)} potential modal overlay elements by z-index and size")
        except Exception as e:
            print(f"Error detecting overlays by z-index: {e}")
    
    if not modal_detected:
        return False
    
    # Try various methods to dismiss the modal
    modal_dismissed = False
    
    # Method 1: Click close buttons
    for close_selector in close_button_selectors:
        try:
            # Try to find close button with normal selector
            close_button = await page.query_selector(close_selector)
            if close_button:
                print(f"Found close button with selector: {close_selector}")
                await close_button.click(force=True)
                await asyncio.sleep(0.5)
                
                # Check if modal is still present
                modal_still_present = False
                for selector in modal_selectors:
                    try:
                        if await page.query_selector(selector):
                            modal_still_present = True
                            break
                    except:
                        continue
                
                if not modal_still_present:
                    print("Modal dismissed successfully")
                    modal_dismissed = True
                    break
        except Exception as e:
            print(f"Error trying to click close button with selector {close_selector}: {e}")
    
    # Method 2: Press ESC key
    if not modal_dismissed:
        try:
            print("Trying to dismiss modal with ESC key")
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            
            # Check if modal is still present
            modal_still_present = False
            for selector in modal_selectors:
                try:
                    if await page.query_selector(selector):
                        modal_still_present = True
                        break
                except:
                    continue
            
            if not modal_still_present:
                print("Modal dismissed successfully with ESC key")
                modal_dismissed = True
        except Exception as e:
            print(f"Error trying to dismiss with ESC key: {e}")
    
    # Method 3: Click outside the modal (on backdrop)
    if not modal_dismissed:
        backdrop_selectors = [".modal-backdrop", ".overlay-backdrop", ".fade"]
        for backdrop_selector in backdrop_selectors:
            try:
                backdrop = await page.query_selector(backdrop_selector)
                if backdrop:
                    print(f"Found backdrop with selector: {backdrop_selector}")
                    await backdrop.click(force=True, position={"x": 10, "y": 10})  # Click in the corner
                    await asyncio.sleep(0.5)
                    
                    # Check if modal is still present
                    modal_still_present = False
                    for selector in modal_selectors:
                        try:
                            if await page.query_selector(selector):
                                modal_still_present = True
                                break
                        except:
                            continue
                    
                    if not modal_still_present:
                        print("Modal dismissed successfully by clicking backdrop")
                        modal_dismissed = True
                        break
            except Exception as e:
                print(f"Error trying to click backdrop: {e}")
    
    return modal_dismissed

# --- Function to interact with the page based on commands ---
async def handle_interaction(page, command, elements_dict):
    """
    Handle interaction commands: BACKBTN, CLICK <unique_id>, TYPE <unique_id> <text>, HOVER <unique_id>, DISMISS
    Returns True if the action might have caused a navigation
    """
    cmd_parts = command.strip().split()
    if not cmd_parts:
        print("Empty command")
        return False
    
    # Convert all unique IDs in the elements_dict to lowercase for case-insensitive matching
    elements_dict_lower = {}
    for unique_id, element_data in elements_dict.items():
        elements_dict_lower[unique_id.lower()] = element_data
    
    
    # Automatically check for and dismiss modals/popups before any interaction
    if "DISMISS" in command:
        print("Checking for modal popups before interaction...")
        modal_dismissed = await detect_and_dismiss_modals(page)
        if modal_dismissed:
            print("Successfully dismissed modal/popup before interaction")
        else:
            print("No modal/popup detected before interaction")
    
    # Handle DISMISS command to close modals/popups
    if "BACKBTN" in command:
        print("Going back in browser history")
        try:
            await page.go_back()
            return True  # Navigation happens
        except Exception as e:
            print(f"Error going back: {e}")
            return False
    
    elif "CLICK" in command and len(cmd_parts) >= 2:
        target_id = cmd_parts[-1].lower()
        if target_id in elements_dict_lower:
            element_data = elements_dict_lower[target_id]
            xpath = element_data.get('xpath')
            element_type = element_data.get('type')
            href = element_data.get('href', '')  # Get href if it exists
            print(f"Clicking element: {target_id} (XPath: {xpath})")
            
            try:
                # Use xpath for more reliable targeting with a 5-second timeout
                selector_visible = await page.wait_for_selector(f"xpath={xpath}", timeout=5000, state="visible")
                if not selector_visible:
                    raise TimeoutError("Element not visible after 5 seconds")
                
                # Special handling for different types of elements
                if element_type in ["checkbox", "radio"]:
                    await page.check(f"xpath={xpath}", timeout=5000)
                else:
                    print(f"Clicking element: {target_id} (XPath: {xpath})")
                    
                    # Strategy 1: Try JavaScript click first
                    try:
                        print("Trying JavaScript click...")
                        await page.evaluate(f"""
                            (xpath) => {{
                                const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                if (element) {{
                                    element.click();
                                    return true;
                                }}
                                return false;
                            }}
                        """, xpath)
                    except Exception as js_error:
                        print(f"JavaScript click failed: {js_error}")
                        
                        # Strategy 2: Try force click
                        try:
                            print("Trying force click...")
                            await page.click(f"xpath={xpath}", force=True, timeout=5000)
                        except Exception as force_error:
                            print(f"Force click failed: {force_error}")
                            
                            # Strategy 3: Check for intercepting element and click it instead
                            try:
                                print("Checking for intercepting element...")
                                intercepting_element = await page.evaluate(f"""
                                    (xpath) => {{
                                        const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                        if (!element) return null;
                                        
                                        // Get element position
                                        const rect = element.getBoundingClientRect();
                                        const centerX = rect.left + rect.width / 2;
                                        const centerY = rect.top + rect.height / 2;
                                        
                                        // Check what element is actually at that point
                                        const elementAtPoint = document.elementFromPoint(centerX, centerY);
                                        
                                        if (elementAtPoint && elementAtPoint !== element) {{
                                            // We found an intercepting element
                                            return {{
                                                intercepts: true,
                                                tag: elementAtPoint.tagName.toLowerCase(),
                                                href: elementAtPoint.href || "",
                                                xpath: window.getXPath(elementAtPoint)
                                            }};
                                        }}
                                        
                                        return null;
                                    }}
                                """, xpath)
                                
                                if intercepting_element:
                                    print(f"Found intercepting element: {intercepting_element['tag']} (XPath: {intercepting_element['xpath']})")
                                    
                                    # Click the intercepting element instead
                                    if intercepting_element['tag'] == 'a' and intercepting_element['href']:
                                        print(f"Clicking intercepting link with href: {intercepting_element['href']}")
                                        await page.goto(intercepting_element['href'], timeout=10000)
                                    else:
                                        print(f"Clicking intercepting element via XPath")
                                        await page.click(f"xpath={intercepting_element['xpath']}", timeout=5000)
                                else:
                                    # Last resort: Regular click
                                    print("No intercepting element found, trying regular click...")
                                    await page.click(f"xpath={xpath}", timeout=5000)
                            except Exception as intercept_error:
                                print(f"Error handling intercepting element: {intercept_error}")
                                # Fall back to regular click as last resort
                                await page.click(f"xpath={xpath}", timeout=5000)
                
                # Give a short delay for any immediate DOM updates
                await asyncio.sleep(0.5)
                
                # Check if this might have caused navigation
                return True  # Assume any click could cause navigation
            except Exception as e:
                print(f"Error clicking element {target_id}: {e}")
                
                # Check if a modal popup might be blocking the click
                print("Click failed - checking if a modal/popup is blocking interaction...")
                modal_dismissed = await detect_and_dismiss_modals(page)
                
                if modal_dismissed:
                    print("Modal dismissed. Trying click again...")
                    try:
                        # Try clicking again after modal dismissed
                        await page.click(f"xpath={xpath}", timeout=5000)
                        await asyncio.sleep(0.5)
                        return True
                    except Exception as retry_error:
                        print(f"Still failed to click after dismissing modal: {retry_error}")
                
                # Fallback: If it's a link or button with href, navigate directly to that URL
                if href and (element_type == 'link' or element_data.get('tag') == 'a'):
                    print(f"Click failed, falling back to navigating directly to href: {href}")
                    try:
                        # Ensure the href is a full URL
                        if href.startswith('/'):
                            # Convert relative URL to absolute using current page's origin
                            current_url = page.url
                            base_url = '/'.join(current_url.split('/')[:3])  # Get "https://domain.com" part
                            href = base_url + href
                        
                        await page.goto(href, timeout=10000)
                        return True  # Navigation happens
                    except Exception as nav_error:
                        print(f"Failed to navigate to href: {nav_error}")
                        return False
                
                # For buttons with form submission behavior, try to submit the form if the button is inside a form
                if element_type in ['button', 'submit']:
                    print("Click failed, attempting to find and submit parent form...")
                    try:
                        # Check if the button is inside a form and submit the form
                        has_form = await page.evaluate(f"""
                            (xpath) => {{
                                const button = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                if (!button) return false;
                                
                                // Find parent form
                                let current = button;
                                while (current && current.tagName !== 'FORM') {{
                                    current = current.parentElement;
                                }}
                                
                                if (current && current.tagName === 'FORM') {{
                                    current.submit();
                                    return true;
                                }}
                                return false;
                            }}
                        """, xpath)
                        
                        if has_form:
                            print("Form submission attempted")
                            await asyncio.sleep(1)  # Wait for the form to submit
                            return True  # Assume form submission causes navigation
                    except Exception as form_error:
                        print(f"Form submission attempt failed: {form_error}")
                
                return False
        else:
            print(f"Element with ID {target_id} not found. Available IDs: {', '.join(elements_dict_lower.keys())}")
            return False
    
    elif "TYPE" in command and len(cmd_parts) >= 3:
        target_id = cmd_parts[-1].lower()
        text_to_type = ' '.join(cmd_parts[2:])
        if target_id in elements_dict_lower:
            element_data = elements_dict_lower[target_id]
            xpath = element_data.get('xpath')
            print(f"Typing '{text_to_type}' into element: {target_id} (XPath: {xpath})")
            
            try:
                # First clear any existing text
                await page.wait_for_selector(f"xpath={xpath}", timeout=5000)
                await page.click(f"xpath={xpath}", click_count=3)  # Triple-click to select all text
                await page.keyboard.press("Delete")  # Clear the selected text
                
                # Then type the new text
                await page.type(f"xpath={xpath}", text_to_type)
                
                # Give a short delay for any immediate DOM updates
                await asyncio.sleep(0.5)
                
                return False  # Typing typically doesn't cause navigation
            except Exception as e:
                print(f"Error typing into element {target_id}: {e}")
                return False
        else:
            print(f"Element with ID {target_id} not found. Available IDs: {', '.join(elements_dict_lower.keys())}")
            return False
    
    elif "HOVER" in command and len(cmd_parts) >= 2:
        target_id = cmd_parts[-1].lower()
        if target_id in elements_dict_lower:
            element_data = elements_dict_lower[target_id]
            xpath = element_data.get('xpath')
            print(f"Hovering over element: {target_id} (XPath: {xpath})")
            
            try:
                await page.wait_for_selector(f"xpath={xpath}", timeout=5000)
                await page.hover(f"xpath={xpath}")
                
                # Give a short delay for any immediate DOM updates
                await asyncio.sleep(0.5)
                
                return False  # Hovering typically doesn't cause navigation
            except Exception as e:
                print(f"Error hovering over element {target_id}: {e}")
                return False
        else:
            print(f"Element with ID {target_id} not found. Available IDs: {', '.join(elements_dict_lower.keys())}")
            return False
    
    else:
        print(f"Unknown command: {command}")
        print("Available commands: BACKBTN, CLICK <unique_id>, TYPE <unique_id> <text>, HOVER <unique_id>, DISMISS")
        return False

# --- Main callback function for processing page content ---
async def process_page_content(page, visited_urls, force_reprocess=False):
    """
    Process the current page content, identifying interactive elements and saving HTML/JSON output
    Returns a dictionary mapping unique IDs to element data for interaction commands
    """
    try:
        # Wait for multiple load states to ensure page is fully ready
        print(f"Waiting for page to load completely: {page.url}")
        try:
            # First wait for basic DOM content loaded
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # Then wait for network to be mostly idle (no more than 2 connections for at least 500ms)
            await page.wait_for_load_state('networkidle', timeout=10000)
            
            # Also wait for the page to be visually stable
            await asyncio.sleep(1)  # Short additional delay for stability
        except Exception as load_error:
            print(f"Warning: Could not confirm complete page load: {load_error}")
            # Continue anyway since some elements might still be accessible
    
        # Ensure we have a valid page context before proceeding
        if page.url == "about:blank" or not page.url:
            print("Page is blank or has no URL, skipping processing")
            return {}
            
    except Exception as e:
        print(f"Error waiting for page load states: {e}")
        await asyncio.sleep(2)  # Give more time for page to stabilize before continuing
        
    url = page.url
    if not force_reprocess and url in visited_urls and url != "about:blank":
        print(f"Skipping already processed URL: {url}")
        return {}  # Return empty dict if not processing
    if url == "about:blank":
        print("Skipping blank page")
        return {}

    print(f"\nProcessing page: {url}")
    if not force_reprocess:
        visited_urls.add(url)
    
    try:
        interactive_elements_data = []
        element_id_map = {}  # Map of unique_id -> element data
        
        # --- Buttons ---
        buttons = await page.query_selector_all('button, input[type="button"], input[type="submit"], [role="button"]')
        for el_handle in buttons:
            text = (await el_handle.text_content() or await el_handle.get_attribute('value') or await el_handle.get_attribute('aria-label') or '').strip()
            element_type = await el_handle.get_attribute('type') or 'button'
            xpath = await el_handle.evaluate('el => window.getXPath(el)')
            class_name = await el_handle.get_attribute('class') or ''
            aria_label_val = await el_handle.get_attribute('aria-label') or ''
            unique_id = generate_unique_id(element_type, xpath, text, class_name, aria_label_val)
            await el_handle.evaluate('(el, uid) => el.setAttribute("data-interactive-id", uid)', unique_id)
            
            element_data = {
                'unique_id': unique_id, 'type': element_type, 'tag': await el_handle.evaluate('el => el.tagName.toLowerCase()'),
                'text': text, 'xpath': xpath, 'id': await el_handle.get_attribute('id') or '', 'class': class_name, 'aria-label': aria_label_val
            }
            interactive_elements_data.append(element_data)
            element_id_map[unique_id] = element_data
        
        # --- Text fields (input, textarea) ---
        inputs = await page.query_selector_all('input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea')
        for el_handle in inputs:
            element_type = await el_handle.get_attribute('type') or 'textarea'
            placeholder = await el_handle.get_attribute('placeholder') or ''
            value = await el_handle.input_value() or ''
            xpath = await el_handle.evaluate('el => window.getXPath(el)')
            class_name = await el_handle.get_attribute('class') or ''
            aria_label_val = await el_handle.get_attribute('aria-label') or ''
            id_text_source = placeholder or value or aria_label_val
            unique_id = generate_unique_id(element_type, xpath, id_text_source, class_name, aria_label_val)
            await el_handle.evaluate('(el, uid) => el.setAttribute("data-interactive-id", uid)', unique_id)
            
            element_data = {
                'unique_id': unique_id, 'type': element_type, 'tag': await el_handle.evaluate('el => el.tagName.toLowerCase()'),
                'placeholder': placeholder, 'value': value, 'xpath': xpath, 'id': await el_handle.get_attribute('id') or '', 'class': class_name, 'aria-label': aria_label_val
            }
            interactive_elements_data.append(element_data)
            element_id_map[unique_id] = element_data

        # --- Select dropdowns ---
        selects = await page.query_selector_all('select')
        for el_handle in selects:
            xpath = await el_handle.evaluate('el => window.getXPath(el)')
            class_name = await el_handle.get_attribute('class') or ''
            aria_label_val = await el_handle.get_attribute('aria-label') or ''
            selected_option_text = await el_handle.evaluate('el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ""')
            id_text_source = aria_label_val or selected_option_text
            unique_id = generate_unique_id('select', xpath, id_text_source, class_name, aria_label_val)
            await el_handle.evaluate('(el, uid) => el.setAttribute("data-interactive-id", uid)', unique_id)
            
            element_data = {
                'unique_id': unique_id, 'type': 'select', 'tag': 'select', 'xpath': xpath, 
                'id': await el_handle.get_attribute('id') or '', 'class': class_name, 'aria-label': aria_label_val,
                'selected_text': selected_option_text, 'value': await el_handle.input_value()
            }
            interactive_elements_data.append(element_data)
            element_id_map[unique_id] = element_data

        # --- Links ---
        links = await page.query_selector_all('a[href]')
        for el_handle in links:
            text = (await el_handle.text_content() or await el_handle.get_attribute('aria-label') or '').strip()
            href = await el_handle.get_attribute('href') or ''
            xpath = await el_handle.evaluate('el => window.getXPath(el)')
            class_name = await el_handle.get_attribute('class') or ''
            aria_label_val = await el_handle.get_attribute('aria-label') or ''
            unique_id = generate_unique_id('link', xpath, text, class_name, aria_label_val)
            await el_handle.evaluate('(el, uid) => el.setAttribute("data-interactive-id", uid)', unique_id)
            
            element_data = {
                'unique_id': unique_id, 'type': 'link', 'tag': 'a', 'text': text, 'href': href, 
                'xpath': xpath, 'id': await el_handle.get_attribute('id') or '', 'class': class_name, 'aria-label': aria_label_val
            }
            interactive_elements_data.append(element_data)
            element_id_map[unique_id] = element_data

        # --- Checkboxes and radio buttons ---
        checkables = await page.query_selector_all('input[type="checkbox"], input[type="radio"]')
        for el_handle in checkables:
            element_type = await el_handle.get_attribute('type')
            checked = await el_handle.is_checked()
            xpath = await el_handle.evaluate('el => window.getXPath(el)')
            class_name = await el_handle.get_attribute('class') or ''
            aria_label_val = await el_handle.get_attribute('aria-label') or ''
            name_attr = await el_handle.get_attribute('name') or ''
            id_text_source = name_attr or aria_label_val
            unique_id = generate_unique_id(element_type, xpath, id_text_source, class_name, aria_label_val)
            await el_handle.evaluate('(el, uid) => el.setAttribute("data-interactive-id", uid)', unique_id)
            
            element_data = {
                'unique_id': unique_id, 'type': element_type, 'tag': 'input', 'checked': checked, 
                'xpath': xpath, 'id': await el_handle.get_attribute('id') or '', 'class': class_name, 
                'aria-label': aria_label_val, 'name': name_attr
            }
            interactive_elements_data.append(element_data)
            element_id_map[unique_id] = element_data
        
        print(f"----- Found {len(interactive_elements_data)} interactive elements -----")
        
        html_content = await page.content()
        cleaned_html = clean_html_string(html_content)
        
        if cleaned_html:
            filename_base = "".join(c if c.isalnum() else "_" for c in url.replace("http://", "").replace("https://", ""))
            filename_base = filename_base[:100]

            html_filename = f"{filename_base}.html"
            html_filepath = os.path.join("cleaned_pages", html_filename)
            with open(html_filepath, "w", encoding="utf-8") as f:
                f.write(cleaned_html)
            print(f"Saved cleaned HTML to {html_filepath}")

            json_filename = f"{filename_base}_elements.json"
            json_filepath = os.path.join("cleaned_pages", json_filename)
            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(interactive_elements_data, f, indent=2)
            print(f"Saved interactive elements to {json_filepath}")
        
        # Print available unique IDs for user interaction
        print("\nAvailable elements for interaction:")
        for i, (unique_id, element_data) in enumerate(element_id_map.items(), 1):
            element_type = element_data.get('type', '')
            text = element_data.get('text', '') or element_data.get('placeholder', '') or element_data.get('aria-label', '')
            if text:
                print(f"{i}. {unique_id}: {element_type} - {text[:40]}")
            else:
                print(f"{i}. {unique_id}: {element_type}")
        
        return element_id_map
            
    except Exception as e:
        print(f"Error processing {url}: {e}")
        import traceback
        traceback.print_exc()
        return {}

# --- Interactive shell loop function ---
async def interactive_shell(page, visited_urls):
    """Run an interactive shell for page interaction"""
    current_elements = await process_page_content(page, visited_urls)
    
    print("\n=== Interactive Mode ===")
    print("Commands: BACKBTN, CLICK <unique_id>, TYPE <unique_id> <text>, HOVER <unique_id>, DISMISS")
    print("Enter 'exit' or 'quit' to exit")
    
    while True:
        # Print prompt and get user input
        command = input("\nEnter command > ").strip()
        
        if command.lower() in ['exit', 'quit']:
            print("Exiting interactive mode...")
            break
        
        if not command:
            continue
        
        # Handle the command
        try:
            might_navigate = await handle_interaction(page, command, current_elements)
            
            if might_navigate:
                # Wait for potential navigation to complete
                try:
                    print("Possible navigation detected, waiting for page to stabilize...")
                    # Wait for navigation to complete with a generous timeout
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    print("Page appears to be stable, processing elements...")
                    await asyncio.sleep(1.5)  # Give extra time for any JS to execute
                except Exception as nav_error:
                    print(f"Navigation wait error: {nav_error}")
                    print("Continuing with processing anyway...")
                    await asyncio.sleep(3)  # Give even more time to stabilize
                
                # Retry processing a few times if needed
                max_retries = 3
                for retry in range(max_retries):
                    try:
                        print(f"Processing page content (attempt {retry+1}/{max_retries})...")
                        current_elements = await process_page_content(page, visited_urls, force_reprocess=True)
                        if current_elements:  # If we got elements, we're good
                            break
                        await asyncio.sleep(1)  # Wait before retrying
                    except Exception as process_error:
                        print(f"Error processing page on attempt {retry+1}: {process_error}")
                        if retry < max_retries - 1:  # If not the last retry
                            print("Waiting before retrying...")
                            await asyncio.sleep(2)
                
                if not current_elements:
                    print("Warning: Could not successfully process page elements after navigation.")
                    print("You can try using the DISMISS command if there are popups, or retry your last command.")
            else:
                # If no navigation is expected, wait a short time and then re-process anyway
                print("Waiting for DOM updates...")
                await asyncio.sleep(1)
                try:
                    current_elements = await process_page_content(page, visited_urls, force_reprocess=True)
                except Exception as process_error:
                    print(f"Error processing page after interaction: {process_error}")
        except Exception as interaction_error:
            print(f"Error during command execution: {interaction_error}")
            print("Try using the DISMISS command if there are popups, or try again.")

# --- Main execution function ---
async def main():
    os.makedirs("cleaned_pages", exist_ok=True)
    visited_urls = set()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.add_init_script("""
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
        """)
        
        # Initially load the page
        start_url = "https://www.gap.com/"
        print(f"Navigating to initial page: {start_url}")
        try:
            await page.goto(start_url, wait_until="load")
        except Exception as e:
            print(f"Error loading initial page: {e}")
        
        print("\nBrowser is now open. Starting interactive mode.")
        
        # Register for automatic processing of page loads
        page.on("load", lambda: asyncio.create_task(process_page_content(page, visited_urls, force_reprocess=True)))
        
        # Run the interactive shell
        await interactive_shell(page, visited_urls)
        
        # Close the browser when done
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

