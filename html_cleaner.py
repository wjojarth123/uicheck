import re
import os
from bs4 import BeautifulSoup, Comment

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


def clean_html_tags(input_file, output_file=None):
    """
    Cleans HTML by removing script, style, link, meta tags, and comments.
    For non-interactive elements, all attributes are stripped, leaving raw tags and text.
    For elements marked as interactive (by a 'data-interactive-id' attribute 
    set prior to calling this function), it keeps the 'name' attribute and replaces 
    others with a 'data-unique-id' attribute.
    
    Args:
        input_file (str): Path to the input HTML file
        output_file (str, optional): Path to the output file. If None, creates a file with "_cleaned" suffix
    
    Returns:
        str: Path to the output file or None if an error occurs
    """
    if not output_file:
        filename, ext = os.path.splitext(input_file)
        output_file = f"{filename}_cleaned{ext}"
    
    try:
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        cleaned_content = clean_html_string(content)
        
        if cleaned_content is not None:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            return output_file
        else:
            return None
    
    except Exception as e:
        print(f"Error in clean_html_tags: {e}")
        return None

def clean_html_string(html_content):
    """
    Cleans an HTML string based on the new system:
    - Removes script, style, link, meta tags, and comments.
    - For elements with 'data-interactive-id': keeps 'name' attribute, adds 'data-unique-id',
      preserves text. This 'data-interactive-id' must be set by an upstream process.
    - For other elements: strips all attributes, preserves tag and text.
    
    Args:
        html_content (str): HTML content as string
    
    Returns:
        str: Cleaned HTML content or None if an error occurs
    """
    if not html_content:
        return ""  # Return empty string for empty input
        
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, link, and meta tags completely
        for s_tag in soup.find_all(['script', 'style', 'link', 'meta']):
            s_tag.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # Process all remaining tags
        for tag in soup.find_all(True):
            interactive_id = tag.get('data-interactive-id')
            
            if interactive_id:
                # This is an interactive element, marked by human.py
                name_attr = tag.get('name')
                
                # Clear all current attributes first
                tag.attrs = {}
                
                # Set the new permanent unique ID
                tag['data-unique-id'] = interactive_id
                
                # Restore name attribute if it existed
                if name_attr:
                    tag['name'] = name_attr
                
                # Text content is implicitly kept. If tag.string is None but it has children,
                # their text will be preserved. get_text() consolidates all text.
            else:
                # Non-interactive element: strip all attributes
                tag.attrs = {}
                
        return str(soup)
    
    except Exception as e:
        print(f"Error in clean_html_string: {e}")
        return None

async def extract_interactive_elements(html_content):
    """
    Extracts interactive elements from HTML content.

    Args:
        html_content (str): HTML content as a string.

    Returns:
        tuple: A tuple containing:
            - elements_dict (dict): A dictionary of interactive elements.
            - cleaned_html (str): The cleaned HTML content.
    """
    elements_dict = {}
    cleaned_html = ""  # Placeholder for now
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Combined selector for all potentially interactive elements.
        # We will filter for visibility and specific types in the Python loop.
        combined_selector = (
            'button, input[type="submit"], input[type="button"], input[type="text"], '
            'input[type="email"], input[type="password"], input[type="search"], '
            'input[type="tel"], input[type="url"], input[type="number"], '
            'input[type="checkbox"], input[type="radio"], '
            'textarea, select, a, '
            'div[role="button"], div[role="link"], div[onclick], div[data-identifier]'
        )

        candidate_elements = soup.select(combined_selector)

        for element in candidate_elements:
            try:
                # Convert the BeautifulSoup element back to a string for Playwright to handle
                element_string = str(element)
                # Query the element using BeautifulSoup
                found_element = soup.select_one(element_string)

                if found_element is None:
                    continue

                # Common attributes
                tag_name = element.name.lower()
                xpath = "test" # Placeholder

                # If XPath is somehow null or empty, skip (should be rare)
                if not xpath:
                    continue

                text_content = (element.text or "").strip()
                class_name = element.get("class") or ""
                aria_label = element.get("aria-label") or ""

                element_type = ""
                # Stores type-specific attributes like 'name', 'placeholder', 'href', 'text'
                specific_details = {}
                # Text used for generating the unique ID (e.g., placeholder, name, actual text)
                id_generation_text_source = text_content

                # Determine element type and gather specific details
                if tag_name == "button":
                    element_type = "button"
                    specific_details = {"text": text_content, "tag_name": tag_name}
                elif tag_name == "input":
                    input_type = (element.get("type") or "text").lower()
                    if input_type in ["submit", "button"]:
                        element_type = input_type
                        value_attr = element.get("value") or ""
                        # For input buttons, text_content might be empty, value_attr is better
                        displayed_text = text_content or value_attr
                        id_generation_text_source = displayed_text
                        specific_details = {"text": displayed_text, "tag_name": tag_name}
                    elif input_type in ["text", "email", "password", "search", "tel", "url", "number"]:
                        element_type = input_type
                        name_attr = element.get("name") or ""
                        placeholder_attr = element.get("placeholder") or ""
                        id_generation_text_source = placeholder_attr or name_attr or aria_label  # Fallback for ID text
                        specific_details = {"name": name_attr, "placeholder": placeholder_attr}
                    elif input_type in ["checkbox", "radio"]:
                        element_type = input_type
                        name_attr = element.get("name") or ""
                        id_generation_text_source = name_attr or aria_label  # Fallback for ID text
                        specific_details = {"name": name_attr}
                    else:
                        continue  # Skip other input types not explicitly handled
                elif tag_name == "a":
                    element_type = "link"
                    href_attr = element.get("href") or ""
                    specific_details = {"text": text_content, "href": href_attr}
                elif tag_name == "textarea":
                    element_type = "textarea"
                    name_attr = element.get("name") or ""
                    placeholder_attr = element.get("placeholder") or ""
                    id_generation_text_source = placeholder_attr or name_attr or aria_label
                    specific_details = {"name": name_attr, "placeholder": placeholder_attr}
                elif tag_name == "select":
                    element_type = "select"
                    name_attr = element.get("name") or ""
                    id_generation_text_source = name_attr or aria_label
                    specific_details = {"name": name_attr}
                elif tag_name == "div":
                    role_attr = element.get("role") or ""
                    onclick_attr = element.get("onclick")  # Check if onclick exists
                    data_identifier_attr = element.get("data-identifier") or ""

                    if role_attr == "button":
                        element_type = "button"
                        specific_details = {"text": text_content, "role": role_attr}
                    elif role_attr == "link":
                        element_type = "link"
                        specific_details = {"text": text_content, "role": role_attr}
                    elif onclick_attr or data_identifier_attr:
                        element_type = "interactive"  # General interactive div
                        id_generation_text_source = text_content or data_identifier_attr or aria_label
                        specific_details = {"text": text_content, "role": role_attr, "data_identifier": data_identifier_attr}
                    else:
                        continue
                else:
                    continue  # Tag not explicitly handled

                if not element_type:
                    continue

                unique_id = generate_unique_id(element_type, xpath, id_generation_text_source, class_name, aria_label)

                # Ensure unique_id is not already taken (e.g. if somehow two elements generate same ID)
                # This is a safeguard, usually generate_unique_id with XPath hash should be quite unique.
                temp_id = unique_id
                counter = 0
                while temp_id in elements_dict:
                    counter += 1
                    temp_id = f"{unique_id}_{counter}"
                unique_id = temp_id

                base_info = {
                    "element_type": element_type,
                    "xpath": xpath,
                    "class_name": class_name,
                    "aria_label": aria_label
                }
                # Add tag_name for buttons/inputs for potential compatibility or detailed info
                if "tag_name" not in specific_details and tag_name in ["button", "input"]:
                    specific_details["tag_name"] = tag_name

                # Add the data-interactive-id attribute to the element
                # await element.evaluate('el => el.setAttribute("data-interactive-id", "' + unique_id + '")')

                elements_dict[unique_id] = {**base_info, **specific_details}

            except Exception as elem_err:
                # Log error and continue with the next element
                print(f"DEBUG (HumanBrowser): Error processing a candidate element: {elem_err}")
                continue

        cleaned_html = clean_html_string(html_content)

    except Exception as e:
        print(f"ERROR in extract_interactive_elements: {e}")

    return elements_dict, cleaned_html
