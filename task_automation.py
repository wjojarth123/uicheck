from playwright.sync_api import sync_playwright
import cohere
import time
import os
from dotenv import load_dotenv
import json
from typing import List, Dict, Any, Optional
import argparse
import requests  # For Llama API

# Load environment variables
load_dotenv()

# Constants
USER_DATA_DIR = "playwright_user_data"
COHERE_API_KEY = os.getenv('COHERE_API_KEY')
LLAMA_API_URL = "https://ai.hackclub.com/chat/completions"

class TaskAutomator:
    def __init__(self, use_llama=False):
        # Initialize LLM clients
        self.use_llama = use_llama
        self.conversation_history = []  # To track context for Llama API
        self.chat_history = []  # To track full hisory and prevent repetitive actions
        
        if not use_llama:
            if not COHERE_API_KEY:
                raise ValueError("COHERE_API_KEY environment variable is not set")
            self.co = cohere.Client(COHERE_API_KEY)
        else:
            print("Using Llama API for text generation")
        
        # Initialize Playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()
        
    def navigate_to(self, url: str) -> None:
        """Navigate to a specified URL"""
        print(f"Navigating to {url}")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                print(f"Warning: Network idle timeout: {e}")
            time.sleep(2)  # Allow time for any popups or overlays to appear
            
            # Try to close common popups/modals
            self._dismiss_popups()
        except Exception as e:
            print(f"Error during navigation: {e}")
            # Try again with less strict conditions
            try:
                self.page.goto(url, timeout=60000)
                time.sleep(5)  # Just wait a fixed time
            except Exception as e2:
                print(f"Critical error during navigation retry: {e2}")
    
    def _dismiss_popups(self) -> None:
        """Attempt to dismiss common popups and modals"""
        popup_selectors = [
            'button:has-text("Accept")', 
            'button:has-text("Close")',
            'button:has-text("No Thanks")',
            'button:has-text("I Accept")',
            'button:has-text("Continue")',
            'button[aria-label*="close" i]',
            '.modal-close',
            '.popup-close',
            '[data-testid="close-button"]'
        ]
        
        for selector in popup_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    self.page.locator(selector).first.click(timeout=2000)
                    print(f"Closed popup using selector: {selector}")
                    time.sleep(1)
            except Exception:
                continue
                
    def get_interactable_elements(self) -> List[Dict[str, Any]]:
        """Identify and extract properties of all interactable elements on the page"""
        print("Identifying interactable elements on the page...")
        
        # Get all interactable elements including those outside viewport
        elements_data = self.page.evaluate("""() => {
            const interactableElements = [];
            let elementIndex = 0;
            
            // Query common interactive elements
            const selectors = [
                'a', 'button', 'input', 'select', 'textarea', 
                '[role="button"]', '[role="link"]', '[role="checkbox"]',
                '[role="radio"]', '[role="tab"]', '[role="menuitem"]',
                'div.clickable', 'div[onclick]', 'div[class*="button"]',
                'span[class*="button"]', 'img[class*="product"]'
            ];
            
            // Get unique elements from all selectors
            const elements = [];
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    // Include elements regardless of viewport visibility
                    const style = window.getComputedStyle(el);
                    const isInvisible = (
                        style.visibility === 'hidden' || 
                        style.display === 'none' || 
                        parseFloat(style.opacity) < 0.1
                    );
                    
                    if (!elements.includes(el) && !isInvisible) {
                        elements.push(el);
                    }
                });
            });
            
            // Extract relevant information for each element
            elements.forEach(element => {
                // Get element properties
                const rect = element.getBoundingClientRect();
                
                // Get text
                let text = element.innerText || element.textContent || '';
                text = text.trim().replace(/\\s+/g, ' ').substring(0, 100);
                
                // Get element type and value
                const tagName = element.tagName.toLowerCase();
                const elementType = element.type || '';
                const value = element.value !== undefined ? String(element.value) : '';
                
                // Get attributes
                const placeholder = element.getAttribute('placeholder') || '';
                const ariaLabel = element.getAttribute('aria-label') || '';
                const title = element.getAttribute('title') || '';
                const role = element.getAttribute('role') || '';
                const href = tagName === 'a' ? (element.getAttribute('href') || '') : '';
                const name = element.getAttribute('name') || '';
                const id = element.getAttribute('id') || '';
                const classes = element.getAttribute('class') || '';
                
                // Get image information if available
                const isImage = tagName === 'img';
                const imageSrc = isImage ? (element.getAttribute('src') || '') : '';
                const imageAlt = isImage ? (element.getAttribute('alt') || '') : '';
                
                // Construct a description of the element
                let description = '';
                if (text) description += text;
                if (ariaLabel && !description.includes(ariaLabel)) description += (description ? ' - ' : '') + ariaLabel;
                if (placeholder && !description.includes(placeholder)) description += (description ? ' - ' : '') + placeholder;
                if (title && !description.includes(title)) description += (description ? ' - ' : '') + title;
                if (imageAlt && !description.includes(imageAlt)) description += (description ? ' - ' : '') + imageAlt;
                
                if (!description) {
                    // If no meaningful description, try to create one
                    if (tagName === 'a' && href) description = `Link to ${href.substring(0, 50)}`;
                    else if (elementType === 'submit') description = 'Submit button';
                    else if (elementType === 'checkbox') description = `Checkbox ${element.checked ? '(checked)' : '(unchecked)'}`;
                    else if (id) description = `${tagName} with id ${id}`;
                    else if (classes) description = `${tagName} with class ${classes.substring(0, 50)}`;
                    else description = `${tagName} element at position (${Math.round(rect.left)}, ${Math.round(rect.top)})`;
                }
                
                // Check if element is in viewport
                const isInViewport = (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                );
                
                // Get scroll position
                const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                
                // Get XPATH for more reliable element identification
                function getXPath(element) {
                    if (element.id) return `//*[@id="${element.id}"]`;
                    
                    let path = '';
                    while (element && element.nodeType === Node.ELEMENT_NODE) {
                        let index = 1;
                        for (let sibling = element.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
                            if (sibling.nodeName === element.nodeName) index++;
                        }
                        const tagName = element.nodeName.toLowerCase();
                        const pathIndex = (index > 1) ? `[${index}]` : '';
                        path = `/${tagName}${pathIndex}${path}`;
                        element = element.parentNode;
                    }
                    return path;
                }
                
                // Store both DOM coordinates and document coordinates
                interactableElements.push({
                    elementIndex,
                    tagName,
                    type: elementType,
                    text: text || '',
                    value: value,
                    placeholder,
                    description,
                    // Key for scrolling: store both viewport and absolute coordinates
                    position: {
                        // Coordinates relative to viewport (what you see on screen)
                        viewport: {
                            x: Math.round(rect.left + rect.width / 2),
                            y: Math.round(rect.top + rect.height / 2)
                        },
                        // Coordinates relative to document (absolute position in page)
                        document: {
                            x: Math.round(rect.left + scrollLeft + rect.width / 2),
                            y: Math.round(rect.top + scrollTop + rect.height / 2)
                        }
                    },
                    dimensions: {
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    isInViewport,
                    xpath: getXPath(element),
                    attributes: {
                        role,
                        href,
                        id,
                        name,
                        class: classes,
                        'aria-label': ariaLabel,
                        title,
                        src: imageSrc,
                        alt: imageAlt
                    }
                });
                
                elementIndex++;
            });
            
            return interactableElements;
        }""")
        
        print(f"Found {len(elements_data)} interactable elements")
        return elements_data
        
    def analyze_page_context(self, task: str) -> Dict[str, Any]:
        """Use selected LLM to analyze the current page context and determine next actions"""
        print("Analyzing page context...")
        
        # Get page information
        page_info = self.page.evaluate("""() => {
            return {
                title: document.title,
                url: window.location.href,
                textContent: document.body.innerText.substring(0, 1000),
                isProductPage: Boolean(
                    document.querySelector('.product-detail') || 
                    document.querySelector('[data-testid="product-title"]') ||
                    document.querySelector('[class*="product"][class*="detail"]') ||
                    document.title.includes('Product') || 
                    document.title.match(/buy|shop|product|detail/i)
                ),
                hasAddToCartButton: Boolean(
                    document.querySelector('[data-testid="add-to-cart"]') ||
                    document.querySelector('button[class*="add-to-cart"]') ||
                    document.querySelector('button[class*="add-to-bag"]') ||
                    document.querySelector('button:contains("Add to")') ||
                    Array.from(document.querySelectorAll('button')).some(b => 
                        b.innerText.toLowerCase().includes('add to cart') || 
                        b.innerText.toLowerCase().includes('add to bag')
                    )
                ),
                hasSizeOptions: Boolean(
                    document.querySelector('[data-testid="size-selector"]') ||
                    document.querySelector('[class*="size"][class*="selector"]') ||
                    document.querySelector('[class*="size-option"]') ||
                    document.querySelector('select[name="size"]') ||
                    document.querySelectorAll('[role="radiogroup"]').length > 0
                ),
                hasColorOptions: Boolean(
                    document.querySelector('[data-testid="color-selector"]') ||
                    document.querySelector('[class*="color"][class*="selector"]') ||
                    document.querySelector('[class*="color-option"]') ||
                    document.querySelector('select[name="color"]') ||
                    document.querySelectorAll('[role="radiogroup"]').length > 1
                ),
                hasSizeSelected: Boolean(
                    document.querySelector('[data-testid="size-selector"] [aria-selected="true"]') ||
                    document.querySelector('[class*="size"][class*="selected"]') ||
                    document.querySelector('input[name="size"]:checked')
                ),
                hasColorSelected: Boolean(
                    document.querySelector('[data-testid="color-selector"] [aria-selected="true"]') ||
                    document.querySelector('[class*="color"][class*="selected"]') ||
                    document.querySelector('input[name="color"]:checked')
                ),
                pageType: (
                    document.querySelector('[class*="product"][class*="detail"]') ? 'product' :
                    document.querySelectorAll('[class*="product-card"]').length > 3 ? 'category' :
                    document.querySelector('form[action*="checkout"]') ? 'checkout' :
                    document.querySelector('[class*="cart"]') ? 'cart' :
                    'unknown'
                )
            };
        }""")
        
        # Create the reasoning prompt
        prompt = f"""You are an AI assistant that helps users navigate e-commerce websites.

Task: {task}

Current Page Information:
- URL: {page_info.get('url', 'Unknown')}
- Title: {page_info.get('title', 'Unknown')}
- Page Type: {page_info.get('pageType', 'Unknown')}
- Is Product Detail Page: {page_info.get('isProductPage', False)}
- Has Add to Cart Button: {page_info.get('hasAddToCartButton', False)}
- Has Size Options: {page_info.get('hasSizeOptions', False)}
- Has Size Selected: {page_info.get('hasSizeSelected', False)}
- Has Color Options: {page_info.get('hasColorOptions', False)}
- Has Color Selected: {page_info.get('hasColorSelected', False)}
- Page Content Excerpt: {page_info.get('textContent', '')[:300]}

Based on the information above, analyze the current page and provide:
1. Current page type (home page, category page, product detail page, cart, etc.)
2. Current progress toward completing the task
3. What actions need to be taken next
4. Any requirements that must be completed before adding to cart (such as selecting size/color)

Format your response as follows:
PAGE_TYPE: [type of page]
PROGRESS: [current progress toward task]
REQUIRED_ACTIONS: [comma-separated list of actions needed, e.g., "select size, select color, click add to cart"]
NEXT_ACTION: [specifically what should be done next]
REASONING: [brief explanation of your analysis]
"""

        # Call LLM for reasoning based on the selected engine
        try:
            if self.use_llama:
                reasoning_text = self._call_llama(prompt, "page_analysis")
            else:
                response = self.co.generate(
                    prompt=prompt,
                    max_tokens=300,
                    temperature=0.2,
                    p=0.75,
                    frequency_penalty=0,
                    presence_penalty=0,
                    truncate="START"
                )
                reasoning_text = response.generations[0].text.strip()
            
            print(f"Page analysis:\n{reasoning_text}")
            
            # Parse the response to extract structured information
            analysis = {
                "page_type": "unknown",
                "progress": "unknown",
                "required_actions": [],
                "next_action": "",
                "reasoning": ""
            }
            
            for line in reasoning_text.split('\n'):
                if line.startswith("PAGE_TYPE:"):
                    analysis["page_type"] = line.replace("PAGE_TYPE:", "").strip().lower()
                elif line.startswith("PROGRESS:"):
                    analysis["progress"] = line.replace("PROGRESS:", "").strip()
                elif line.startswith("REQUIRED_ACTIONS:"):
                    actions_text = line.replace("REQUIRED_ACTIONS:", "").strip()
                    if actions_text:
                        analysis["required_actions"] = [a.strip() for a in actions_text.split(',')]
                elif line.startswith("NEXT_ACTION:"):
                    analysis["next_action"] = line.replace("NEXT_ACTION:", "").strip()
                elif line.startswith("REASONING:"):
                    analysis["reasoning"] = line.replace("REASONING:", "").strip()
            
            # Add the original page_info to the analysis
            analysis["page_info"] = page_info
            
            return analysis
            
        except Exception as e:
            print(f"Error during page analysis: {e}")
            return {
                "page_type": page_info.get('pageType', 'unknown'),
                "progress": "error_during_analysis",
                "required_actions": [],
                "next_action": "continue_with_default",
                "reasoning": f"Error during analysis: {str(e)}",
                "page_info": page_info
            }
    
    def _call_llama(self, prompt: str, context_type: str = "general") -> str:
        """Call the Llama API with contextual history"""
        
        # Create a message that includes context from previous interactions
        context_message = ""
        if context_type in ["element_selection", "page_analysis"] and self.conversation_history:
            # Include relevant history for this context type
            relevant_history = [msg for msg in self.conversation_history if msg["type"] == context_type]
            
            # If we have relevant history, include the last few interactions
            if relevant_history:
                last_interactions = relevant_history[-3:]  # Get last 3 interactions
                context_message = "Previous context:\n"
                for interaction in last_interactions:
                    context_message += f"- {interaction['summary']}\n"
                context_message += "\n"
        
        # Prepare the full prompt with context
        full_prompt = f"{context_message}{prompt}"
        
        # Make the API call
        try:
            response = requests.post(
                LLAMA_API_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "messages": [{"role": "user", "content": full_prompt}]
                }
            )
            
            response_json = response.json()
            
            if "choices" in response_json and len(response_json["choices"]) > 0:
                result = response_json["choices"][0]["message"]["content"]
                
                # Create a summary for context tracking
                summary = ""
                if context_type == "element_selection":
                    # Extract element number if present
                    for line in result.split('\n'):
                        if line.startswith("ELEMENT:"):
                            element_num = line.replace("ELEMENT:", "").strip()
                            summary = f"Selected element {element_num}"
                            break
                elif context_type == "page_analysis":
                    # Extract page type and next action
                    page_type = "unknown"
                    next_action = "unknown"
                    for line in result.split('\n'):
                        if line.startswith("PAGE_TYPE:"):
                            page_type = line.replace("PAGE_TYPE:", "").strip()
                        elif line.startswith("NEXT_ACTION:"):
                            next_action = line.replace("NEXT_ACTION:", "").strip()
                    
                    summary = f"Analyzed page as '{page_type}', next action: {next_action}"
                
                # Store context in history
                if summary:
                    self.conversation_history.append({
                        "type": context_type,
                        "prompt": prompt,
                        "response": result,
                        "summary": summary
                    })
                    
                    # Limit history size
                    if len(self.conversation_history) > 20:
                        self.conversation_history = self.conversation_history[-20:]
                
                return result
            else:
                print(f"Error in Llama API response: {response_json}")
                return "ERROR: Could not parse Llama API response"
                
        except Exception as e:
            print(f"Error calling Llama API: {e}")
            return f"ERROR: Failed to call Llama API: {e}"

    def choose_element_for_task(self, task: str, elements: List[Dict[str, Any]], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Use selected LLM to decide which element to interact with based on the task and context"""
        if not elements:
            print("No interactable elements found on the page")
            return None
            
        print(f"Asking {'Llama' if self.use_llama else 'Cohere'} to select an element for task: {task}")
        
        # Prepare a simplified view of each element with minimal token usage
        elements_info = ""
        for element in elements:
            # Get the most essential information about the element
            element_id = element['elementIndex']
            tag_type = f"{element['tagName']}"
            if element.get('type'):
                tag_type += f" (type={element['type']})"
                
            # Just get the most essential text, limited to a very short snippet
            text = element.get('text', '')[:30]  # Limit to 30 chars
            if len(text) == 30 and len(element.get('text', '')) > 30:
                text += "..."
                
            # Only include ID if it exists and is short
            element_id_attr = ""
            if element.get('attributes', {}).get('id') and len(element.get('attributes', {}).get('id')) < 20:
                element_id_attr = f" id='{element['attributes']['id']}'"
                
            # Only include if it's a form control
            element_name = ""
            if element.get('attributes', {}).get('name') and element['tagName'] in ['input', 'select', 'textarea', 'button']:
                element_name = f" name='{element['attributes']['name']}'"
                
            # Super compact representation
            elements_info += f"#{element_id}: {tag_type}{element_id_attr}{element_name} - {text}\n"
        
        # Include context in the prompt if available
        page_context = ""
        next_action_hint = ""
        
        # Extract context components if available
        page_analysis = context.get("page_analysis") if context else None
        webpage_summary = context.get("webpage_summary") if context else None
        page_changes = context.get("page_changes") if context else None
        
        # Add page changes context if available - this is critical for selection requirements
        if page_changes and page_changes.get("has_changes"):
            page_context += f"""
Page Changes Detected:
- Change Summary: {page_changes.get('change_summary', 'Unknown')}
"""
            
            if page_changes.get("error_messages"):
                page_context += "- Error Messages:\n"
                for error in page_changes.get("error_messages")[:3]:  # Limit to first 3
                    page_context += f"  * {error}\n"
                    
            if page_changes.get("required_selections"):
                page_context += "- Required Selections:\n"
                for selection in page_changes.get("required_selections"):
                    page_context += f"  * {selection}\n"
                    
            if page_changes.get("recommended_action"):
                page_context += f"- Recommended Action: {page_changes.get('recommended_action')}\n"
                
            # Set next action hint based on detected changes
            if page_changes.get("required_selections"):
                selection_terms = page_changes.get("required_selections")
                if any("size" in term.lower() for term in selection_terms):
                    next_action_hint = "Look for size selection elements"
                elif any("color" in term.lower() for term in selection_terms):
                    next_action_hint = "Look for color selection elements"
                elif any("fit" in term.lower() for term in selection_terms):
                    next_action_hint = "Look for fit selection elements"
                elif any("waist" in term.lower() for term in selection_terms):
                    next_action_hint = "Look for waist size selection elements"
                elif any("length" in term.lower() for term in selection_terms):
                    next_action_hint = "Look for length selection elements"
                else:
                    selections = ", ".join(selection_terms)
                    next_action_hint = f"Look for elements to select {selections}"
        
        if webpage_summary:
            page_context += f"""
Webpage Summary:
- Page Type: {webpage_summary.get('page_type', 'Unknown')}
- Main Purpose: {webpage_summary.get('main_purpose', 'Unknown')}
- Key Information: {', '.join(webpage_summary.get('key_information', [])[:3])}
- Available Actions: {', '.join(webpage_summary.get('available_actions', [])[:3])}
"""
        
        if page_analysis:
            page_context += f"""
Page Analysis:
- Page Type: {page_analysis.get('page_type', 'Unknown')}
- Current Progress: {page_analysis.get('progress', 'Unknown')}
- Required Actions: {', '.join(page_analysis.get('required_actions', []))}
- Next Action Needed: {page_analysis.get('next_action', 'Unknown')}
"""
            
            # Add specific hints based on the page type and next action
            if not next_action_hint and page_analysis.get('page_type') == 'product':
                if 'size' in page_analysis.get('next_action', '').lower():
                    next_action_hint = "Look for size selection elements (buttons or dropdowns with sizes like S, M, L, XL)"
                elif 'color' in page_analysis.get('next_action', '').lower():
                    next_action_hint = "Look for color selection elements (color names or swatches)"
                elif any(term in page_analysis.get('next_action', '').lower() for term in ['add to cart', 'add to bag']):
                    next_action_hint = "Look for an 'Add to Cart' or 'Add to Bag' button"
            elif not next_action_hint and page_analysis.get('page_type') == 'category':
                next_action_hint = "Look for a product that matches the task requirements"
            elif not next_action_hint and page_analysis.get('page_type') == 'home':
                next_action_hint = "Look for navigation elements to find the right category"
                
        # Add step history context to avoid repetitive actions
        step_history = ""
        steps_taken = [entry for entry in self.chat_history if entry.get("type") == "task_step"]
        if steps_taken:
            recent_steps = steps_taken[-3:]  # Last 3 steps
            step_history = "Recent actions taken:\n"
            for step in recent_steps:
                step_data = step.get("data", {})
                step_history += f"- {step_data.get('action', 'clicked')} '{step_data.get('element_description', '')}'\n"
        
        # Create the prompt for LLM
        prompt = f"""You are an AI assistant that helps automate web interactions.
        
Task: {task}

{page_context}
{step_history}
Your job is to determine which ONE element should be interacted with to progress toward completing the task.

{next_action_hint}

Available Elements (format is #ID: type - text):
{elements_info}

Based on the task "{task}" and the current page context, which element should be interacted with next?
Choose exactly ONE element by its number (e.g., "#5") and explain why this element is the best choice.
If it's an input field that needs text, also suggest what text to enter.

For shopping tasks, remember:
1. On category pages: select a specific product
2. On product pages: select required attributes (size, color, fit, etc.) before adding to cart
3. Look for buttons that match the next required action

IMPORTANT: If error messages or required selections were detected, prioritize addressing those issues first before continuing.
Do not repeat actions that were recently taken. Choose a different approach if previous actions didn't progress the task.

Your response format must be:
ELEMENT: #[element number]
ACTION: [click/input/select]
INPUT_VALUE: [text to input, if applicable]
EXPLANATION: [brief explanation of why this element helps accomplish the task]
"""

        # Call LLM based on selected engine
        try:
            if self.use_llama:
                decision_text = self._call_llama(prompt, "element_selection")
            else:
                response = self.co.generate(
                    prompt=prompt,
                    max_tokens=250,
                    temperature=0.2,
                    p=0.75,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stop_sequences=["Task:", "Available Elements:"],
                    truncate="START"  # Enable truncation from the start of the prompt if needed
                )
                decision_text = response.generations[0].text.strip()
            
            print(f"{'Llama' if self.use_llama else 'Cohere'}'s decision:\n{decision_text}")
            
            # Parse the response to get the chosen element
            element_match = None
            for line in decision_text.split('\n'):
                if line.startswith("ELEMENT:"):
                    element_num = line.replace("ELEMENT:", "").strip()
                    if "#" in element_num:
                        element_num = element_num.replace("#", "").strip()
                    try:
                        element_index = int(element_num)
                        # Find the element with this index
                        for element in elements:
                            if element['elementIndex'] == element_index:
                                element_match = element
                                break
                    except ValueError:
                        continue
            
            # Extract action and input value if available
            action = "click"  # Default action
            input_value = ""
            explanation = ""
            for line in decision_text.split('\n'):
                if line.startswith("ACTION:"):
                    action = line.replace("ACTION:", "").strip().lower()
                elif line.startswith("INPUT_VALUE:"):
                    input_value = line.replace("INPUT_VALUE:", "").strip()
                elif line.startswith("EXPLANATION:"):
                    explanation = line.replace("EXPLANATION:", "").strip()
            
            if element_match:
                element_match['action'] = action
                element_match['input_value'] = input_value
                element_match['explanation'] = explanation
                return element_match
            
            print("No valid element was chosen by the LLM")
            return None
        except Exception as e:
            print(f"Error getting LLM's decision: {e}")
            return None
    
    def perform_action(self, element: Dict[str, Any]) -> bool:
        """Perform the specified action on the chosen element"""
        if not element:
            return False
            
        element_index = element['elementIndex']
        action = element.get('action', 'click')
        input_value = element.get('input_value', '')
        
        # Check if this is a repetitive action
        interaction_data = {
            "element": {
                "elementIndex": element_index,
                "xpath": element.get("xpath", ""),
                "description": element.get("description", ""),
                "tagName": element.get("tagName", "")
            },
            "action": action,
            "input_value": input_value
        }
        
        if self.has_recent_interaction("element_interaction", interaction_data, time_window=30):
            print(f"Detected repetitive action on element #{element_index}. Skipping to avoid loop.")
            return False
            
        print(f"Performing {action} on element #{element_index}: {element['description']}")
        
        # Track this interaction
        self._track_interaction("element_interaction", interaction_data)
        
        # Capture the page state before the action for later comparison
        pre_action_state = self.page.evaluate("""() => {
            return {
                url: window.location.href,
                title: document.title,
                textContent: document.body.innerText.substring(0, 1000)
            };
        }""")
        self._track_interaction("page_state", pre_action_state)
        
        # CRITICAL FIX: If element is not in viewport, we MUST scroll to it first
        if not element['isInViewport']:
            print("Element is outside viewport. Scrolling to it...")
            try:
                # Try to scroll using element's XPath if available
                if element.get('xpath'):
                    xpath = element['xpath']
                    # Use XPath to scroll the element into view
                    scroll_script = f"""
                    (xpath) => {{
                        const element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (element) {{
                            element.scrollIntoView({{behavior: 'auto', block: 'center', inline: 'center'}});
                            return true;
                        }}
                        return false;
                    }}
                    """
                    scroll_success = self.page.evaluate(scroll_script, element['xpath'])
                    
                    if scroll_success:
                        print(f"Successfully scrolled to element using XPath: {xpath}")
                        # Important: wait for scroll to finish and page to stabilize
                        time.sleep(1.5)
                    else:
                        print("Failed to scroll using XPath, trying document coordinates")
                        # Try to scroll using absolute document coordinates
                        doc_x = element['position']['document']['x']
                        doc_y = element['position']['document']['y']
                        
                        self.page.evaluate(f"""
                        (x, y) => {{
                            window.scrollTo({{
                                left: x - (window.innerWidth / 2),
                                top: y - (window.innerHeight / 2),
                                behavior: 'auto'
                            }});
                        }}
                        """, doc_x, doc_y)
                        
                        print(f"Scrolled to document coordinates: ({doc_x}, {doc_y})")
                        time.sleep(1.5)
                else:
                    # Fallback to document coordinates
                    doc_x = element['position']['document']['x']
                    doc_y = element['position']['document']['y']
                    
                    self.page.evaluate(f"""
                    (x, y) => {{
                        window.scrollTo({{
                            left: x - (window.innerWidth / 2),
                            top: y - (window.innerHeight / 2),
                            behavior: 'auto'
                        }});
                    }}
                    """, doc_x, doc_y)
                    
                    print(f"Scrolled to document coordinates: ({doc_x}, {doc_y})")
                    time.sleep(1.5)
                    
                # After scrolling, we need to re-check if the element is now in viewport
                # This is crucial for correct clicking
                is_in_viewport = self.page.evaluate(f"""
                () => {{
                    const elements = document.querySelectorAll('*');
                    const el = elements[{element_index}];
                    if (!el) return false;
                    
                    const rect = el.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                    );
                }}
                """)
                
                if is_in_viewport:
                    print("Element is now in viewport after scrolling")
                else:
                    print("Element still not in viewport after scrolling, will try additional methods")
                    # One more attempt with a different method
                    self.page.evaluate(f"""
                    () => {{
                        const elements = document.querySelectorAll('*');
                        const el = elements[{element_index}];
                        if (el) {{
                            el.scrollIntoView({{behavior: 'auto', block: 'center', inline: 'center'}});
                        }}
                    }}
                    """)
                    time.sleep(1.5)
            except Exception as e:
                print(f"Error during scrolling: {e}")
                # We'll still try to interact with the element
        
        action_success = False
        
        try:
            # SPECIAL HANDLING FOR GAP.COM MEN'S MENU
            # Check for specific patterns in element description
            description_lower = element['description'].lower()
            
            # Special handling for the men's section on Gap.com (direct navigation)
            if "men" in description_lower and element['tagName'] == 'button' and "division" in str(element['attributes']):
                print("Detected Men's menu button on Gap.com - using direct navigation approach")
                # Direct navigation to men's page
                self.page.goto("https://www.gap.com/browse/division.do?cid=5063")
                print("Directly navigated to men's section")
                try:
                    self.page.wait_for_load_state("networkidle", timeout=10000)
                except Exception as e:
                    print(f"Network idle timeout (normal if no navigation occurred): {e}")
                action_success = True
            
            # Check if element has a link that we can extract and navigate to directly
            href = None
            if element['attributes'].get('href'):
                href = element['attributes']['href']
            else:
                # Try to find if this is a button that has an associated link we can extract
                try:
                    href = self.page.evaluate(f"""
                    () => {{
                        const elements = document.querySelectorAll('*');
                        const el = elements[{element_index}];
                        if (!el) return null;
                        
                        // Check for an associated anchor inside or nearby
                        const associatedLink = el.querySelector('a') || 
                                              el.parentElement.querySelector('a[aria-label="${element['description']}"]') || 
                                              document.querySelector(`a[aria-label="${element['description']}"]`);
                        
                        if (associatedLink && associatedLink.href) {{
                            return associatedLink.href;
                        }}
                        
                        return null;
                    }}
                    """)
                except Exception:
                    href = None
            
            if href:
                print(f"Found href link: {href}")
                # Navigate directly to the href
                try:
                    self.page.goto(href)
                    print(f"Directly navigated to: {href}")
                    try:
                        self.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception as e:
                        print(f"Network idle timeout (normal if no navigation occurred): {e}")
                    action_success = True
                except Exception as e:
                    print(f"Error navigating to href: {e}")
                    # Continue with other methods
            
            # Now try multiple interaction methods if we haven't succeeded yet
            if not action_success:
                # Strategy 1: Try by ID or unique attributes first
                if element['attributes']['id']:
                    selector = f"#{element['attributes']['id']}"
                    print(f"Using ID selector: {selector}")
                    element_locator = self.page.locator(selector)
                    
                    if element_locator.count() > 0:
                        if action == 'click':
                            element_locator.first.click(timeout=5000)
                        elif action == 'input':
                            element_locator.first.fill(input_value, timeout=5000)
                        elif action == 'select':
                            element_locator.first.select_option(input_value, timeout=5000)
                        
                        print(f"Action performed successfully using ID selector")
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception as e:
                            print(f"Network idle timeout (normal if no navigation occurred): {e}")
                        action_success = True
                
                # Strategy 2: Try XPath if available (most reliable for elements outside viewport)
                if not action_success and element.get('xpath'):
                    print(f"Using XPath: {element['xpath']}")
                    xpath_locator = self.page.locator(f"xpath={element['xpath']}")
                    
                    if xpath_locator.count() > 0:
                        if action == 'click':
                            xpath_locator.first.click(timeout=5000)
                        elif action == 'input':
                            xpath_locator.first.fill(input_value, timeout=5000)
                        elif action == 'select':
                            xpath_locator.first.select_option(input_value, timeout=5000)
                        
                        print(f"Action performed successfully using XPath")
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception as e:
                            print(f"Network idle timeout (normal if no navigation occurred): {e}")
                        action_success = True
                
                # Strategy 3: Check if the element has an overlay, try to click through or around it
                if not action_success:
                    try:
                        has_overlay = self.page.evaluate(f"""
                        () => {{
                            const elements = document.querySelectorAll('*');
                            const el = elements[{element_index}];
                            if (!el) return false;
                            
                            // Check if clicking would be intercepted
                            const rect = el.getBoundingClientRect();
                            const centerX = rect.left + rect.width / 2;
                            const centerY = rect.top + rect.height / 2;
                            
                            // Get element at this point - if it's not our target, we have an overlay
                            const elementAtPoint = document.elementFromPoint(centerX, centerY);
                            return elementAtPoint !== el ? elementAtPoint : false;
                        }}
                        """)
                        
                        if has_overlay:
                            print("Detected element is covered by an overlay. Attempting to handle overlay...")
                            # Try to click the overlay element first
                            try:
                                self.page.evaluate(f"""
                                () => {{
                                    const elements = document.querySelectorAll('*');
                                    const el = elements[{element_index}];
                                    if (!el) return;
                                    
                                    const rect = el.getBoundingClientRect();
                                    const centerX = rect.left + rect.width / 2;
                                    const centerY = rect.top + rect.height / 2;
                                    
                                    // Try to find and click the overlay element
                                    const overlayElement = document.elementFromPoint(centerX, centerY);
                                    if (overlayElement) {{
                                        overlayElement.click();
                                    }}
                                }}
                                """)
                                time.sleep(1)  # Wait for any overlay transitions
                            except Exception as e:
                                print(f"Error handling overlay: {e}")
                    except Exception:
                        pass
                
                # Strategy 4: Try by position after ensuring we scrolled
                if not action_success:
                    print("Trying to click by position coordinates")
                    
                    # Get current scroll position to adjust coordinates
                    scroll_left = self.page.evaluate("window.pageXOffset || document.documentElement.scrollLeft")
                    scroll_top = self.page.evaluate("window.pageYOffset || document.documentElement.scrollTop")
                    
                    # Calculate viewport coordinates (adjusted for scroll)
                    viewport_x = element['position']['viewport']['x']
                    viewport_y = element['position']['viewport']['y']
                    
                    # Document coordinates
                    doc_x = element['position']['document']['x']
                    doc_y = element['position']['document']['y']
                    
                    # Calculate adjusted click position (crucial for elements that were outside viewport)
                    # For elements that were outside viewport, we need to calculate new viewport coordinates
                    # after scrolling
                    if not element['isInViewport']:
                        click_x = doc_x - scroll_left
                        click_y = doc_y - scroll_top
                        print(f"Using scroll-adjusted coordinates: ({click_x}, {click_y})")
                    else:
                        click_x = viewport_x
                        click_y = viewport_y
                        print(f"Using viewport coordinates: ({click_x}, {click_y})")
                    
                    # Perform the click
                    try:
                        self.page.mouse.click(click_x, click_y)
                        print(f"Clicked by position at ({click_x}, {click_y})")
                        
                        # Handle input if needed
                        if action == 'input' and input_value:
                            self.page.keyboard.type(input_value)
                            print(f"Typed text: {input_value}")
                        
                        # Wait for navigation or network idle
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception as e:
                            print(f"Network idle timeout (normal if no navigation occurred): {e}")
                        
                        action_success = True
                    except Exception as e:
                        print(f"Error clicking by position: {e}")
                
        except Exception as e:
            print(f"Error during interaction: {e}")
            # Last resort fallback - try JavaScript click
            try:
                print("Trying JavaScript click as fallback")
                js_click_result = self.page.evaluate(f"""
                () => {{
                    try {{
                        const elements = document.querySelectorAll('*');
                        const el = elements[{element_index}];
                        if (!el) return false;
                        
                        // First try direct event to bypass overlay issues
                        const clickEvent = new MouseEvent('click', {{
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }});
                        
                        const clickResult = el.dispatchEvent(clickEvent);
                        
                        // If element has an onclick attribute, try to execute it directly
                        if (el.hasAttribute('onclick')) {{
                            const onClickFn = new Function(el.getAttribute('onclick'));
                            onClickFn.call(el);
                        }}
                        
                        // If none of the above worked, try a direct click
                        setTimeout(() => el.click(), 10);
                        
                        return true;
                    }} catch (err) {{
                        return false;
                    }}
                }}
                """)
                
                if js_click_result:
                    print("JavaScript click successful")
                    if action == 'input' and input_value:
                        self.page.keyboard.type(input_value)
                        print(f"Typed text: {input_value}")
                    
                    try:
                        self.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception as e:
                        print(f"Network idle timeout (normal if no navigation occurred): {e}")
                    
                    action_success = True
                else:
                    print("JavaScript click failed")
            except Exception as e_js:
                print(f"JavaScript click error: {e_js}")
        
        # After the action, check if there were any page changes, especially error messages
        time.sleep(1.5)  # Give time for any DOM updates to complete
        
        # Capture the new page state
        post_action_state = self.page.evaluate("""() => {
            return {
                url: window.location.href,
                title: document.title,
                textContent: document.body.innerText.substring(0, 1000)
            };
        }""")
        
        # Only check for changes if the action seemed successful
        if action_success:
            # Check for error messages or warnings that appeared after the action
            # This is particularly important when a button like "Add to Cart" is clicked
            # without required options being selected
            try:
                # Look for error messages that might have appeared
                error_messages = self.page.evaluate("""() => {
                    const errorMessages = [];
                    const errorSelectors = [
                        '.error:visible', '.alert:visible', '.warning:visible',
                        '[role="alert"]', '[aria-live="assertive"]',
                        '.toast:visible', '.message:visible', '.validation-message:visible'
                    ];
                    
                    for (const selector of errorSelectors) {
                        document.querySelectorAll(selector).forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                const text = el.innerText.trim();
                                if (text) {
                                    errorMessages.push(text);
                                }
                            }
                        });
                    }
                    
                    // Also check for text containing common error terms
                    const errorTerms = [
                        'please select', 'must select', 'required', 'select a', 
                        'choose a', 'error', 'invalid', 'failed'
                    ];
                    
                    document.querySelectorAll('p, div, span').forEach(el => {
                        const text = el.innerText.trim();
                        if (text && errorTerms.some(term => text.toLowerCase().includes(term))) {
                            const style = window.getComputedStyle(el);
                            if (style.display !== 'none' && style.visibility !== 'hidden') {
                                if (!errorMessages.includes(text)) {
                                    errorMessages.push(text);
                                }
                            }
                        }
                    });
                    
                    return errorMessages;
                }""")
                
                if error_messages and len(error_messages) > 0:
                    print("\nDetected error messages after action:")
                    for msg in error_messages:
                        print(f"- {msg}")
                    
                    # If there's an error message and the action was a button click,
                    # it likely means we need to make selections first
                    if action == 'click' and element.get('tagName') == 'button':
                        print("\nWARNING: Error messages appeared after clicking a button.")
                        print("This often means required options (like size or color) need to be selected first.")
                        
                        # Check what options need to be selected
                        required_options = self.page.evaluate("""() => {
                            const requiredOptions = [];
                            
                            // Common selectors for option groups that need selection
                            const optionGroups = document.querySelectorAll(
                                '.swatch-group, .size-selector, .color-selector, .product-options'
                            );
                            
                            for (const group of optionGroups) {
                                // Try to get the option type (e.g., "Size", "Color")
                                let optionType = '';
                                const label = group.querySelector('label, .option-label, .swatch-label');
                                if (label) {
                                    optionType = label.innerText.trim();
                                } else if (group.className.includes('size')) {
                                    optionType = 'Size';
                                } else if (group.className.includes('color')) {
                                    optionType = 'Color';
                                } else if (group.className.includes('fit')) {
                                    optionType = 'Fit';
                                } else if (group.className.includes('waist')) {
                                    optionType = 'Waist';
                                } else if (group.className.includes('length')) {
                                    optionType = 'Length';
                                } else {
                                    optionType = 'Option';
                                }
                                
                                // Check if any option in this group is selected
                                const options = group.querySelectorAll(
                                    'input[type="radio"], button, .swatch, .option, [role="radio"]'
                                );
                                let hasSelection = false;
                                
                                for (const option of options) {
                                    if (option.checked || option.classList.contains('selected') || 
                                        option.classList.contains('active') || 
                                        option.getAttribute('aria-selected') === 'true') {
                                        hasSelection = true;
                                        break;
                                    }
                                }
                                
                                if (!hasSelection && options.length > 0) {
                                    requiredOptions.push(optionType);
                                }
                            }
                            
                            return requiredOptions;
                        }""")
                        
                        if required_options and len(required_options) > 0:
                            print(f"Required options that need to be selected: {', '.join(required_options)}")
                
                    # Store information about required selections in history
                    selection_info = {
                        "url": post_action_state.get("url"),
                        "timestamp": time.time(),
                        "error_messages": error_messages,
                        "required_selections": required_options if required_options else []
                    }
                    self._track_interaction("required_selections", selection_info)
            except Exception as e:
                print(f"Error checking for post-action messages: {e}")
        
        # Check if the action caused a page navigation
        url_changed = pre_action_state.get("url") != post_action_state.get("url")
        if url_changed:
            print(f"Page navigation occurred: {pre_action_state.get('url')} -> {post_action_state.get('url')}")
        
        return action_success
    
    def complete_task(self, task: str, website: str, max_steps: int = 10) -> None:
        """Complete a specified task on a website with a maximum number of steps"""
        print(f"\n=== Starting task: {task} on {website} ===\n")
        
        # Initialize task context
        task_context = {
            "task": task,
            "website": website,
            "steps_taken": [],
            "progress": "not_started"
        }
        
        # Track this task in history
        self._track_interaction("task_start", {"task": task, "website": website})
        
        # Navigate to the website
        self.navigate_to(website)
        
        # Perform steps until task is complete or max steps reached
        for step in range(1, max_steps + 1):
            print(f"\n--- Step {step}/{max_steps} ---")
            
            try:
                # Get webpage summary first for better context
                webpage_summary = None
                try:
                    webpage_summary = self.get_webpage_summary()
                    print(f"Page type identified as: {webpage_summary.get('page_type', 'unknown')}")
                    print(f"Page purpose: {webpage_summary.get('main_purpose', '')}")
                    
                    # Add to task context
                    task_context["current_page"] = {
                        "url": self.page.url,
                        "title": self.page.evaluate("document.title"),
                        "type": webpage_summary.get("page_type", "unknown"),
                        "summary": webpage_summary.get("summary", ""),
                        "actions": webpage_summary.get("available_actions", [])
                    }
                    
                    # Check for error messages or warnings in the summary
                    if webpage_summary.get("error_warnings"):
                        print("\nDetected error messages or warnings:")
                        for error in webpage_summary.get("error_warnings"):
                            print(f"- {error}")
                except Exception as e:
                    print(f"Error getting webpage summary: {e}")
                    # Continue without webpage summary
                
                # Check for page changes from previous action, especially for error messages
                # This is particularly useful after clicking "Add to Cart" without selecting options
                page_changes = None
                try:
                    # Only check for changes if we've performed at least one action
                    if step > 1 or len(task_context.get("steps_taken", [])) > 0:
                        page_changes = self.get_page_changes()
                        
                        if page_changes.get("has_changes"):
                            print("\n=== Page Changes Detected ===")
                            print(f"Change summary: {page_changes.get('change_summary', '')}")
                            
                            # Display any error messages
                            if page_changes.get("error_messages"):
                                print("\nError messages:")
                                for error in page_changes.get("error_messages"):
                                    print(f"- {error}")
                            
                            # Track the current state for future comparisons
                            self._track_interaction("page_state", detailed_state)
                            
                            # Now analyze the changes using Cohere
                            error_messages = detailed_state.get("errorMessages", [])
                            required_selections = detailed_state.get("requiredSelections", [])
                            
                            # Format the required selections for the prompt
                            required_selections_text = ""
                            if required_selections:
                                required_selections_text = "Required selections that haven't been made:\n"
                                for selection in required_selections:
                                    required_selections_text += f"- {selection.get('type', 'option')} needs to be selected from: "
                                    options = selection.get('options', [])
                                    option_texts = [opt.get('text', 'option') for opt in options]
                                    required_selections_text += f"{', '.join(option_texts[:5])}\n"
                            
                            # Format the error messages for the prompt
                            error_messages_text = ""
                            if error_messages:
                                error_messages_text = "Error messages or warnings detected:\n"
                                for error in error_messages:
                                    error_messages_text += f"- {error.get('text', '')}\n"
                            
                            # Only use Cohere if there are significant changes to analyze
                            if error_messages or required_selections:
                                # Prepare a prompt for Cohere to analyze the changes
                                prompt = f"""You are an AI assistant helping to analyze changes on a webpage after a user interaction.

Previous page URL: {previous_page_state.get("url", "Unknown")}
Current page URL: {detailed_state.get("url", "Unknown")}

{error_messages_text}
{required_selections_text}

Based on the above information, analyze what has changed on the page and why. 
Focus particularly on:
1. Any error messages or warnings that appeared
2. Any required selections that need to be made before proceeding
3. The likely reason for these changes (e.g., "Add to Cart failed because size wasn't selected")

Format your response as a JSON with the following fields:
- has_changes: true
- change_summary: A concise 1-2 sentence description of what changed and why
- error_messages: Array of error message texts found
- required_selections: Array of selections that need to be made (e.g., ["Size", "Color"])
- recommended_action: What the user should do next to proceed

IMPORTANT: Your response should be valid JSON and nothing else. No explanations before or after.
"""

                                try:
                                    # Call Cohere to analyze the changes
                                    response = self.co.generate(
                                        prompt=prompt,
                                        max_tokens=300,
                                        temperature=0.2,
                                        p=0.7,
                                        frequency_penalty=0,
                                        presence_penalty=0,
                                        return_likelihoods='NONE',
                                        truncate="START"
                                    )
                                    changes_text = response.generations[0].text.strip()
                                    
                                    # Parse the JSON response
                                    try:
                                        changes = json.loads(changes_text)
                                        # Add URLs for reference
                                        changes["current_url"] = detailed_state.get("url")
                                        changes["previous_url"] = previous_page_state.get("url")
                                        return changes
                                    except json.JSONDecodeError:
                                        print("Error parsing Cohere's response as JSON for page changes.")
                                        # Create a simple version based on the raw data
                                        return {
                                            "has_changes": bool(error_messages or required_selections),
                                            "change_summary": "Changes detected but couldn't parse structured data",
                                            "error_messages": [msg.get("text", "") for msg in error_messages],
                                            "required_selections": [sel.get("type", "option") for sel in required_selections],
                                            "recommended_action": "Review errors and make required selections",
                                            "current_url": detailed_state.get("url"),
                                            "previous_url": previous_page_state.get("url")
                                        }
                                except Exception as e:
                                    print(f"Error analyzing page changes: {e}")
                            
                            # If no significant changes or Cohere analysis failed, return a simple result
                            return {
                                "has_changes": bool(error_messages or required_selections),
                                "change_summary": "Page changed after interaction",
                                "error_messages": [msg.get("text", "") for msg in error_messages],
                                "required_selections": [sel.get("type", "option") for sel in required_selections],
                                "recommended_action": "Continue with task",
                                "current_url": detailed_state.get("url"),
                                "previous_url": previous_page_state.get("url")
                            }
                except Exception as e:
                    print(f"Error during step {step}: {e}")
                    continue
            except Exception as e:
                print(f"Error during step {step}: {e}")
                continue
        
        # Track the final state for future comparisons
        self._track_interaction("task_end", {"task": task, "website": website})
    
    def _track_interaction(self, interaction_type: str, data: Dict[str, Any]) -> None:
        """Track user interactions to prevent repetitive actions"""
        history_entry = {
            "type": interaction_type,
            "data": data,
            "timestamp": time.time(),
            "url": self.page.url
        }
        
        self.chat_history.append(history_entry)
        
        # Limit history size
        if len(self.chat_history) > 50:
            self.chat_history = self.chat_history[-50:]
    
    def has_recent_interaction(self, interaction_type: str, data: Dict[str, Any], 
                              time_window: int = 60) -> bool:
        """
        Check if a similar interaction was performed recently
        
        Args:
            interaction_type: Type of interaction to check
            data: Data describing the interaction
            time_window: Time window in seconds to consider "recent"
            
        Returns:
            True if a similar interaction was performed recently
        """
        current_time = time.time()
        current_url = self.page.url
        
        for entry in reversed(self.chat_history):
            # Only check entries of the specified type
            if entry.get("type") != interaction_type:
                continue
                
            # Check if entry is recent enough
            if current_time - entry.get("timestamp", 0) > time_window:
                continue
                
            # For element interactions, check if it's similar
            if interaction_type == "element_interaction":
                if entry.get("url") == current_url:
                    entry_element = entry.get("data", {}).get("element", {})
                    current_element = data.get("element", {})
                    
                    # Check if interacting with same element
                    if (entry_element.get("elementIndex") == current_element.get("elementIndex") or
                        entry_element.get("xpath") == current_element.get("xpath") or
                        (entry_element.get("description") == current_element.get("description") and 
                         entry_element.get("tagName") == current_element.get("tagName"))):
                        return True
            
            # For other types, check if data is similar
            else:
                if entry.get("data") == data:
                    return True
                    
        return False


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Web Task Automation")
    parser.add_argument("--llama", action="store_true", help="Use Llama API instead of Cohere")
    parser.add_argument("--task", type=str, default="Add a men's jeans to cart on gap.com", 
                        help="Task to execute (default: Add a men's jeans to cart on gap.com)")
    parser.add_argument("--website", type=str, default="https://www.gap.com",
                        help="Website URL (default: https://www.gap.com)")
    args = parser.parse_args()
    
    # Example usage
    automator = None
    
    try:
        # Create automator instance with selected LLM
        automator = TaskAutomator(use_llama=args.llama)
        
        # Task and website from args
        task = args.task
        website = args.website
        
        print(f"\n=== Starting task: {task} ===")
        
        # Execute the task
        automator.complete_task(task, website)
        
    except KeyboardInterrupt:
        print("\n\nTask execution interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Clean up
        if automator:
            try:
                automator.close()
            except Exception as e:
                print(f"Error during cleanup: {e}")
        print("Execution finished.")


if __name__ == "__main__":
    main() 