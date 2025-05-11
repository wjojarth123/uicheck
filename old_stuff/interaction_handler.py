"""
Interaction Handler for Web Explorer
-----------------------------------
This module handles interactions with various web elements
"""

import asyncio
from typing import Dict, List, Optional, Any
import random
import re

from playwright.async_api import Page, ElementHandle

# Debug flag
DEBUG = True

class InteractionHandler:
    """Handles interactions with various web elements"""
    
    @staticmethod
    async def analyze_form_elements(page: Page) -> List[Dict[str, Any]]:
        """Find and analyze form elements on the page"""
        form_elements = []
        
        try:
            # Find all form input elements
            elements = await page.query_selector_all(
                'input:not([type="hidden"]), textarea, select, [role="textbox"], [contenteditable="true"], [role="checkbox"], [role="radio"], [role="switch"], [role="slider"], [role="combobox"]'
            )
            
            for element in elements:
                try:
                    # Get element properties
                    tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                    element_type = await element.get_attribute('type') or ''
                    role = await element.get_attribute('role') or ''
                    name = await element.get_attribute('name') or ''
                    placeholder = await element.get_attribute('placeholder') or ''
                    label_text = await InteractionHandler._get_element_label(element, page)
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    
                    # Only include visible and enabled elements
                    if is_visible and is_enabled:
                        element_info = {
                            'tag': tag_name,
                            'type': element_type,
                            'role': role,
                            'name': name,
                            'label': label_text,
                            'placeholder': placeholder,
                            'element': element,  # Keep reference to actual element
                            'interacted': False  # Track if we've interacted with this element
                        }
                        form_elements.append(element_info)
                        
                        if DEBUG:
                            print(f"Found form element: {tag_name} - {element_type or role} - {label_text or name or placeholder}")
                
                except Exception as e:
                    if DEBUG:
                        print(f"Error analyzing form element: {str(e)}")
        
        except Exception as e:
            if DEBUG:
                print(f"Error finding form elements: {str(e)}")
        
        return form_elements
    
    @staticmethod
    async def _get_element_label(element: ElementHandle, page: Page) -> str:
        """Get the label text for an element"""
        label_text = ""
        
        try:
            # Check for id attribute
            element_id = await element.get_attribute('id')
            if element_id:
                # Find label with for=element_id
                label = await page.query_selector(f'label[for="{element_id}"]')
                if label:
                    label_text = await label.text_content() or ""
                    return label_text.strip()
            
            # Check if element is wrapped in a label
            parent_label = await element.evaluate('''
                el => {
                    let parent = el.parentElement;
                    while (parent) {
                        if (parent.tagName === 'LABEL') {
                            return parent.textContent;
                        }
                        parent = parent.parentElement;
                    }
                    return null;
                }
            ''')
            
            if parent_label:
                return parent_label.strip()
            
            # Check for aria-label attribute
            aria_label = await element.get_attribute('aria-label')
            if aria_label:
                return aria_label.strip()
            
            # Check for aria-labelledby attribute
            aria_labelledby = await element.get_attribute('aria-labelledby')
            if aria_labelledby:
                label_elem = await page.query_selector(f'#{aria_labelledby}')
                if label_elem:
                    label_text = await label_elem.text_content() or ""
                    return label_text.strip()
                    
        except Exception as e:
            if DEBUG:
                print(f"Error getting element label: {str(e)}")
        
        return label_text.strip()
    
    @staticmethod
    async def interact_with_form_elements(page: Page, form_elements: List[Dict], cohere_client: Any) -> Dict:
        """Interact with form elements based on AI decisions"""
        interactions = {}
        
        if not form_elements:
            return interactions
        
        # Create descriptions of form elements for Cohere
        element_descriptions = []
        for i, elem in enumerate(form_elements):
            label = elem['label'] or elem['name'] or elem['placeholder'] or f"Unnamed {elem['tag']} {elem['type']}"
            element_descriptions.append(f"{i+1}. {label} ({elem['tag']} - {elem['type'] or elem['role']})")
        
        # Join the descriptions with newlines
        descriptions_text = '\n'.join(element_descriptions)
        
        # Ask Cohere what to do with these elements - use regular string, not f-string to avoid backslash issues
        prompt = """
        You are an AI web assistant tasked with exploring a website.
        
        You've encountered a form with the following elements:
        
        """ + descriptions_text + """
        
        What values should I enter into these fields? For each element, provide:
        1. Which element to interact with (by number)
        2. What value to enter or action to take
        3. Brief reasoning for your decision
        
        Format your response as JSON like this:
        {
            "interactions": [
                {
                    "element_number": 1,
                    "value": "example input text",
                    "reasoning": "This appears to be a search box so I'm searching for relevant content"
                },
                {
                    "element_number": 2,
                    "value": "click",
                    "reasoning": "This is a toggle button that should be turned on"
                }
            ]
        }
        
        For text inputs, provide text to enter.
        For checkboxes, toggles, and radio buttons, just say "click".
        For select dropdowns, provide a value to select (or "click" if unsure).
        Only interact with elements that make sense for exploring the website.
        """
        
        if DEBUG:
            print("Asking Cohere for form interaction instructions")
            
        try:
            response = cohere_client.chat(
                message=prompt,
                model="command-r", 
                temperature=0.7
            )
            
            # Extract the JSON response
            response_text = response.text
            json_match = re.search(r'({.*})', response_text, re.DOTALL)
            
            if json_match:
                try:
                    import json
                    decision = json.loads(json_match.group(1))
                    interaction_instructions = decision.get("interactions", [])
                    
                    if DEBUG:
                        print(f"Received {len(interaction_instructions)} interaction instructions from Cohere")
                    
                    # Process each interaction
                    for instruction in interaction_instructions:
                        element_number = instruction.get("element_number")
                        value = instruction.get("value")
                        reasoning = instruction.get("reasoning", "No reasoning provided")
                        
                        if element_number and element_number <= len(form_elements) and value:
                            elem_index = element_number - 1  # Convert to 0-indexed
                            element_info = form_elements[elem_index]
                            element = element_info['element']
                            tag = element_info['tag']
                            elem_type = element_info['type']
                            elem_name = element_info['name'] or element_info['label'] or element_info['placeholder']
                            
                            # Perform the interaction
                            if tag == 'input' and elem_type in ['text', 'email', 'password', 'search', 'tel', 'url', 'number'] or tag == 'textarea':
                                if value != "click":
                                    await element.fill(value)
                                    if DEBUG:
                                        print(f"Filled {elem_name} with '{value}': {reasoning}")
                                    interactions[elem_name] = {'value': value, 'reasoning': reasoning}
                                    element_info['interacted'] = True
                            
                            elif tag == 'input' and elem_type in ['checkbox', 'radio'] or elem_type == '' and element_info['role'] in ['checkbox', 'radio', 'switch']:
                                # Use safe click
                                await InteractionHandler.safe_click(element, page)
                                if DEBUG:
                                    print(f"Clicked {elem_name}: {reasoning}")
                                interactions[elem_name] = {'value': 'click', 'reasoning': reasoning}
                                element_info['interacted'] = True
                            
                            elif tag == 'select' or element_info['role'] == 'combobox':
                                try:
                                    # Try to select the value if it's not just "click"
                                    if value != "click":
                                        await element.select_option(value=value)
                                    else:
                                        # If it's "click", just click to open the dropdown
                                        await InteractionHandler.safe_click(element, page)
                                        # Wait briefly
                                        await asyncio.sleep(0.5)
                                        # Try to select the first option
                                        await page.keyboard.press('ArrowDown')
                                        await page.keyboard.press('Enter')
                                    
                                    if DEBUG:
                                        print(f"Interacted with select/combobox {elem_name}: {reasoning}")
                                    interactions[elem_name] = {'value': value, 'reasoning': reasoning}
                                    element_info['interacted'] = True
                                except Exception as e:
                                    if DEBUG:
                                        print(f"Error interacting with select/combobox: {str(e)}")
                            
                            else:
                                # Generic click for any other element
                                await InteractionHandler.safe_click(element, page)
                                if DEBUG:
                                    print(f"Clicked unknown element type {elem_name}: {reasoning}")
                                interactions[elem_name] = {'value': 'click', 'reasoning': reasoning}
                                element_info['interacted'] = True
                    
                except Exception as e:
                    if DEBUG:
                        print(f"Error processing interaction instructions: {str(e)}")
            
        except Exception as e:
            if DEBUG:
                print(f"Error getting Cohere response for form interactions: {str(e)}")
        
        # If Cohere failed to give instructions, perform default actions for important elements
        if not interactions and form_elements:
            if DEBUG:
                print("No specific instructions from Cohere, using default interactions")
            
            default_interactions = await InteractionHandler.default_interactions(page, form_elements)
            interactions.update(default_interactions)
        
        return interactions
    
    @staticmethod
    async def default_interactions(page: Page, form_elements: List[Dict]) -> Dict:
        """Perform default interactions with important elements when Cohere doesn't provide instructions"""
        interactions = {}
        
        # Process search boxes
        search_boxes = [elem for elem in form_elements 
                        if not elem['interacted'] and elem['tag'] in ['input'] 
                        and (elem['type'] == 'search' or 'search' in (elem['name'] or '').lower() or 'search' in (elem['label'] or '').lower())]
        
        for elem in search_boxes:
            try:
                search_terms = ["features", "help", "tutorial", "documentation", "about"]
                term = random.choice(search_terms)
                await elem['element'].fill(term)
                
                if DEBUG:
                    print(f"Default action: Filled search box {elem['label'] or elem['name']} with '{term}'")
                
                interactions[elem['label'] or elem['name'] or 'search'] = {'value': term, 'reasoning': 'Default search action'}
                elem['interacted'] = True
                
                # Submit search by pressing Enter
                await page.keyboard.press('Enter')
                await asyncio.sleep(1)  # Wait for results
            except Exception as e:
                if DEBUG:
                    print(f"Error with default search action: {str(e)}")
        
        # Click a submit button if there's one
        submit_buttons = await page.query_selector_all('button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Search")')
        
        if submit_buttons:
            try:
                button = submit_buttons[0]
                btn_text = await button.text_content() or "Submit button"
                
                # Use safe click
                await InteractionHandler.safe_click(button, page)
                
                interactions[btn_text.strip()] = {'value': 'click', 'reasoning': 'Default submit action'}
                
                if DEBUG:
                    print(f"Default action: Clicked submit button: {btn_text.strip()}")
                
                await asyncio.sleep(1.5)  # Wait longer for submission
            except Exception as e:
                if DEBUG:
                    print(f"Error with default submit action: {str(e)}")
        
        return interactions
    
    @staticmethod
    async def find_and_interact_with_ui_patterns(page: Page) -> List[Dict]:
        """Find and interact with common UI patterns"""
        interactions = []
        
        ui_patterns = [
            # Tabs
            {'selector': '[role="tab"]', 'description': 'tab', 'max_clicks': 3},
            {'selector': '.tabs button, .tab-button, .tab', 'description': 'tab', 'max_clicks': 3},
            
            # Accordions
            {'selector': '[aria-expanded="false"]', 'description': 'accordion', 'max_clicks': 3},
            {'selector': '.accordion-header, .accordion-button', 'description': 'accordion', 'max_clicks': 3},
            
            # Modals/Dialogs
            {'selector': '[data-toggle="modal"], [data-bs-toggle="modal"]', 'description': 'modal trigger', 'max_clicks': 1},
            {'selector': 'button.modal-trigger', 'description': 'modal trigger', 'max_clicks': 1},
            
            # Navigation toggles
            {'selector': '.navbar-toggler, .menu-toggle', 'description': 'navigation toggle', 'max_clicks': 1},
            
            # Sliders
            {'selector': 'input[type="range"], [role="slider"]', 'description': 'slider', 'max_clicks': 1},
            
            # Popover triggers
            {'selector': '[data-toggle="popover"], [data-bs-toggle="popover"]', 'description': 'popover', 'max_clicks': 2},
        ]
        
        for pattern in ui_patterns:
            try:
                elements = await page.query_selector_all(pattern['selector'])
                
                # Limit to visible elements and maximum clicks
                visible_elements = []
                for element in elements:
                    try:
                        if await element.is_visible():
                            visible_elements.append(element)
                    except Exception:
                        # Skip elements with visibility errors
                        continue
                
                if DEBUG and visible_elements:
                    print(f"Found {len(visible_elements)} {pattern['description']} elements")
                
                # Click up to max_clicks elements of this type
                for element in visible_elements[:pattern['max_clicks']]:
                    try:
                        text = await element.text_content() or f"{pattern['description']} element"
                        if DEBUG:
                            print(f"Clicking element: {text.strip()}")
                        
                        # Add safe click with retry
                        await InteractionHandler.safe_click(element, page)
                        await asyncio.sleep(1.0)  # Wait longer for UI to update
                        
                        interactions.append({
                            'element_type': pattern['description'],
                            'text': text.strip(),
                            'action': 'click'
                        })
                    except Exception as e:
                        if DEBUG:
                            print(f"Error clicking {pattern['description']}: {str(e)}")
            
            except Exception as e:
                if DEBUG:
                    print(f"Error finding {pattern['description']} elements: {str(e)}")
        
        return interactions
    
    @staticmethod
    async def safe_click(element, page, max_retries=3):
        """Try to click an element safely with multiple approaches"""
        for attempt in range(max_retries):
            try:
                # Scroll element into view first
                await element.scroll_into_view_if_needed()
                
                # Wait a bit for the page to stabilize
                await asyncio.sleep(0.5)
                
                # Try direct click first
                try:
                    await element.click(timeout=5000, force=False)
                    return
                except Exception:
                    if DEBUG and attempt > 0:
                        print(f"Direct click failed on attempt {attempt+1}, trying alternatives...")
                
                # Try forced click to bypass overlay elements
                try:
                    await element.click(force=True, timeout=5000)
                    return
                except Exception:
                    pass
                
                # If direct click failed, try clicking by JavaScript
                try:
                    await page.evaluate("(element) => element.click()", element)
                    return
                except Exception:
                    pass
                
                # If that also failed, try clicking by position
                box = await element.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    
                    try:
                        await page.mouse.click(x, y)
                        return
                    except Exception:
                        pass
                    
                    # Try a forced mouse click as a last resort
                    try:
                        await page.mouse.click(x, y, {force: True})
                        return
                    except Exception:
                        pass
                
                # Wait longer before next attempt
                await asyncio.sleep(1.0)
            
            except Exception as e:
                if DEBUG:
                    print(f"Click attempt {attempt+1} failed: {str(e)}")
                
                # Wait before retrying
                await asyncio.sleep(1.0)
        
        # If we get here, all attempts failed
        raise Exception(f"Failed to click element after {max_retries} attempts") 