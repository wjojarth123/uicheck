from playwright.sync_api import sync_playwright
import cohere
import json
import os
from typing import List, Dict, Any
from dotenv import load_dotenv
import random # For random browsing
import re # Import re for regular expressions

#hey dont do this
load_dotenv()
class WebNavigator:
    def __init__(self, cohere_api_key: str):
        self.co =cohere.Client(cohere_api_key)
        
    def get_interactable_elements(self, page) -> List[Dict[str, Any]]:
        """Get all interactable elements from the current page."""
        elements = page.evaluate("""() => {
            const elements = [];
            const selectors = [
                'button', 'input', 'select', 'textarea', 'a',
                '[role="button"]', '[role="link"]', '[role="checkbox"]',
                '[role="radio"]', '[role="switch"]', '[role="tab"]',
                '[role="menuitem"]', '[contenteditable="true"]'
            ];
            
            let elementId = 0;
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        elements.push({
                            id: `el_${elementId++}`,
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            text: el.textContent?.trim() || '',
                            xpath: getXPath(el)
                        });
                    }
                });
            });
            
            function getXPath(element) {
                if (element.id !== '')
                    return `//*[@id="${element.id}"]`;
                if (element === document.body)
                    return '/html/body';
                
                let ix = 0;
                const siblings = element.parentNode.childNodes;
                for (let i = 0; i < siblings.length; i++) {
                    const sibling = siblings[i];
                    if (sibling === element)
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                        ix++;
                }
            }
            
            return elements;
        }""")
        return elements

    def get_cohere_guidance(self, task: str, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get guidance from Cohere on how to interact with elements."""
        # Create a simplified list of elements with ID, type, and text
        simplified_elements = []
        for el in elements:
            if not el['text'].strip() and el['type'] not in ['text', 'search', 'email', 'password']:
                continue
                
            element_info = f"{el['id']}: [{el['tag']}"
            if el['type']:
                element_info += f" type={el['type']}"
            element_info += f"] {el['text']}"
            simplified_elements.append(element_info)
        
        prompt = f"""Task: {task}

Available elements:
{json.dumps(simplified_elements, indent=2)}

You are a web automation assistant. Your job is to provide the next action to take in a simple command format.
Return a JSON object with:
- action: one of ["CLICK", "TYPE", "SELECT", "WAIT"]
- element_id: the ID of the element to interact with (e.g. "el_0")
- value: the value to type or select (if applicable)
- explanation: brief explanation of why this action was chosen

Important: 
- For navigation tasks, look for links or buttons with relevant text
- For search tasks, look for input fields with type="search" or "text"
- For form tasks, look for input fields with appropriate types
- For adding items to cart, look for buttons with "add to cart" or similar text

Example responses:
{{
    "action": "CLICK",
    "element_id": "el_0",
    "value": "",
    "explanation": "CLICK 'Add to Cart' button to add item"
}}

{{
    "action": "TYPE",
    "element_id": "el_1",
    "value": "mens jacket",
    "explanation": "TYPE 'mens jacket' in search field"
}}

{{
    "action": "SELECT",
    "element_id": "el_2",
    "value": "medium",
    "explanation": "SELECT 'medium' size from dropdown"
}}"""

        print("\n=== Sending to Cohere ===\n")
        print(prompt)
        print("\n=== End of Cohere Prompt ===\n")

        try:
            response = self.co.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.3,
                k=0,
                stop_sequences=[],
                return_likelihoods='NONE'
            )
            
            print("\n=== Cohere Response ===\n")
            print(response.generations[0].text)
            print("\n=== End of Cohere Response ===\n")
            
            result = json.loads(response.generations[0].text)
            
            # Validate the response format
            required_fields = ["action", "element_id", "explanation"]
            for field in required_fields:
                if field not in result:
                    print(f"Missing required field: {field}")
                    return {
                        "action": "ERROR",
                        "explanation": f"Invalid response format: missing {field}"
                    }
            
            # Validate action type
            valid_actions = ["CLICK", "TYPE", "SELECT", "WAIT"]
            if result["action"].upper() not in valid_actions:
                print(f"Invalid action: {result['action']}")
                return {
                    "action": "ERROR",
                    "explanation": f"Invalid action: {result['action']}. Must be one of {valid_actions}"
                }
            
            # Convert action to uppercase for consistency
            result["action"] = result["action"].upper()
            return result
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {str(e)}")
            return {
                "action": "ERROR",
                "explanation": f"Failed to parse JSON response: {str(e)}"
            }
        except Exception as e:
            print(f"Error from Cohere API: {str(e)}")
            return {
                "action": "ERROR",
                "explanation": f"Error from Cohere API: {str(e)}"
            }

    def execute_action(self, page, action: Dict[str, Any]):
        """Execute the action specified by Cohere."""
        try:
            # Find the element by its ID
            element_id = action["element_id"]
            element = next((el for el in self.get_interactable_elements(page) if el["id"] == element_id), None)
            
            if not element:
                print(f"Element {element_id} not found")
                return False
                
            if action["action"] == "CLICK":
                page.click(element["xpath"])
            elif action["action"] == "TYPE":
                page.fill(element["xpath"], action["value"])
            elif action["action"] == "SELECT":
                page.select_option(element["xpath"], action["value"])
            elif action["action"] == "WAIT":
                page.wait_for_selector(element["xpath"])
            return True
        except Exception as e:
            print(f"Error executing action: {str(e)}")
            return False

    def navigate_and_execute(self, url: str, task: str):
        """Navigate to URL and execute task using Cohere guidance."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url)
            
            while True:
                elements = self.get_interactable_elements(page)
                action = self.get_cohere_guidance(task, elements)
                
                if action["action"] == "ERROR":
                    print("Error getting guidance from Cohere")
                    break
                    
                print(f"Executing: {action['explanation']}")
                success = self.execute_action(page, action)
                
                if not success:
                    print("Failed to execute action")
                    break
                    
                # Wait for page to stabilize
                page.wait_for_load_state("networkidle")
                
            browser.close()

def main():
    # Get Cohere API key from environment variable

    navigator = WebNavigator(os.getenv('COHERE_API_KEY'))
    
    # Example usage
    url = "https://www.gap.com"
    task = "add a mens jacket to the cart on gap.com"
    
    navigator.navigate_and_execute(url, task)

if __name__ == "__main__":
    main()
