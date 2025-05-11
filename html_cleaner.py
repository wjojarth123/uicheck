import re
import os
from bs4 import BeautifulSoup, Comment

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
        return "" # Return empty string for empty input
        
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