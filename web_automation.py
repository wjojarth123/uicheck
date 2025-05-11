import asyncio
from playwright.async_api import async_playwright
import requests
import json
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse

class WebAutomation:
    def __init__(self):
        self.llama_api_url = "https://ai.hackclub.com/chat/completions"
        self.context = None
        self.page = None

    def format_url(self, url):
        """Format URL to ensure it has proper scheme"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    async def init_browser(self):
        print("Initializing browser...")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        self.context = await browser.new_context()
        self.page = await self.context.new_page()
        print("Browser initialized successfully")

    def get_page_summary(self, html_content):
        """Create a summarized version of the page HTML"""
        print("\nAnalyzing page content...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Get interactive elements
        interactive_elements = []
        for element in soup.find_all(['input', 'button', 'a', 'select']):
            element_type = element.name
            element_id = element.get('id', '')
            element_class = element.get('class', [])
            element_text = element.get_text(strip=True)
            
            if element_type == 'input':
                input_type = element.get('type', '')
                interactive_elements.append(f"Input field: type={input_type}, id={element_id}, class={element_class}")
            elif element_type == 'button':
                interactive_elements.append(f"Button: text={element_text}, id={element_id}, class={element_class}")
            elif element_type == 'a':
                interactive_elements.append(f"Link: text={element_text}, href={element.get('href', '')}")
            elif element_type == 'select':
                options = [opt.get_text(strip=True) for opt in element.find_all('option')]
                interactive_elements.append(f"Select: options={options}, id={element_id}, class={element_class}")

        # Create summary
        summary = {
            "page_title": soup.title.string if soup.title else "No title",
            "main_content": text[:1000] + "..." if len(text) > 1000 else text,
            "interactive_elements": interactive_elements
        }
        
        print(f"Found {len(interactive_elements)} interactive elements")
        return json.dumps(summary, indent=2)

    def extract_json_from_response(self, response_text):
        """Extract JSON object from Llama API response"""
        # Find JSON block in the response
        json_match = re.search(r'```json\s*({[\s\S]*?})\s*```', response_text)
        if json_match:
            return json_match.group(1)
        
        # If no JSON block found, try to find any JSON object
        json_match = re.search(r'({[\s\S]*})', response_text)
        if json_match:
            return json_match.group(1)
        
        raise ValueError("No JSON object found in response")

    def get_llama_response(self, task, page_summary):
        """Get response from Llama API"""
        print("\nSending request to Llama API...")
        messages = [
            {
                "role": "system",
                "content": """You are a web automation assistant. Based on the page summary and task, provide the next action to take. 
                Respond with a JSON object containing:
                - 'action': one of 'click', 'type', 'select', 'wait'
                - 'selector': CSS selector for the element
                - 'value': (optional) value for type/select actions
                - 'description': brief description of what you're doing
                Example response:
                ```json
                {
                    "action": "click",
                    "selector": "a[href*='men']",
                    "description": "Clicking on the Men's section link"
                }
                ```"""
            },
            {
                "role": "user",
                "content": f"Task: {task}\nPage Summary: {page_summary}"
            }
        ]

        try:
            response = requests.post(
                self.llama_api_url,
                headers={"Content-Type": "application/json"},
                json={"messages": messages}
            )
            
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                print(f"Llama API Response: {content}")
                
                # Extract JSON from the response
                json_str = self.extract_json_from_response(content)
                print(f"Extracted JSON: {json_str}")
                return json_str
            else:
                print(f"API Error Response: {response.text}")
                raise Exception(f"API request failed with status {response.status_code}")
        except Exception as e:
            print(f"Error calling Llama API: {str(e)}")
            raise

    async def execute_action(self, action_data):
        """Execute the action returned by Llama"""
        try:
            print("\nExecuting action...")
            action_json = json.loads(action_data)
            action = action_json.get("action")
            selector = action_json.get("selector")
            value = action_json.get("value")
            description = action_json.get("description", "No description provided")

            print(f"Action: {action}")
            print(f"Selector: {selector}")
            print(f"Description: {description}")

            if action == "click":
                await self.page.click(selector)
                print("Clicked element")
            elif action == "type":
                await self.page.fill(selector, value)
                print(f"Typed: {value}")
            elif action == "select":
                await self.page.select_option(selector, value)
                print(f"Selected: {value}")
            elif action == "wait":
                await self.page.wait_for_selector(selector)
                print("Waited for element")
            
            # Wait for navigation or network idle
            await self.page.wait_for_load_state("networkidle")
            print("Page load complete")
            
        except Exception as e:
            print(f"Error executing action: {str(e)}")
            raise

    async def run_automation(self, task, url):
        """Main automation loop"""
        url = self.format_url(url)
        print(f"\nStarting automation for task: {task}")
        print(f"URL: {url}")
        
        await self.init_browser()
        print(f"Navigating to {url}...")
        await self.page.goto(url)
        print("Page loaded")
        
        while True:
            # Get current page content
            html_content = await self.page.content()
            page_summary = self.get_page_summary(html_content)
            
            # Get next action from Llama
            llama_response = self.get_llama_response(task, page_summary)
            
            # Execute the action
            await self.execute_action(llama_response)
            
            # Check if task is complete
            if "task_complete" in llama_response.lower():
                print("\nTask completed!")
                break

        await self.context.close()
        print("Browser closed")

async def main():
    task = input("Enter your task (e.g., 'buy men's jeans on gap.com'): ")
    url = input("Enter the starting URL (e.g., gap.com or https://www.gap.com): ")
    
    automation = WebAutomation()
    await automation.run_automation(task, url)

if __name__ == "__main__":
    asyncio.run(main()) 