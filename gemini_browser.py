import os
import asyncio
from typing import Dict, List, Optional, Tuple, Union
import google.generativeai as genai
from human import HumanBrowser
import html_cleaner

# Add dotenv support to load .env file
try:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    load_dotenv()
    print("INFO: Loaded environment variables from .env file")
except ImportError:
    print("WARNING: python-dotenv not installed. To use .env files, install with: pip install python-dotenv")

# Configure the Gemini API with your API key
# You'll need to set this as an environment variable or provide it directly
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# If API key not found in environment, try to read it directly from .env file
if not GEMINI_API_KEY:
    try:
        with open(".env", "r") as env_file:
            for line in env_file:
                if line.strip().startswith("GEMINI_API_KEY"):
                    key_parts = line.strip().split("=", 1)
                    if len(key_parts) == 2:
                        GEMINI_API_KEY = key_parts[1].strip()
                        print("INFO: Loaded Gemini API key directly from .env file")
                        break
    except FileNotFoundError:
        print("WARNING: .env file not found")
    except Exception as e:
        print(f"WARNING: Error reading .env file: {e}")

class GeminiBrowser:
    """
    GeminiBrowser - A class that uses Google's Gemini API to analyze web page content
    and determine the next action to take with HumanBrowser.
    
    This class connects the HumanBrowser automation with Gemini's AI capabilities to:
    1. Extract the current state of a webpage (HTML content and interactive elements)
    2. Send this information to Gemini API for analysis
    3. Get recommendations on what action to take next
    4. Execute that action through HumanBrowser
    
    Args:
        human_browser: An instance of HumanBrowser or None (will create one if None)
        gemini_api_key: Your Gemini API key (default: uses GEMINI_API_KEY env variable)
        gemini_model: The Gemini model to use (default: "models/gemini-2.0-flash")
        max_tokens: Maximum tokens for Gemini response (default: 1024)
        temperature: Temperature for Gemini generation (default: 0.7)
    """
    
    def __init__(
        self,
        human_browser: Optional[HumanBrowser] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "models/gemini-2.0-flash",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        auto_close: bool = False
    ):
        # Set up Gemini API
        self.api_key = gemini_api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("Gemini API key is required. Provide it directly or set GEMINI_API_KEY environment variable, or add it to a .env file.")

        genai.configure(api_key=self.api_key)

        # Print model being used
        print(f"INFO: Using Gemini model: {gemini_model}")

        self.model = genai.GenerativeModel(
            model_name=gemini_model,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
        )

        # Set up HumanBrowser
        self.browser = human_browser
        self._browser_owner = False
        self.auto_close = auto_close

        # History of interactions for context
        self.interaction_history = []
        # Cache for the last processed elements
        self._cached_elements = {}

    async def initialize(self, start_url: Optional[str] = None) -> None:
        """Initialize the GeminiBrowser by creating a HumanBrowser instance if needed."""
        if self.browser is None:
            print("INFO (GeminiBrowser): Creating new HumanBrowser instance")
            self.browser = HumanBrowser(start_url=start_url, start_paused=False)
            self._browser_owner = True
            await self.browser.launch()
        elif not self.browser._context_instance:
            # If browser exists but isn't launched yet
            print("INFO (GeminiBrowser): Launching existing HumanBrowser instance")
            await self.browser.launch()

    async def close(self) -> None:
        """Close the browser if this instance owns it."""
        if self.browser and self._browser_owner and self.auto_close:
            await self.browser.close()

    async def get_page_data(self) -> Dict:
        """Get the current page data including HTML and interactive elements."""
        if not self.browser:
            raise ValueError("Browser not initialized. Call initialize() first.")

        current_page = await self.browser.get_current_page()
        if not current_page:
            raise ValueError("No active page available.")

        # Get the raw HTML
        raw_html = await current_page.content()
        
        # Count occurrences of 'ata-unique-id' in the HTML
        
        # Clean the HTML and extract interactive elements
        elements_dict, cleaned_html = await html_cleaner.extract_interactive_elements(raw_html)
        
        # Count occurrences of 'interactable' in cleaned_html
        interactable_count = cleaned_html.count("interact")
        print(f"INFO: 'interactable' appears {interactable_count} times in cleaned_html.")
        
        #print(cleaned_html[:10000])  # Print the first 10000 characters of cleaned HTML for debugging
        
        # Cache the elements
        self._cached_elements[current_page.url] = elements_dict
        
        # Log the number of interactive elements found
        print(f"INFO: Extracted {len(elements_dict)} interactive elements.")
        
        # Get the current URL
        url = current_page.url
        
        # Get the page title
        title = await current_page.title()
        
        return {
            "url": url,
            "title": title,
            "html": cleaned_html,
            "elements": elements_dict
        }
    
    def _create_prompt(self, page_data: Dict, task_description: Optional[str] = None) -> str:
        """Create a prompt for Gemini API based on the page data and task."""
        # Create context from previous interactions (limited to last 5)
        history_section = ""
        if self.interaction_history:
            history_section = "Previous actions:\n"
            for action in self.interaction_history[-5:]:
                history_section += f"- {action}\\n"
        print(page_data['html'][:1000])
        # Construct the prompt
        prompt = f"""
You are an AI web automation assistant. Analyze the web page and determine the next action to take to achieve the given task.

URL: {page_data['url']}
Page Title: {page_data['title']}

{history_section}


HTML Content (condensed, first 7000 characters):
{page_data['html']}...

{f'Task: {task_description}' if task_description else 'Determine the next action to take on this page.'}

Respond with a single command on a new line in one of these formats, followed by an explanation:
- LIST PAGES (List all open browser tabs)
- SWITCH N (Switch to page number N)
- GOTO url (Navigate to URL)
- CLICK element_id (Click on element with ID)
- TYPE element_id "text to type" (Type text into element with ID)
- HOVER element_id (Hover over element with ID)
- BACKBTN (Click browser back button)
- WAIT (Wait a short time if no action is needed)
- DONE (Indicate the task is complete)

Explanation: [brief explanation of why you\'re suggesting this action]
"""
        return prompt
    
    async def get_next_action(self, task_description: Optional[str] = None) -> Tuple[str, str]:
        """
        Get the next action to take based on the current page content.
        
        Args:
            task_description: Optional description of the task to accomplish
            
        Returns:
            Tuple of (action, explanation)
        """
        # Get the current page data
        page_data = await self.get_page_data()
        
        # Create the prompt for Gemini
        prompt = self._create_prompt(page_data, task_description)
        
        # Send to Gemini
        response = self.model.generate_content(prompt)
        
        # Parse the response
        response_text = response.text.strip()
        
        # Extract the action and explanation
        action_lines = [line for line in response_text.split('\n') if line.strip()]
        
        if not action_lines:
            return "WAIT", "No clear action determined"
        
        action = action_lines[0].strip()
        
        # Extract explanation if provided
        explanation = ""
        for line in action_lines:
            if line.startswith("Explanation:"):
                explanation = line[len("Explanation:"):].strip()
                break
        
        # Add to history
        self.interaction_history.append(action)
        
        return action, explanation
    
    async def execute_action(self, action: str) -> Union[bool, Dict]:
        """Execute the specified action using HumanBrowser."""
        if not self.browser:
            raise ValueError("Browser not initialized. Call initialize() first.")
        
        current_page = await self.browser.get_current_page()
        if not current_page:
            # Handle cases where no active page is found, especially after closing tabs
            print("WARN: No active page found to execute action.")
            # If we were trying to switch or list pages, that might still be possible
            if action.startswith("LIST PAGES") or action.startswith("SWITCH "):
                 pass # Allow these commands even without an active page
            else:
                return False # Cannot execute other actions
        
        print(f"Executing action: {action} on page: {current_page.url if current_page else 'N/A'}")
        
        # Handle specific commands that don't map directly to handle_interaction
        if action == "LIST PAGES":
            print("Listing open pages...")
            pages_info = []
            if self.browser._pages:
                 for i, page in enumerate(self.browser._pages):
                     active_marker = "* " if i == self.browser._active_page_index else "  "
                     url = page.url if page else "about:blank"
                     title = await page.title() if page and not page.is_closed() else "Closed Page"
                     pages_info.append(f"{active_marker}[{i}] {title} ({url})")
            print("Open Pages:\\n" + "\\n".join(pages_info))
            return {"action_type": "PAGES_LISTED", "pages": pages_info}
        
        elif action.startswith("SWITCH "):
            try:
                page_num = int(action.split(' ')[1])
                if 0 <= page_num < len(self.browser._pages):
                    self.browser._active_page_index = page_num
                    new_page = self.browser._pages[self.browser._active_page_index]
                    print(f"Switched to page {page_num}: {new_page.url}")
                    # Clear cached elements for the previous page if needed
                    self._cached_elements.pop(current_page.url, None)
                    return True # Action successful
                else:
                    print(f"Invalid page number: {page_num}")
                    return False
            except (ValueError, IndexError):
                print(f"Invalid SWITCH command format: {action}. Use 'SWITCH N'")
                return False
        
        elif action.startswith("GOTO "):
            url = action[5:].strip()
            try:
                # Add protocol if missing
                if not url.startswith(('http://', 'https://')):
                    url = f"https://{url}"
                await current_page.goto(url, wait_until="load")
                print(f"Navigated to: {current_page.url}")
                # Clear cached elements as the page content has changed
                self._cached_elements.pop(current_page.url, None)
                # The AI should explicitly request ELEMENTS for the new page
                return True
            except Exception as e:
                print(f"Navigation error: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        elif action == "WAIT":
            print("Waiting as recommended by Gemini")
            await asyncio.sleep(2)  # Wait a short time
            return True
        
        elif action == "DONE":
             print("Task marked as complete by Gemini.")
             return {"action_type": "TASK_COMPLETE"}
        
        else:
            # For interaction actions (CLICK, TYPE, HOVER, BACKBTN, DISMISS)
            # Need to provide cached elements to handle_interaction
            elements_on_page = self._cached_elements.get(current_page.url, {})
            if not elements_on_page and action in ["CLICK", "TYPE", "HOVER"]:
                print(f"WARNING: Attempted to execute interaction action '{action}' but no elements are listed for this page. Request ELEMENTS first.")
                return False # Indicate failure
            
            try:
                result = await self.browser.handle_interaction(action, elements_dict=elements_on_page)
                
                # After action, wait briefly and then the AI should decide the next step
                await asyncio.sleep(1.0)
                
                # Do not automatically check for new pages or process content here.
                # The AI should explicitly LIST PAGES or ELEMENTS after an interaction if needed.
                
                return result
                
            except Exception as e:
                print(f"Action execution error: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    async def analyze_and_act(self, task_description: Optional[str] = None) -> Tuple[str, str, Union[bool, Dict]]:
        """
        Analyze the current page and take the recommended action.
        
        Args:
            task_description: Optional description of the task to accomplish
            
        Returns:
            Tuple of (action, explanation, result). Result can be bool or Dict.
        """
        # Get the current page data, including cached elements if available
        page_data = await self.get_page_data()
        
        # Get next action and explanation from Gemini
        action, explanation = await self.get_next_action(task_description)
        
        # Execute the chosen action
        result = await self.execute_action(action)
        
        return action, explanation, result
    
    async def complete_task(
        self, 
        task_description: str, 
        max_steps: int = 15, 
        wait_time: float = 2.0
    ) -> List[Tuple[str, str, Union[bool, Dict]]]:
        """
        Attempt to complete a task by taking multiple actions until completion.
        
        Args:
            task_description: Description of the task to accomplish
            max_steps: Maximum number of steps to take
            wait_time: Wait time between steps in seconds
            
        Returns:
            List of (action, explanation, result) tuples for each step
        """
        results = []
        
        for step in range(max_steps):
            print(f"\nStep {step+1}/{max_steps}: Analyzing page and determining action...")
            
            # Analyze the current page and get the next action
            action, explanation, result = await self.analyze_and_act(task_description)
            
            # Record the result
            results.append((action, explanation, result))
            print(f"Suggested action: {action}")
            print(f"Explanation: {explanation}")
            print(f"Execution Result: {result}")
            
            # Check for task completion signal from AI
            if isinstance(result, dict) and result.get("action_type") == "TASK_COMPLETE":
                 print("Task completed as signaled by AI.")
                 break
            
            # If the action was listing elements, the AI might immediately request another action
            # We don't need to wait as long in this case, but a brief pause is still good.
            if isinstance(result, dict) and result.get("action_type") == "ELEMENTS_LISTED":
                await asyncio.sleep(0.5) # Short pause after listing elements
            else:
                 # Wait between actions as specified
                 await asyncio.sleep(wait_time)
        
        print(f"\nTask attempt finished after {len(results)} steps.")
        return results

# Example usage
async def main():
    # Initialize GeminiBrowser
    try:
        print("Initializing GeminiBrowser...")
        gemini_browser = GeminiBrowser(auto_close=False)

        try:
            # Start the browser
            print("Starting browser...")
            await gemini_browser.initialize("https://everfi.com")
            
            # Complete a task
            print("Starting task execution...")
            results = await gemini_browser.complete_task(
                task_description="login with google as a student.", 
                max_steps=15,  # Increased from 5 to 15
                wait_time=2.0  # Increased wait time between actions
            )
            
            # Print results
            print("\nTask completion results:")
            for i, (action, explanation, result) in enumerate(results):
                print(f"Step {i+1}: {action} - {'Success' if isinstance(result, bool) and result else 'Completed'}")
                print(f"  Explanation: {explanation}")
            
        except Exception as e:
            print(f"ERROR during browser operation: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Always close the browser, but safely
            print("Closing browser...")
            try:
                # Properly clean up resources before closing
                if gemini_browser.browser:
                    # Make sure we're not processing page content during close
                    if hasattr(gemini_browser.browser, '_processing_active'):
                        gemini_browser.browser._processing_active[0] = False
                    
                    # Close any extra pages first to avoid context errors
                    if gemini_browser.browser._pages:
                        for i in range(len(gemini_browser.browser._pages) - 1, 0, -1):
                            try:
                                page = gemini_browser.browser._pages[i]
                                if page and not page.is_closed():
                                    await page.close()
                            except Exception as page_close_err:
                                print(f"Warning: Error closing page {i}: {page_close_err}")
                
                # Now close the browser
                await gemini_browser.close()
            except Exception as close_err:
                print(f"Warning: Error during browser closing: {close_err}")
                import traceback
                traceback.print_exc()
    
    except Exception as e:
        print(f"FATAL ERROR initializing GeminiBrowser: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting GeminiBrowser main function...")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Unhandled exception in main loop: {e}")
        import traceback
        traceback.print_exc()
