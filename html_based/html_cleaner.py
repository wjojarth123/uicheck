import re
import os
import hashlib
import string
import random
from bs4 import BeautifulSoup, Comment

def generate_xpath(element):
    """
    Generate an XPath for an element.
    """
    components = []
    child = element
    
    # Traverse up the tree and collect path information
    while child.parent:
        siblings = child.parent.find_all(child.name, recursive=False)
        if len(siblings) > 1:
            # If there are multiple siblings with the same tag, add index
            sibling_index = siblings.index(child) + 1
            components.insert(0, f"{child.name}[{sibling_index}]")
        else:
            components.insert(0, child.name)
        child = child.parent
        
        # Stop at body or html to keep XPath manageable
        if child.name in ['body', 'html']:
            components.insert(0, child.name)
            break
            
    return '/' + '/'.join(components)

def generate_unique_id(element_type, xpath, text="", class_name="", aria_label=""):
    """
    Generate a unique ID for an interactive element based on its characteristics.
    """
    # Generate type prefix
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
    
    # Generate middle part based on text content or attributes
    middle_part_source = ""
    if text and text.strip():
        middle_part_source = text.strip()
    elif class_name and class_name.strip():
        if isinstance(class_name, list):
            middle_part_source = " ".join(class_name).strip().split()[0]
        else:
            middle_part_source = class_name.strip().split()[0]
    elif aria_label and aria_label.strip():
        middle_part_source = aria_label.strip()
    
    if middle_part_source:
        middle_part = ''.join(filter(str.isalnum, middle_part_source))[:3]
    else:
        middle_part = ''.join(random.choices(string.ascii_lowercase, k=3))
    
    middle_part = middle_part.lower().ljust(3, 'x')[:3]
    
    # Generate hash suffix from xpath
    xpath_hash_suffix = hashlib.sha256(xpath.encode()).hexdigest()[:3]
    
    return f"{type_prefix}{middle_part}{xpath_hash_suffix}"


def clean_html_string(html_content):
    """
    Cleans an HTML string:
    - Removes script, style, link, meta tags, and comments.
    - Preserves interact-element-id attributes and other key attributes.
    
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
        for s_tag in soup.find_all(['script', 'style', 'meta']):
            s_tag.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # Process all remaining tags
        for tag in soup.find_all(True):
            attrs_to_keep = {}
            
            # Keep important attributes
            important_attrs = ['name', 'id', 'href', 'interact-element-id']
            for attr in important_attrs:
                if attr in tag.attrs:
                    attrs_to_keep[attr] = tag[attr]
            
            # Keep aria attributes
            for attr, value in tag.attrs.items():
                if attr.startswith('aria-'):
                    attrs_to_keep[attr] = value
            
            # Replace all attributes with only the ones we want to keep
            tag.attrs = attrs_to_keep
            
        return str(soup)

    except Exception as e:
        print(f"Error in clean_html_string: {e}")
        return None

async def extract_interactive_elements(html_content):
    """
    Extracts interactive elements from HTML content and adds unique IDs to them.

    Args:
        html_content (str): HTML content as a string.

    Returns:
        tuple: A tuple containing:
            - elements_dict (dict): A dictionary of interactive elements.
            - cleaned_html (str): The cleaned HTML content with interact-element-id attributes.
    """
    elements_dict = {}
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Combined selector for all potentially interactive elements
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
                # Get tag name and generate xpath
                tag_name = element.name.lower()
                xpath = generate_xpath(element)

                # Get text and attribute values
                text_content = (element.get_text() or "").strip()
                class_name = element.get("class", "")
                aria_label = element.get("aria-label", "")

                element_type = ""
                specific_details = {}
                id_generation_text_source = text_content

                # Determine element type and gather specific details
                if tag_name == "button":
                    element_type = "button"
                    specific_details = {"text": text_content, "tag_name": tag_name}
                elif tag_name == "input":
                    input_type = (element.get("type") or "text").lower()
                    if input_type in ["submit", "button"]:
                        element_type = input_type
                        value_attr = element.get("value", "")
                        displayed_text = text_content or value_attr
                        id_generation_text_source = displayed_text
                        specific_details = {"text": displayed_text, "tag_name": tag_name}
                    elif input_type in ["text", "email", "password", "search", "tel", "url", "number"]:
                        element_type = input_type
                        name_attr = element.get("name", "")
                        placeholder_attr = element.get("placeholder", "")
                        id_generation_text_source = placeholder_attr or name_attr or aria_label
                        specific_details = {"name": name_attr, "placeholder": placeholder_attr}
                    elif input_type in ["checkbox", "radio"]:
                        element_type = input_type
                        name_attr = element.get("name", "")
                        id_generation_text_source = name_attr or aria_label
                        specific_details = {"name": name_attr}
                    else:
                        continue  # Skip other input types
                elif tag_name == "a":
                    element_type = "link"
                    href_attr = element.get("href", "")
                    specific_details = {"text": text_content, "href": href_attr}
                elif tag_name == "textarea":
                    element_type = "textarea"
                    name_attr = element.get("name", "")
                    placeholder_attr = element.get("placeholder", "")
                    id_generation_text_source = placeholder_attr or name_attr or aria_label
                    specific_details = {"name": name_attr, "placeholder": placeholder_attr}
                elif tag_name == "select":
                    element_type = "select"
                    name_attr = element.get("name", "")
                    id_generation_text_source = name_attr or aria_label
                    specific_details = {"name": name_attr}
                elif tag_name == "div":
                    role_attr = element.get("role", "")
                    onclick_attr = element.get("onclick")
                    data_identifier_attr = element.get("data-identifier", "")

                    if role_attr == "button":
                        element_type = "button"
                        specific_details = {"text": text_content, "role": role_attr}
                    elif role_attr == "link":
                        element_type = "link"
                        specific_details = {"text": text_content, "role": role_attr}
                    elif onclick_attr or data_identifier_attr:
                        element_type = "interactive"
                        id_generation_text_source = text_content or data_identifier_attr or aria_label
                        specific_details = {"text": text_content, "role": role_attr, "data_identifier": data_identifier_attr}
                    else:
                        continue
                else:
                    continue  # Skip tags not explicitly handled

                # Skip if we couldn't determine element type
                if not element_type:
                    continue

                # Generate unique ID
                unique_id = generate_unique_id(element_type, xpath, id_generation_text_source, class_name, aria_label)

                # Ensure ID is truly unique
                temp_id = unique_id
                counter = 0
                while temp_id in elements_dict:
                    counter += 1
                    temp_id = f"{unique_id}_{counter}"
                unique_id = temp_id

                # Create element info dictionary
                base_info = {
                    "element_type": element_type,
                    "xpath": xpath,
                    "class_name": class_name,
                    "aria_label": aria_label
                }
                
                # Add tag_name for buttons/inputs
                if "tag_name" not in specific_details and tag_name in ["button", "input"]:
                    specific_details["tag_name"] = tag_name

                # Add the interact-element-id attribute to the element
                element['interact-element-id'] = unique_id

                # Store element info in dictionary
                elements_dict[unique_id] = {**base_info, **specific_details}

            except Exception as elem_err:
                # Log error and continue with next element
                print(f"Error processing element: {elem_err}")
                continue
        
        # Clean the HTML while preserving our added interact-element-id attributes
        cleaned_html = clean_html_string(str(soup))
        return elements_dict, cleaned_html

    except Exception as e:
        print(f"Error in extract_interactive_elements: {e}")
        return {}, ""