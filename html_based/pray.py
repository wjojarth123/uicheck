import asyncio
import sys
from playwright.async_api import async_playwright
from lxml import etree
from bs4 import BeautifulSoup
import hashlib
import time
import random

interactparam = 'inter'
async def get_interactable_elements(page):
    # Collect all clickable elements like <a>, <button>, <input>, etc.
    interactable_elements = await page.evaluate("""
        () => {
            const elements = [];
            const allElements = document.querySelectorAll('*');
            
            // Function to generate XPath for an element
            const getXPath = function(element) {
                if (element.id !== '') {
                    return `//*[@id="${element.id}"]`;
                }
                
                if (element === document.body) {
                    return '/html/body';
                }
                
                let ix = 0;
                const siblings = element.parentNode.childNodes;
                
                for (let i = 0; i < siblings.length; i++) {
                    const sibling = siblings[i];
                    
                    if (sibling === element) {
                        const pathIndex = ix + 1;
                        const tagName = element.tagName.toLowerCase();
                        
                        if (element.parentNode) {
                            return `${getXPath(element.parentNode)}/${tagName}[${pathIndex}]`;
                        } else {
                            return `/${tagName}[${pathIndex}]`;
                        }
                    }
                    
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        ix++;
                    }
                }
                
                return '';
            };

            allElements.forEach(element => {
                let method = null;
                
                // Check if element is a clickable element
                if (element instanceof HTMLButtonElement ||
                    element instanceof HTMLAnchorElement ||
                    element instanceof HTMLInputElement ||
                    element instanceof HTMLLabelElement ||
                    element instanceof HTMLSelectElement ||
                    element instanceof HTMLTextAreaElement ||
                    getComputedStyle(element).cursor === 'pointer' ||
                    element.hasAttribute('role') && (element.getAttribute('role') === 'button' || element.getAttribute('role') === 'link')
                ) {
                    // Determine method based on element type or role
                    if (element instanceof HTMLButtonElement || element instanceof HTMLAnchorElement) {
                        method = 'click';
                    } else if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
                        method = 'type';
                    } else if (element instanceof HTMLSelectElement) {
                        method = 'select';
                    } else if (getComputedStyle(element).cursor === 'pointer' || (element.hasAttribute('role') && (element.getAttribute('role') === 'button' || element.getAttribute('role') === 'link'))) {
                        method = 'click';
                    }
                    
                    elements.push({
                        tag: element.tagName,
                        role: element.getAttribute('role'),
                        id: element.id,
                        class: element.className,
                        onclick: element.onclick ? true : false,
                        href: element.href || null,
                        name: element.name || null,
                        value: element.value || null,
                        xpath: getXPath(element),
                        method: method  // Added the method
                    });
                }
            });

            return elements;
        }
    """)

    return interactable_elements



def generate_key(tag: str, xpath: str, method: str) -> str:
    """
    Generate a key in the format: method_tag_hash,
    where hash is the first 5 characters of an MD5 hash of the xpath.
    
    :param tag: The HTML tag (e.g., 'div', 'a')
    :param xpath: The XPath string
    :param method: The method name (e.g., 'click', 'type')
    :return: A formatted key string
    """
    # Ensure tag and method are strings and lowercase, use 'none' if None or empty
    tag_str = str(tag).lower() if tag else 'none'
    method_str = str(method).lower() if method else 'none'
    
    # Generate MD5 hash of the xpath
    xpath_hash = hashlib.md5(xpath.encode('utf-8')).hexdigest()[:5]
    
    # Construct the key
    key = f"{method_str}_{tag_str}_{xpath_hash}"
    
    return key

def get_xpath_by_unique_id(unique_id_to_find: str, all_elements_data: list) -> str | None:
    """
    Finds the XPath of an element given its unique ID.

    :param unique_id_to_find: The unique ID (generated by generate_key) to search for.
    :param all_elements_data: A list of dictionaries, where each dictionary contains
                              data about an interactable element, including 'tag', 'xpath', and 'method'.
    :return: The XPath string if the unique ID is found, otherwise None.
    """
    for element_data in all_elements_data:
        tag = element_data.get('tag')
        xpath = element_data.get('xpath')
        method = element_data.get('method')

        # We need all parts to generate the key for comparison
        if xpath is not None: # tag and method can be None, generate_key handles it
            current_key = generate_key(tag, xpath, method)
            if current_key == unique_id_to_find:
                return xpath
    return None

def clean_html(html_text):
    # Parse the HTML
    soup = BeautifulSoup(html_text, 'html.parser')

    # Remove all script and style tags
    for tag in soup(['script', 'style']):
        tag.decompose()

    # Define allowed attributes
    allowed_attributes = {interactparam, 'aria-name', 'title','placeholder','name','type','d', 'viewBox', 'width', 'height', 'fill', 'stroke', 
                      'points', 'transform', 'x', 'y', 'x1', 'y1', 'x2', 'y2',
                      'cx', 'cy', 'r', 'rx', 'ry', 'path', 'polygon', 'polyline',
                      'stroke-width', 'stroke-linecap', 'stroke-linejoin',
                      'fill-opacity', 'stroke-opacity', 'opacity', 'xmlns','alt'}

    # Function to clean tags' attributes
    def clean_attributes(tag):
        # Get all attributes of the tag
        for attribute in list(tag.attrs):
            # Keep only allowed attributes
            if attribute not in allowed_attributes:
                del tag[attribute]

    # Clean attributes for every tag in the HTML
    for tag in soup.find_all(True):  # True means all tags
        clean_attributes(tag)

    # Rename all <div> tags to <d>
    for div_tag in soup.find_all('div'):
        div_tag.name = 'd'

    # Return the cleaned HTML as a string
    return str(soup)
def click_helper(element,page):    
    def human_delay(min_ms=100, max_ms=300):
        time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))
    element = page.wait_for_selector(f"xpath={xpath}", timeout=5000)

    # Hover over the element first
    element.hover()
    human_delay(100, 300)

    # Get the position of the element and simulate a more natural click
    box = element.bounding_box()
    if box:
        x = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
        y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
        page.mouse.move(x, y, steps=random.randint(10, 25))  # Smooth movement
        human_delay(50, 150)
        page.mouse.down()
        human_delay(20, 100)
        page.mouse.up()
def modify_html_by_xpath(html, xpath, attribute, value):
    """
    Modify the HTML by setting a given attribute at the specified XPath location.

    Parameters:
    - html (str): The HTML content as a string.
    - xpath (str): The XPath expression to locate the element.
    - attribute (str): The attribute name to be modified or added.
    - value (str): The value to set the attribute to.

    Returns:
    - str: The modified HTML content.
    """
    # Parse the HTML content
    tree = etree.HTML(html)
    
    # Find the element(s) at the given XPath
    elements = tree.xpath(xpath)
    
    # If there are no elements matching the XPath, return the original HTML
    if not elements:
        return html

    # Modify the element's attribute
    for element in elements:
        element.set(attribute, value)
    
    modified_html = etree.tostring(tree, pretty_print=True, method="html").decode('utf-8')
    # Return the modified HTML as a string
    if modified_html != html:
        print(f"Modified HTML at XPath: {xpath} with attribute: {attribute} and value: {value}")
    return modified_html
async def main():
    # Check if URL was provided as command line argument
    if len(sys.argv) != 2:
        print("Usage: python script.py domain.com")
        sys.exit(1)
    
    # Get the domain from command line arguments and add https://
    domain = sys.argv[1]
    url = f"https://{domain}"
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"Navigating to {url}...")
        await page.goto(url)
        
        interactable_elements = await get_interactable_elements(page)

        if not interactable_elements:
            print("No interactable elements found!")
        else:
            raw_html = await page.content()

            print(f"\nInteractable Elements Found: ({len(interactable_elements)})")
            for idx, element in enumerate(interactable_elements, 1):
                # Use element['tag'] (HTML tag name) for the 'tag' parameter in generate_key
                # This aligns with generate_key's docstring and is more robust than element['name']
                unique_element_id = generate_key(element['tag'], element['xpath'], element['method'])
                raw_html = modify_html_by_xpath(raw_html, element['xpath'], interactparam, unique_element_id)
                print(f"{idx}. Tag: {element['tag']} | XPath: {element['xpath']} | Role: {element['role']} | ID: {element['id']} | Class: {element['class']} | Href: {element['href']} | Name: {element['name']} | Value: {element['value']}")
            cleaned_html = clean_html(raw_html)
            print("\nCleaned HTML:")
            print(cleaned_html)

            # Save the cleaned HTML to a file
            output_filename = f"{domain}_cleaned.html"
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(cleaned_html)
            print(f"\nCleaned HTML saved to {output_filename}")

        await browser.close()

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())