import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser
from dotenv import load_dotenv
from browser_use import BrowserConfig

# Read GOOGLE_API_KEY into env
load_dotenv()
config = BrowserConfig(
    headless=False,
    disable_security=False
)
# Initialize the model
llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash')

# Create agent with the model and browser
browser = Browser(config=config)
agent = Agent(
    task="Go to apnow.vercel.app. Its an app that helps you prepare for ap exams. Try out a few practice questions and see how it works. Try out different subjects, and utilize the many features it has.",
    llm=llm,
    browser=browser
)

async def main():
    # Execute the agent's task and await the result
    result = await agent.run()
    # Print the result
    print(result)
    # Close the browser
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())