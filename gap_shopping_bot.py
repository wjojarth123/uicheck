#!/usr/bin/env python3
"""
GAP Shopping Bot

This script automates the process of adding men's jeans to the cart on gap.com using:
1. Playwright for web automation
2. HTML Cleaner to remove unnecessary elements from the page source
3. Groq AI (DeepSeek model) or Llama API to analyze the page and decide what elements to interact with
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import argparse
from playwright.async_api import async_playwright
from html_cleaner import clean_html_string
from bs4 import BeautifulSoup
import difflib

# For Groq API
try:
    from groq import Groq
except ImportError:
    print("Installing required packages...")
    subprocess.run([sys.executable, "-m", "pip", "install", "groq"], check=True)
    from groq import Groq

# Groq API Key
GROQ_API_KEY = "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"

# Llama API Key
LLAMA_API_KEY = "LL-2YwX9QZ8N7V6B4C3D2E1F0G9H8I7J6K5L4M3N2O1P0Q9R8S7T6U5V4W3X2Y1Z0"

# Task for the AI
SHOPPING_TASK = """
You are a web automation assistant. You will be given the HTML of a webpage from gap.com.
Your task is to help add men's jeans to the shopping cart.

Please analyze the HTML and tell me EXACTLY what to do next. Choose ONE of these actions:
1. CLICK: Specify the element to click by providing its class, id, or text content
2. SEARCH: Tell me what to search for in the search box
3. TYPE: Tell me what text to type and in which element
4. WAIT: If we need to wait for a page to load
5. HOVER: Specify an element to hover over
6. SELECT: Choose an option from a dropdown
7. DONE: If we have successfully added jeans to the cart

For each action, give:
1. The action type (CLICK, SEARCH, TYPE, etc.)
2. The exact selector to use (CSS selector, XPath, or text description)
3. A very brief explanation of why this action
4. If it's a TYPE action, specify the text to enter

Respond in this exact format:
ACTION: [action type]
SELECTOR: [selector or description]
VALUE: [only for TYPE or SELECT actions]
REASON: [brief explanation]

Current page: [briefly describe what you see on the current page]
"""

# Add this global variable after the imports
last_page_content = None

def get_page_differences(new_html):
    """
    Compare new HTML with the last page content and return only the differences
    """
    global last_page_content
    
    if last_page_content is None:
        # First page, store it and return the whole content
        last_page_content = new_html
        return new_html
    
    # Parse both HTML contents
    soup1 = BeautifulSoup(last_page_content, 'html.parser')
    soup2 = BeautifulSoup(new_html, 'html.parser')
    
    # Remove script and style tags from both
    for tag in soup1.find_all(['script', 'style']):
        tag.decompose()
    for tag in soup2.find_all(['script', 'style']):
        tag.decompose()
    
    # Get the text content of both pages
    text1 = soup1.get_text(separator=' ', strip=True)
    text2 = soup2.get_text(separator=' ', strip=True)
    
    # Find differences
    differ = difflib.Differ()
    diff = list(differ.compare(text1.splitlines(), text2.splitlines()))
    
    # Extract only the new and changed lines
    changes = []
    for line in diff:
        if line.startswith('+ '):
            changes.append(line[2:])
    
    # If there are changes, update the last page content
    if changes:
        last_page_content = new_html
    
    # Return either the changes or a minimal representation of the new page
    if changes:
        return "Page changes detected:\n" + "\n".join(changes)
    else:
        # If no changes detected, return a minimal representation of the current page
        return f"Current page URL: {soup2.find('title').text if soup2.find('title') else 'No title'}\n" + \
               "No significant changes detected from previous page."

async def fetch_llama_response(html_content):
    """
    Send the cleaned HTML to Hack Club AI and get a response about what to do next
    """
    try:
        # Get only the differences from the last page
        page_diff = get_page_differences(html_content)
        
        # Save the differences for debugging
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        diff_file = f"llama_request_{timestamp}.txt"
        with open(diff_file, "w", encoding="utf-8") as f:
            f.write(page_diff)
        print(f"Saved page differences to {diff_file}")
        
        # Create a prompt with the task and the page differences
        prompt = f"{SHOPPING_TASK}\n\nPage Content:\n{page_diff}"
        
        # Prepare the curl command for Hack Club AI
        curl_command = [
            "curl",
            "-X", "POST",
            "https://ai.hackclub.com/chat/completions",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            })
        ]
        
        max_retries = 3
        current_retry = 0
        
        while current_retry < max_retries:
            try:
                print(f"Calling Hack Club AI (attempt {current_retry + 1}/{max_retries})...")
                
                # Execute the curl command
                result = subprocess.run(curl_command, capture_output=True, text=True)
                
                if result.returncode == 0:
                    try:
                        response = json.loads(result.stdout)
                        # Fix: Properly access the response content based on Hack Club AI format
                        if "choices" in response and len(response["choices"]) > 0:
                            if "message" in response["choices"][0]:
                                response_content = response["choices"][0]["message"]["content"]
                            else:
                                response_content = response["choices"][0]["text"]
                            print("Received response from Hack Club AI")
                            return response_content
                        else:
                            print(f"Unexpected Hack Club AI response format: {response}")
                            raise Exception("Invalid response format from Hack Club AI")
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse Hack Club AI response: {e}")
                        print(f"Raw response: {result.stdout}")
                        raise Exception("Invalid JSON response from Hack Club AI")
                else:
                    print(f"Error calling Hack Club AI: {result.stderr}")
                    raise Exception(f"Hack Club AI call failed: {result.stderr}")
                
            except Exception as e:
                print(f"Error calling Hack Club AI: {e}")
                current_retry += 1
                if current_retry < max_retries:
                    wait_time = 5 * current_retry  # Exponential backoff
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        # If all retries failed, use fallback actions
        print("All Hack Club AI calls failed, using fallback action sequence...")
        return get_fallback_action()
        
    except Exception as e:
        print(f"Unexpected error in fetch_llama_response: {e}")
        return get_fallback_action()

async def fetch_groq_response(html_content):
    """
    Send the cleaned HTML to Groq AI (DeepSeek model) and get a response about what to do next
    """
    try:
        # Get only the differences from the last page
        page_diff = get_page_differences(html_content)
        
        # Save the differences for debugging
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        diff_file = f"page_diff_{timestamp}.txt"
        with open(diff_file, "w", encoding="utf-8") as f:
            f.write(page_diff)
        print(f"Saved page differences to {diff_file}")
        
        # Create a prompt with the task and the page differences
        prompt = f"{SHOPPING_TASK}\n\nPage Content:\n{page_diff}"
        
        # Initialize Groq client
        client = Groq(api_key=GROQ_API_KEY)
        
        max_retries = 3
        current_retry = 0
        
        while current_retry < max_retries:
            try:
                print(f"Calling Groq API (attempt {current_retry + 1}/{max_retries})...")
                
                # Create messages for the chat completion
                messages = [
                    {"role": "user", "content": prompt}
                ]
                
                # Request completion from Groq
                completion = client.chat.completions.create(
                    model="deepseek-r1-distill-llama-70b",
                    messages=messages,
                    temperature=0.6,
                    max_completion_tokens=4096,
                    top_p=0.95,
                    stream=False,
                    stop=None,
                )
                
                # Extract and return the content
                response_content = completion.choices[0].message.content
                print("Received response from Groq API")
                return response_content
            
            except Exception as e:
                print(f"Error calling Groq API: {e}")
                current_retry += 1
                if current_retry < max_retries:
                    wait_time = 5 * current_retry  # Exponential backoff
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
        
        # If all retries failed, use fallback actions
        print("All Groq API calls failed, using fallback action sequence...")
        return get_fallback_action()
        
    except Exception as e:
        print(f"Unexpected error in fetch_groq_response: {e}")
        return get_fallback_action()

def get_fallback_action():
    """
    Provides a fallback action sequence when API is unavailable
    """
    # Predefined fallback actions for gap.com - Each will be returned in sequence
    fallback_actions = [
        """
ACTION: SEARCH
SELECTOR: men's jeans
REASON: Search for men's jeans to find relevant products
        """,
        """
ACTION: CLICK
SELECTOR: a.product_card
REASON: Click the first product to view details
        """,
        """
ACTION: SELECT
SELECTOR: select[aria-label="Size"]
VALUE: 32W x 30L
REASON: Select a common size for men's jeans
        """,
        """
ACTION: CLICK
SELECTOR: button.add-to-bag, button.add-to-cart
REASON: Add the selected item to the shopping cart
        """,
        """
ACTION: DONE
SELECTOR: 
REASON: Successfully added jeans to cart using fallback sequence
        """
    ]
    
    # Use a file to track which fallback action to return next
    fallback_index_file = "fallback_index.txt"
    
    try:
        if os.path.exists(fallback_index_file):
            with open(fallback_index_file, "r") as f:
                index = int(f.read().strip())
        else:
            index = 0
            
        action = fallback_actions[index]
        
        # Update the index for next time
        with open(fallback_index_file, "w") as f:
            f.write(str((index + 1) % len(fallback_actions)))
            
        return action
    except Exception as e:
        print(f"Error in fallback action: {e}")
        return fallback_actions[0]  # Return first action as ultimate fallback

async def execute_action(page, action):
    """
    Execute the action recommended by the AI
    """
    try:
        # Parse the AI response into a dictionary
        action_dict = {}
        for line in action.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                action_dict[key.strip()] = value.strip()
        
        # Extract action details
        action_type = action_dict.get('ACTION', '').lower()
        selector = action_dict.get('SELECTOR', '')
        value = action_dict.get('VALUE', '')
        
        print(f"Executing action: {action_type} with selector: {selector}")
        
        if action_type == "click":
            # Try multiple click methods in sequence
            click_methods = [
                # Method 1: Direct CSS selector
                lambda: page.click(selector),
                # Method 2: Text content exact match
                lambda: page.click(f"text={selector}"),
                # Method 3: Text content contains
                lambda: page.click(f"text='{selector}'"),
                # Method 4: Element containing text
                lambda: page.click(f"*:has-text('{selector}')"),
                # Method 5: Button with text
                lambda: page.click(f"button:has-text('{selector}')"),
                # Method 6: Link with text
                lambda: page.click(f"a:has-text('{selector}')"),
                # Method 7: Button or anchor with partial text match
                lambda: page.click(f"button, a >> text=/{selector}/i")
            ]
            
            # Additional selectors for common elements
            if "men" in selector.lower():
                click_methods.extend([
                    lambda: page.click('a[href*="mens"]'),
                    lambda: page.click('a[href*="men"]'),
                    lambda: page.click('a:has-text("Men")'),
                    lambda: page.click('a:has-text("Men\'s")')
                ])
            
            for i, click_method in enumerate(click_methods, 1):
                try:
                    print(f"Trying click method {i}...")
                    await click_method()
                    print(f"Click method {i} succeeded")
                    
                    # Wait for navigation or network idle
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass  # Ignore timeout, continue anyway
                    
                    # Check if we're on a product page or cart page
                    current_url = page.url
                    if "product" in current_url or "cart" in current_url or "bag" in current_url:
                        # If we're on a product page, try to add to cart
                        if "product" in current_url:
                            add_to_cart_selectors = [
                                '[data-testid="add-to-cart-button"]',
                                '[aria-label="Add to Bag"]',
                                'button:has-text("Add to Bag")',
                                'button:has-text("Add to Cart")',
                                '[data-testid="add-to-bag-button"]',
                                'button.add-to-cart',
                                'button.add-to-bag'
                            ]
                            
                            for cart_selector in add_to_cart_selectors:
                                try:
                                    await page.click(cart_selector)
                                    print(f"Clicked add to cart button: {cart_selector}")
                                    # Wait for cart confirmation
                                    await page.wait_for_load_state("networkidle", timeout=5000)
                                    return True
                                except:
                                    continue
                    
                    return False  # Not done yet
                except Exception as e:
                    print(f"Click method {i} failed: {e}")
                    if i == len(click_methods):
                        print("All click methods failed")
                        return False
            
        elif action_type == "type":
            # Type text into the search box
            await page.fill(selector, value or "men's jeans")
            await page.press(selector, "Enter")
            return False  # Not done yet
            
        elif action_type == "wait":
            # Wait for a specific element
            await page.wait_for_selector(selector, timeout=10000)
            return False  # Not done yet
            
        elif action_type == "scroll":
            # Scroll to a specific element
            element = await page.query_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()
            return False  # Not done yet
            
        elif action_type == "check_cart":
            # Check if we're on the cart page and item is added
            if "cart" in page.url or "bag" in page.url:
                # Verify item is in cart
                try:
                    cart_items = await page.query_selector_all('.cart-item, .bag-item, [data-testid="cart-item"]')
                    if len(cart_items) > 0:
                        return True  # Item is in cart
                except:
                    pass
            return False
            
        elif action_type == "check_product":
            # Check if we're on a product page
            if "product" in page.url:
                # Try to find and click the add to cart button
                add_to_cart_selectors = [
                    '[data-testid="add-to-cart-button"]',
                    '[aria-label="Add to Bag"]',
                    'button:has-text("Add to Bag")',
                    'button:has-text("Add to Cart")',
                    '[data-testid="add-to-bag-button"]',
                    'button.add-to-cart',
                    'button.add-to-bag'
                ]
                
                for cart_selector in add_to_cart_selectors:
                    try:
                        await page.click(cart_selector)
                        print(f"Clicked add to cart button: {cart_selector}")
                        # Wait for cart confirmation
                        await page.wait_for_load_state("networkidle", timeout=5000)
                        return True
                    except:
                        continue
                
                return False
            
        return False
        
    except Exception as e:
        print(f"Error executing action: {e}")
        return False

async def gap_shopping_automation(use_llama=False):
    """
    Main function to automate shopping on gap.com
    """
    async with async_playwright() as p:
        # Launch a new browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800}
        )
        
        # Create a new page
        page = await context.new_page()
        
        try:
            # Navigate to gap.com with extended timeout
            print("Navigating to gap.com...")
            try:
                await page.goto("https://www.gap.com/", timeout=60000)  # Increase timeout to 60 seconds
                print("Initial page load complete")
            except Exception as e:
                print(f"Warning during initial navigation: {e} - will attempt to continue")
                # Take a screenshot of whatever loaded
                await page.screenshot(path="partial_load.png")
                print("Partial load screenshot saved to partial_load.png")
            
            print("Waiting for page to be fully loaded...")
            
            # Wait for the page to be fully loaded
            try:
                # First wait for network to be idle
                await page.wait_for_load_state("networkidle", timeout=60000)
                print("Network activity settled")
            except Exception as e:
                print(f"Network idle timeout, but continuing: {e}")
            
            # Wait for a commonly available element to ensure the page is loaded
            try:
                await page.wait_for_selector("header, .header, nav, .nav, .logo, a, button", timeout=30000)
                print("Found navigation elements, page appears to be loaded")
            except Exception as e:
                print(f"Could not find common elements, but continuing: {e}")
            
            print("Page loaded, proceeding with automation...")
            
            # Take initial screenshot
            await page.screenshot(path="initial_page.png")
            print("Initial screenshot saved to initial_page.png")
            
            # Loop for interaction steps guided by AI
            max_steps = 15  # Limit to prevent infinite loops
            current_step = 0
            task_completed = False
            consecutive_failures = 0  # Track consecutive failures
            
            while current_step < max_steps and not task_completed:
                current_step += 1
                print(f"\nStep {current_step}/{max_steps}")
                
                try:
                    # Get the current page content
                    html_content = await page.content()
                    
                    # Clean the HTML using our module
                    try:
                        cleaned_html = clean_html_string(html_content)
                        print("HTML cleaned successfully")
                    except Exception as e:
                        print(f"Error cleaning HTML: {e}")
                        print("Using original HTML content")
                        cleaned_html = html_content
                    
                    # Get action recommendation from AI
                    print("Asking AI what to do next...")
                    if use_llama:
                        ai_response = await fetch_llama_response(cleaned_html)
                    else:
                        ai_response = await fetch_groq_response(cleaned_html)
                    
                    if not ai_response:
                        print("No response from AI, using fallback action...")
                        ai_response = get_fallback_action()
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0  # Reset failure counter on success
                    
                    print("Action to execute:")
                    print(ai_response)
                    
                    # Execute the recommended action
                    try:
                        task_completed = await execute_action(page, ai_response)
                        if task_completed:
                            print("Task marked as completed!")
                    except Exception as e:
                        print(f"Error executing action: {e}")
                        consecutive_failures += 1
                        
                        if consecutive_failures >= 3:
                            print(f"WARNING: {consecutive_failures} consecutive failures detected")
                            # Try a simple fallback - click on something related to men's jeans
                            try:
                                print("Attempting emergency fallback action...")
                                await page.click('a:has-text("Men"), a:has-text("Jeans"), [href*="mens"], [href*="jeans"]')
                                print("Emergency fallback action succeeded")
                                consecutive_failures = 0
                            except:
                                print("Emergency fallback action also failed")
                    
                    # Take a screenshot after each action
                    screenshot_path = f"step_{current_step}.png"
                    await page.screenshot(path=screenshot_path)
                    print(f"Screenshot saved to {screenshot_path}")
                    
                except Exception as e:
                    print(f"Error during step {current_step}: {e}")
                    consecutive_failures += 1
                    
                # If we've had too many consecutive failures, try to refresh the page
                if consecutive_failures >= 3:
                    print("Too many consecutive failures, trying to refresh the page...")
                    try:
                        await page.reload(timeout=60000)
                        print("Page refreshed successfully")
                        consecutive_failures = 0  # Reset failure counter
                    except Exception as e:
                        print(f"Error refreshing page: {e}")
                
            if task_completed:
                print("\nSuccessfully completed the task of adding men's jeans to the cart!")
                # Final screenshot
                await page.screenshot(path="final_result.png")
                print("Final screenshot saved to final_result.png")
            else:
                print("\nReached maximum steps without completing the task.")
                # Check if we're on what looks like a product or cart page
                url = page.url
                if "product" in url or "jeans" in url or "mens" in url or "cart" in url or "bag" in url:
                    print("It looks like we made progress even though the task wasn't explicitly completed.")
                await page.screenshot(path="final_state.png")
                print("Final state screenshot saved to final_state.png")
                
        except Exception as e:
            print(f"An error occurred: {e}")
            # Take a screenshot of the error state
            try:
                await page.screenshot(path="error_state.png")
                print("Error state screenshot saved to error_state.png")
            except:
                pass
            
        finally:
            # Close the browser
            await browser.close()

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GAP Shopping Bot')
    parser.add_argument('--llama', action='store_true', help='Use Llama API instead of Groq')
    args = parser.parse_args()
    
    # Install required packages if not already installed
    try:
        import playwright
    except ImportError:
        print("Installing Playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    
    try:
        from groq import Groq
    except ImportError:
        print("Installing Groq API client...")
        subprocess.run([sys.executable, "-m", "pip", "install", "groq"], check=True)
        
    # Run the automation
    asyncio.run(gap_shopping_automation(use_llama=args.llama)) 