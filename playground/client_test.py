#!/usr/bin/env python3

import asyncio
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from playwright.async_api import async_playwright

# Load environment variables (for API keys)
load_dotenv()


async def hook_function(agent):
    """
    A hook function that takes a screenshot of the current page
    and saves it as 'screenshot.png'.
    """
    page = agent.browser_session.context.pages[-1]
    if page:
        await page.screenshot(path='screenshot.png')
        print("✅ Screenshot taken and saved as 'screenshot.png'.")
    else:
        print("⚠️ Page is not initialized!")

async def main():
    global context, page

    # Path to the default Edge browser executable
    edge_path = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
    user_data_dir = "c:\\Users\\HP\\AppData\\Local\\Microsoft\\Edge\\User Data"

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=edge_path,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-client-side-phishing-detection',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-prompt-on-repost',
                '--disable-sync',
                '--no-first-run',
            ],
            viewport={'width': 1920, 'height': 1080},
        )

        # Open the page
        page = await context.new_page()
        await page.goto("https://everfi.com")

        # Initialize the Gemini model
        llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash')

        # Create the agent
        agent = Agent(
            task=(
                "Go to everfi.com, log in as a student using Google account "
                "100034323@mvla.net. Complete a mental health lesson, and interact "
                "with the questions there as if you were a student. Tools like "
                "hovering or scrolling are often useful."
            ),
            llm=llm,
            page=page,
            context=context,
        )

        # Run the agent with the hook
        await agent.run(on_step_end=hook_function)

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())
