from playwright.sync_api import sync_playwright
import cohere
import time
import os
from dotenv import load_dotenv
import random # For random browsing
import re # Import re for regular expressions

#hey dont do this
load_dotenv()

USER_DATA_DIR = "playwright_user_data"

class WebInteractor:
    def __init__(self):
        self.co = cohere.Client(os.getenv('COHERE_API_KEY'))
        self.playwright = sync_playwright().start()
        
        # For persistent context, we launch it directly from the browser type
        # The browser instance itself isn't stored as self.browser in this setup
        # because launch_persistent_context returns the context directly.
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, 
            headless=False,
            args=["--disable-blink-features=AutomationControlled"], # Standard arg to look less like a bot
            # --no-sandbox is generally not needed/recommended for typical Playwright use and has security implications.
            # Playwright handles sandboxing by default.
            # ignore_default_args=["--enable-automation"] # This can also be useful
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.context.on("page", self._handle_new_page)
        self._last_clicked_gap_element_id = None # For tracking last clicked element by a stable ID if possible

    def _handle_new_page(self, new_page):
        print(f"\nDebug - New page/tab opened. Initial URL: {new_page.url}")
        old_page_url = "N/A (page might be closed)"
        try:
            if hasattr(self, 'page') and self.page and not self.page.is_closed():
                old_page_url = self.page.url
        except Exception:
            pass # Page might be in an unusable state
        
        # It's crucial to update self.page reference immediately
        current_old_page = self.page # Keep a reference if needed for comparison or cleanup
        self.page = new_page
        print(f"Debug - Switched self.page from {old_page_url} to new page. Current new page URL: {self.page.url}")

        try:
            self.page.bring_to_front()
            print(f"Debug - New page {self.page.url} brought to front.")

            # Wait for the new page to complete its initial navigation, especially if it starts as about:blank
            # This will wait until the URL is no longer 'about:blank' or a timeout occurs.
            if "about:blank" in self.page.url:
                print(f"Debug - New page is {self.page.url}, waiting for it to navigate...")
                try:
                    self.page.wait_for_url(lambda url: url != "about:blank", timeout=15000) 
                    print(f"Debug - New page navigated. Current URL: {self.page.url}")
                except Exception as e_wait_url:
                    print(f"Debug - Timeout or error waiting for new page to navigate from about:blank: {e_wait_url}. Will try to load state anyway.")
            
            # Now wait for the (potentially navigated) page to load its content
            self.page.wait_for_load_state('load', timeout=20000) # 'load' is more comprehensive than 'domcontentloaded'
            print(f"Debug - New page {self.page.url} fully loaded (state: 'load').")

        except Exception as e:
            print(f"Debug - Error during new page handling for {self.page.url if self.page else 'unknown page'}: {e}")
            # If new_page is self.page and it's closed, this might indicate the popup closed itself fast.
            if self.page and self.page.is_closed():
                 print("Debug - The new page seems to have closed itself quickly.")
                 # Potentially revert to current_old_page if it's still valid and open?
                 # if current_old_page and not current_old_page.is_closed():
                 # self.page = current_old_page
                 # print(f"Debug - Reverted self.page back to {self.page.url} as new page closed.")

    def warm_up_browser(self):
        print("\n--- Starting Browser Warm-up ---")
        try:
            # 1. Visit gap.com and browse with some Cohere guidance
            print("Warm-up: Navigating to gap.com")
            self.page.goto("https://www.gap.com", timeout=90000)
            self.page.wait_for_load_state('domcontentloaded', timeout=60000)
            time.sleep(3)

            # More robust popup dismissal using re.compile for text matching
            common_close_patterns = [
                (self.page.locator('button', has_text=re.compile(r"accept|agree|got it|ok", re.IGNORECASE)), "Regex for accept/agree/ok"),
                (self.page.locator('button[aria-label*="close"i]'), "aria-label close (case insensitive)"), # Attribute selector for close
                (self.page.locator('div[role="dialog"] button', has_text=re.compile(r"no thanks|continue", re.IGNORECASE)), "Regex for no thanks/continue in dialog")
            ]
            popup_dismissed_this_session = False
            if not popup_dismissed_this_session:
                for locator, desc in common_close_patterns:
                    try:
                        for i_btn in range(locator.count()):
                            btn = locator.nth(i_btn)
                            if btn.is_visible(timeout=2000):
                                print(f"Warm-up: Attempting to close Gap popup/banner ({desc})")
                                btn.click(timeout=5000); time.sleep(1.5)
                                print("Warm-up: Gap Popup/banner dismissal attempted.")
                                popup_dismissed_this_session = True; break 
                        if popup_dismissed_this_session: break
                    except Exception as e_popup_gap:
                        print(f"Warm-up: No Gap popup/banner ({desc}) or error: {e_popup_gap}")
            
            print("Warm-up: Browsing gap.com with some Cohere-assisted clicks")
            clicks_done_gap = 0
            attempted_elements_ids_gap = set() # Track elements attempted to click in this Gap session

            for i in range(5): # Reduced to 5 click attempts
                if clicks_done_gap >= 5: break # Ensure we don't exceed
                time.sleep(random.uniform(2, 4)) # More human-like pause
                
                base_clickables_a = self.page.locator('a:visible', has_text=re.compile(r"\S+"))
                base_clickables_button = self.page.locator('button:visible', has_text=re.compile(r"\S+"))
                
                all_potential_locators = []
                for idx in range(base_clickables_a.count()): all_potential_locators.append(base_clickables_a.nth(idx))
                for idx in range(base_clickables_button.count()): all_potential_locators.append(base_clickables_button.nth(idx))

                if not all_potential_locators:
                    print(f"Warm-up (Gap Interaction {i+1}/5): No suitable clickable elements found. Ending Gap interaction.")
                    break

                # Prepare elements for Cohere selection
                candidate_elements_for_cohere = []
                temp_locators_map = {}
                random.shuffle(all_potential_locators)

                for idx_cand, el_locator_cand in enumerate(all_potential_locators):
                    if len(candidate_elements_for_cohere) >= 10: break
                    try:
                        el_text_cand = el_locator_cand.inner_text(timeout=500).strip().split('\n')[0][:70]
                        el_tag_cand = el_locator_cand.evaluate("node => node.tagName.toLowerCase()")
                        unique_id_cand = f"{el_tag_cand}_{el_text_cand}_{idx_cand}"
                        candidate_elements_for_cohere.append({"id": unique_id_cand, "tag": el_tag_cand, "text": el_text_cand})
                        temp_locators_map[unique_id_cand] = el_locator_cand
                    except Exception: continue
                
                if not candidate_elements_for_cohere:
                    print(f"Warm-up (Gap Interaction {i+1}/5): No new candidate elements for Cohere. Trying random click or ending.")
                    # Fallback to a simple random click if Cohere can't be used
                    if all_potential_locators:
                        target_locator = random.choice(all_potential_locators)
                    else: break # No elements at all
                else:
                    # Ask Cohere to pick an element
                    cohere_prompt = "You are browsing a retail website (Gap.com). Which of these clickable elements seems most reasonable or interesting for a user to click next? Respond with only the ID of your chosen element. Example: button_Shop Men_3\n\n"
                    for el_data in candidate_elements_for_cohere:
                        cohere_prompt += f"ID: {el_data['id']} (Type: {el_data['tag']}, Text: \"{el_data['text']}\")\n"
                    cohere_prompt += "\nChosen ID:"
                    
                    print(f"Warm-up: Asking Cohere to choose from {len(candidate_elements_for_cohere)} elements...")
                    # print(f"Cohere Prompt for Gap warm-up:\n{cohere_prompt}") # For debugging prompt
                    try:
                        response = self.co.generate(
                            prompt=cohere_prompt,
                            max_tokens=20,
                            temperature=0.5,
                            stop_sequences=["\n"]
                        )
                        chosen_id = response.generations[0].text.strip()
                        print(f"Warm-up: Cohere chose ID: '{chosen_id}'")
                        target_locator = temp_locators_map.get(chosen_id)
                        if not target_locator:
                            print(f"Warm-up: Cohere chose an invalid ID or element not found in map. Falling back to random.")
                            target_locator = random.choice(list(temp_locators_map.values())) if temp_locators_map else random.choice(all_potential_locators)
                    except Exception as e_cohere_warmup:
                        print(f"Warm-up: Error during Cohere call for Gap click: {e_cohere_warmup}. Falling back to random.")
                        target_locator = random.choice(all_potential_locators) # Fallback

                # Click the chosen/fallback element
                if not target_locator:
                    print(f"Warm-up (Gap Interaction {i+1}/5): No target locator selected. Ending Gap interaction.")
                    break

                try:
                    element_text_display = "N/A"
                    el_id_for_tracking_current = "N/A_Tracker"
                    try: 
                        element_text_display = target_locator.inner_text(timeout=1000).strip().split('\n')[0]
                        el_tag_current = target_locator.evaluate("node => node.tagName.toLowerCase()")
                        el_id_for_tracking_current = f"{el_tag_current}_{element_text_display[:30]}"
                    except Exception: pass
                    
                    print(f"Warm-up (Gap Interaction {i+1}/5): Clicking on '{element_text_display[:60].strip()}' (ID for tracking: {el_id_for_tracking_current})")
                    # attempted_elements_ids_gap.add(el_id_for_tracking_current) # Add to attempted after trying to click
                    target_locator.click(timeout=15000)
                    self.page.wait_for_load_state('domcontentloaded', timeout=25000)
                    print(f"Warm-up (Gap Interaction {i+1}/5): Click successful, page state reloaded.")
                    clicks_done_gap += 1
                    attempted_elements_ids_gap.clear() # Clear after successful nav implied by reload
                except Exception as e_click_gap:
                    print(f"Warm-up (Gap Interaction {i+1}/5): Error clicking element '{element_text_display[:60].strip()}': {e_click_gap}")
            
            print(f"Warm-up: Completed {clicks_done_gap} interactions on gap.com.")
            
            # 2. Google search for "cat gifs"
            print("\nWarm-up: Navigating to google.com for cat gif search")
            self.page.goto("https://www.google.com", timeout=60000)
            self.page.wait_for_load_state('domcontentloaded', timeout=30000)
            print("Warm-up: Searching for 'cat gifs' on Google")
            
            # Robust Google cookie button handling using re.compile
            google_cookie_locators = [
                (self.page.locator('button', has_text=re.compile(r"Accept all|Reject all|Agree", re.IGNORECASE)), "Cookie button regex"),
                (self.page.locator('button:has-text("Accept all")'), "Exact Accept all"),
                (self.page.locator('button:has-text("Agree")'), "Exact Agree")
            ]
            google_cookie_dismissed = False
            for locator, desc in google_cookie_locators:
                if google_cookie_dismissed: break
                try:
                    for i in range(locator.count()):
                        btn = locator.nth(i)
                        if btn.is_visible(timeout=2000):
                            print(f"Warm-up: Clicking Google cookie button ({desc})")
                            btn.click(timeout=5000); time.sleep(1)
                            google_cookie_dismissed = True; break
                    if google_cookie_dismissed: break
                except Exception as e_cookie: 
                    print(f"Warm-up: Google cookie button ({desc}) not found or error: {e_cookie}") 
            
            self.page.locator('[name="q"]').fill("cat gifs")
            self.page.locator('[name="q"]').press("Enter")
            
            print("Warm-up: Waiting for Google search results page to load...")
            self.page.wait_for_selector("div#search", timeout=30000) # Wait for search results container
            self.page.wait_for_load_state('domcontentloaded', timeout=30000)
            print("Warm-up: Google search results page loaded.")

            print("Warm-up: Attempting to click first search result for cat gifs")
            first_result_links = self.page.locator('div#search a[href^="http"]:has(h3)').all()
            if first_result_links:
                try:
                    first_link_element = first_result_links[0]
                    target_url = first_link_element.get_attribute('href')
                    result_text = first_link_element.locator('h3').inner_text().strip()
                    print(f"Warm-up: Found first search result: '{result_text[:70]}' linking to {target_url}")
                    
                    current_url_before_click = self.page.url
                    print(f"Warm-up: Clicking search result. Current URL: {current_url_before_click}")
                    first_link_element.click(timeout=10000)
                    
                    print("Warm-up: Waiting for navigation to search result page...")
                    # Wait for URL to change from Google or for a new page to load fully
                    self.page.wait_for_url(lambda url: not url.startswith("https://www.google.com/search"), timeout=20000)
                    self.page.wait_for_load_state('domcontentloaded', timeout=30000) 
                    
                    final_url = self.page.url
                    if final_url != current_url_before_click and not final_url.startswith("https://www.google.com"):
                        print(f"Warm-up: Successfully navigated to search result page: {final_url}")
                    else:
                        print(f"Warm-up: Failed to navigate away from Google or URL did not change as expected. Final URL: {final_url}")

                except Exception as e_search_click:
                    print(f"Warm-up: Error clicking or validating search result navigation: {e_search_click}")
            else:
                print("Warm-up: No search result links found (locator: div#search a[href^=\"http\"]:has(h3)).")

            print("--- Browser Warm-up Complete ---")
        except Exception as e:
            print(f"Error during browser warm-up: {e}")

    def navigate_to(self, url):
        """Navigate to a specific URL"""
        self.page.goto(url)
        time.sleep(2)  # Wait for page to load

    def _get_visible_elements(self):
        """Get only visible and interactive elements from the page"""
        elements = {
            'buttons': [],
            'inputs': [],
            'accordions': []
        }
        
        # Get visible buttons
        buttons = self.page.query_selector_all('button:visible, [role="button"]:visible, a:visible')
        for button in buttons:
            text = button.inner_text().strip()
            if text:
                elements['buttons'].append(text)

        # Get visible inputs
        inputs = self.page.query_selector_all('input:visible, textarea:visible')
        for input_elem in inputs:
            placeholder = input_elem.get_attribute('placeholder') or input_elem.get_attribute('name') or input_elem.get_attribute('id')
            if placeholder:
                elements['inputs'].append(placeholder)

        # Get visible accordions
        accordions = self.page.query_selector_all('[role="button"]:visible, [aria-expanded]:visible')
        for accordion in accordions:
            text = accordion.inner_text().strip()
            if text:
                elements['accordions'].append(text)

        return elements

    def interact_with_page(self, instruction):
        """Use Cohere to understand and execute natural language instructions"""
        # Get only visible elements
        elements = self._get_visible_elements()
        
        # Create a concise prompt for Cohere
        prompt = f"""
        Available elements:
        - Buttons: {', '.join(elements['buttons'])}
        - Input fields: {', '.join(elements['inputs'])}
        - Accordions: {', '.join(elements['accordions'])}
        
        User instruction: {instruction}
        
        Based on the above, what action should be taken? Respond with one of:
        1. CLICK [element text]
        2. TYPE [element text] [content]
        3. EXPAND [accordion text]
        4. COLLAPSE [accordion text]
        """

        print("\nDebug - Prompt sent to Cohere:")
        print(prompt)

        # Get response from Cohere
        response = self.co.generate(
            prompt=prompt,
            max_tokens=50,
            temperature=0.3,
            stop_sequences=["\n"]
        )

        action = response.generations[0].text.strip()
        print("\nDebug - Cohere's response:")
        print(action)
        
        self._execute_action(action)

    def _execute_action(self, action):
        """Execute the action determined by Cohere"""
        target_element_text = ""
        interaction_type = ""
        content_to_type = ""

        if action.startswith("CLICK"):
            target_element_text = action.split("CLICK", 1)[1].strip()
            interaction_type = "click"
        elif action.startswith("TYPE"):
            parts = action.split("TYPE", 1)[1].strip().split(" ", 1)
            target_element_text = parts[0].strip()
            content_to_type = parts[1].strip() if len(parts) > 1 else ""
            interaction_type = "type"
        elif action.startswith("EXPAND"):
            target_element_text = action.split("EXPAND", 1)[1].strip()
            interaction_type = "click"
        elif action.startswith("COLLAPSE"):
            target_element_text = action.split("COLLAPSE", 1)[1].strip()
            interaction_type = "click"
        else:
            print(f"Debug - Unknown action: {action}")
            return

        target_element_text = target_element_text.strip('"').strip("'")

        print(f"\nDebug - Attempting to {interaction_type} element with text/placeholder: '{target_element_text}'")
        if content_to_type:
            print(f"Debug - Content to type: '{content_to_type}' (will be typed char-by-char)")

        action_successful = False
        
        # --- Try direct interaction on the main page first ---
        try:
            if not self.page or self.page.is_closed():
                print("Debug - Main page is closed or not available. Skipping direct interaction.")
                raise Exception("Main page closed")

            if interaction_type == "click":
                print(f"Debug - Attempting direct click on main page for: '{target_element_text}'")
                self.page.click(f'text="{target_element_text}"', timeout=7000)
                print(f"Debug - Successfully clicked '{target_element_text}' directly on main page.")
                action_successful = True
            elif interaction_type == "type":
                print(f"Debug - Attempting natural typing on main page for: '{target_element_text}'")
                locator_str = f'[placeholder="{target_element_text}"], [name="{target_element_text}"], [id="{target_element_text}"], input[value="{target_element_text}"], textarea:has-text("{target_element_text}"), input:has-text("{target_element_text}")'
                target_locator = self.page.locator(locator_str).first
                if target_locator.is_visible(timeout=5000):
                    target_locator.click() # Focus the field first
                    target_locator.type(content_to_type, delay=random.uniform(75, 200)) # Type with delay
                    print(f"Debug - Successfully typed naturally into '{target_element_text}' directly on main page.")
                    action_successful = True
                else:
                    print(f"Debug - Element '{target_element_text}' not visible for typing directly on main page.")
                    text_locator_str = f'input:text-is("{target_element_text}"):visible, textarea:text-is("{target_element_text}"):visible'
                    text_target_locator = self.page.locator(text_locator_str).first
                    if text_target_locator.is_visible(timeout=2000):
                        text_target_locator.click() # Focus
                        text_target_locator.type(content_to_type, delay=random.uniform(75, 200))
                        print(f"Debug - Successfully typed naturally into element by its text content on main page.")
                        action_successful = True
                    else:
                         print(f"Debug - Element by text not visible for natural typing.")

        except Exception as e_main:
            print(f"Debug - Direct interaction on main page for '{target_element_text}' failed: {e_main}")

        if action_successful:
            time.sleep(random.uniform(0.5, 1.2)) # Shorter sleep after successful action
            return

        # --- Fallback to checking iframes if direct interaction failed or element not found ---
        print(f"Debug - Direct main page interaction failed or element not found for '{target_element_text}'. Checking iframes...")
        if not self.page or self.page.is_closed():
            print("Error: Page is closed, cannot check iframes.")
            return

        page_frames = []
        try: page_frames = self.page.frames
        except Exception as e_frames: print(f"Debug - Could not retrieve frames from page: {e_frames}"); return

        print(f"Debug - Found {len(page_frames)} frames (including main frame). Checking subframes for element...")
        for i, frame in enumerate(page_frames):
            if frame.is_detached(): continue
            if frame == self.page.main_frame and action_successful: continue 
            
            frame_url_for_debug = "N/A"
            try: 
                frame_url_for_debug = frame.url
            except Exception: 
                pass # Keep it as N/A if frame.url access fails
            
            print(f"Debug - Checking frame {i} (URL: {frame_url_for_debug})")
            try:
                if interaction_type == "click":
                    frame.click(f'text="{target_element_text}"', timeout=3000)
                    print(f"Debug - Successfully clicked '{target_element_text}' in frame {i} (URL: {frame_url_for_debug}).")
                    action_successful = True
                elif interaction_type == "type":
                    locator_str_frame = f'[placeholder="{target_element_text}"], [name="{target_element_text}"], [id="{target_element_text}"], input[value="{target_element_text}"], textarea:has-text("{target_element_text}"), input:has-text("{target_element_text}")'
                    target_locator_in_frame = frame.locator(locator_str_frame).first
                    if target_locator_in_frame.is_visible(timeout=3000):
                        target_locator_in_frame.click() # Focus
                        target_locator_in_frame.type(content_to_type, delay=random.uniform(75, 200)) # Type with delay
                        print(f"Debug - Successfully typed naturally into '{target_element_text}' in frame {i} (URL: {frame_url_for_debug}).")
                        action_successful = True
                    else:
                        text_locator_frame_str = f'input:text-is("{target_element_text}"):visible, textarea:text-is("{target_element_text}"):visible'
                        text_target_locator_frame = frame.locator(text_locator_frame_str).first
                        if text_target_locator_frame.is_visible(timeout=2000):
                            text_target_locator_frame.click() # Focus
                            text_target_locator_frame.type(content_to_type, delay=random.uniform(75, 200))
                            print(f"Debug - Successfully typed naturally into element by its text content in frame {i}.")
                            action_successful = True
                        else:
                            print(f"Debug - Element '{target_element_text}' not visible for natural typing in frame {i} (URL: {frame_url_for_debug}).")

                if action_successful:
                    time.sleep(random.uniform(0.5, 1.2))
                    return
            except Exception as e_frame:
                print(f"Debug - Error while checking/interacting in frame {i} (URL: {frame_url_for_debug}) for '{target_element_text}': {e_frame}")
        
        if not action_successful:
            print(f"Error: Could not find or interact with element '{target_element_text}' after checking page and all iframes.")

    def close(self):
        """Clean up resources"""
        if self.context:
            self.context.close()
        # self.browser.close() is not needed here as launch_persistent_context manages the browser lifecycle with the context
        if self.playwright:
            self.playwright.stop()

def main():
    my_email = os.getenv("MY_EMAIL")
    my_password = os.getenv("MY_PASSWORD")

    if not all([my_email, my_password, os.getenv("COHERE_API_KEY") ]):
        print("Error: Ensure COHERE_API_KEY, MY_EMAIL, and MY_PASSWORD are set in your .env file.")
        return

    interactor = WebInteractor()
    try:
        # Perform browser warm-up
        interactor.warm_up_browser()

        # Navigate to a website
        print("\n--- Starting Main Task: Navigating to classmate.app ---")
        interactor.navigate_to("https://www.classmate.app")
        
        # Interact with the page using natural language
        interactor.interact_with_page("Click the Sign in button") # Adjusted instruction for clarity
        interactor.interact_with_page("Authenticate with Google")
        # Use credentials from .env file
        interactor.interact_with_page(f"Type {my_email} in the email field") 
        interactor.interact_with_page("press next")
        interactor.interact_with_page(f"type {my_password} in the password field")
        # Potentially add a "press next" or "sign in" for the password page if needed
        # interactor.interact_with_page("press next") 
        
        print("\nWaiting for a moment to observe results...")
        time.sleep(10) # Increased wait time
    except Exception as e:
        print(f"An error occurred in main: {e}")
    finally:
        print("Closing interactor.")
        interactor.close()

if __name__ == "__main__":
    main() 