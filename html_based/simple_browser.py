import os
import json
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from html_cleaner import clean_html_string
from dotenv import load_dotenv
import time

# Load API key
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Create logs folder
os.makedirs("logs", exist_ok=True)

# Setup Gemini model
model = genai.GenerativeModel(
    model_name="models/gemini-2.0-flash",
    generation_config={"max_output_tokens": 1024, "temperature": 0.7}
)

# Start browser
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Go to start URL
    start_url = "https://www.google.com"
    page.goto(start_url)
    
    # Keep track of previous actions to avoid loops
    previous_actions = []
    
    # Main loop
    for step in range(10):  # Run 10 steps max
        print(f"\nStep {step+1}: Getting page content...")
        
        # 1. GET HTML
        html = page.content()
        cleaned_html = clean_html_string(html)
        url = page.url
        title = page.title()
        
        # 2. CREATE PROMPT
        prompt = f"""
        You are an AI web automation assistant. Analyze the web page HTML and determine the next action to take.

        URL: {url}
        Page Title: {title}

        HTML Content:
        {cleaned_html[:10000]}...

        IMPORTANT: All interactive elements have been assigned a "data-unique-id" attribute.
        Look for these data-unique-id values in the HTML and use ONLY those exact values in your commands.

        Respond with a single action in one of these formats:
        - CLICK data-unique-id
        - TYPE data-unique-id "text to type"
        - HOVER data-unique-id
        - BACKBTN
        - DISMISS
        - GOTO url
        - WAIT
        """
        
        # Save prompt to log
        with open(f"logs/prompt_{step}.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
        
        # 3. SEND TO GEMINI
        print("Sending to Gemini API...")
        response = model.generate_content(prompt)
        action = response.text.strip()
        
        # Save response to log
        with open(f"logs/response_{step}.txt", "w", encoding="utf-8") as f:
            f.write(action)
        
        # 4. CHECK FOR REPETITION
        if action in previous_actions:
            print(f"Avoiding repeated action: {action}")
            action = "DISMISS"  # Try dismissing dialogs instead
        previous_actions.append(action)
        
        # 5. TAKE ACTION
        print(f"Taking action: {action}")
        
        if action.startswith("CLICK "):
            element_id = action.split(" ")[1]
            try:
                page.click(f"[data-unique-id='{element_id}']")
                print(f"Clicked element: {element_id}")
                time.sleep(2)  # Wait for page to react
            except Exception as e:
                print(f"Error clicking element: {e}")
                
        elif action.startswith("TYPE "):
            parts = action.split(" ", 2)
            if len(parts) >= 3:
                element_id = parts[1]
                text = parts[2].strip('"')
                try:
                    page.click(f"[data-unique-id='{element_id}']")
                    page.fill(f"[data-unique-id='{element_id}']", text)
                    print(f"Typed '{text}' into element: {element_id}")
                    time.sleep(1)
                except Exception as e:
                    print(f"Error typing text: {e}")
                    
        elif action.startswith("GOTO "):
            url = action[5:].strip()
            try:
                page.goto(url)
                print(f"Navigated to: {url}")
                time.sleep(2)
            except Exception as e:
                print(f"Error navigating: {e}")
                
        elif action == "BACKBTN":
            page.go_back()
            print("Went back to previous page")
            time.sleep(2)
            
        elif action == "DISMISS":
            # Simple modal dismissal logic
            for button in ["Accept", "OK", "Close", "No Thanks", "I Agree"]:
                try:
                    page.click(f"button:has-text('{button}')", timeout=1000)
                    print(f"Dismissed dialog by clicking '{button}'")
                    break
                except:
                    pass
            time.sleep(1)
            
        elif action == "WAIT":
            print("Waiting as recommended")
            time.sleep(3)
            
        # Wait between actions
        time.sleep(2)
    
    print("Browser automation complete")
    browser.close()