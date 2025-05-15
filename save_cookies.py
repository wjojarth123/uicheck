import asyncio
import json
import os
from playwright.async_api import async_playwright

COOKIES_FILE = "cookies.json"

async def main():
    async with async_playwright() as p:
        # Suggest using a persistent context for a better chance of extensions/settings being sticky
        # if the user wants that, though it's not strictly for cookie saving here.
        # For simplicity, a regular context is fine for just cookie saving.
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        
        page = await context.new_page()
        await page.goto("about:blank") # Or a common start page like "https://www.google.com"
        
        print("\n" + "="*50)
        print("BROWSER WINDOW IS OPEN FOR MANUAL BROWSING")
        print("Please browse as needed. Your cookies will be saved when you close the browser window.")
        print(f"Cookies will be saved to: {os.path.abspath(COOKIES_FILE)}")
        print("DO NOT PRESS CTRL+C. Simply close the browser window.")
        print("="*50 + "\n")

        disconnected_event = asyncio.Event()
        browser_closed_normally = False # Flag to indicate normal closure

        def on_disconnected():
            nonlocal browser_closed_normally
            print("DEBUG: Browser disconnected event received.")
            browser_closed_normally = True
            if not disconnected_event.is_set():
                disconnected_event.set()

        browser.on("disconnected", on_disconnected)

        try:
            # Keep the script alive while the browser is open
            # This will block until browser.close() is implicitly called by user closing window,
            # which then triggers the "disconnected" event.
            # An alternative way to keep it alive is to wait for the page to close if only one page matters.
            print("DEBUG: Script is now waiting for the browser window to be closed by the user...")
            await disconnected_event.wait()
            if browser_closed_normally:
                 print("DEBUG: Browser was closed by the user (disconnected event).")

        except KeyboardInterrupt:
            print("\nWARNING: KeyboardInterrupt received by script.")
            print("This usually means you pressed Ctrl+C in the terminal.")
            print("Attempting to close browser and save cookies, but this might be unreliable.")
            if not browser_closed_normally:
                 # If Ctrl+C happened before normal close, try to close browser to trigger disconnect logic
                try:
                    print("DEBUG: KeyboardInterrupt - trying to explicitly close browser...")
                    await browser.close() # This should trigger the disconnected event if not already fired
                    await asyncio.sleep(1) # Give a moment for disconnect event to process
                except Exception as e_close:
                    print(f"DEBUG: Error closing browser during KeyboardInterrupt: {e_close}")
        finally:
            print("\nINFO: Proceeding to cookie saving logic (in finally block).")
            # Ensure the disconnected_event is set if it hasn't been, to avoid deadlocks if error occurred before
            if not disconnected_event.is_set():
                print("DEBUG: Forcing disconnected_event set in finally block (likely due to early exit/error).")
                disconnected_event.set() # Ensure we don't hang if an error happened before event was set

            try:
                # Check if context is still usable. Context might be gone if browser closed abruptly.
                # Playwright context.cookies() can throw if the underlying connection is gone.
                print("DEBUG: Checking if context is usable for cookie retrieval...")
                cookies = []
                try:
                    # Try to get cookies. This is the part that might fail if browser closed too fast or was killed.
                    # We might need a short delay or a check if browser.is_connected()
                    if browser.is_connected(): # is_connected() is a browser method
                        print("DEBUG: Browser is reported as connected. Attempting context.cookies().")
                        # Sometimes, even if browser is_connected, context might be unavailable after manual close
                        # Give it a tiny moment
                        await asyncio.sleep(0.5)
                        cookies = await context.cookies()
                    else:
                        print("WARN: Browser is reported as not connected. May not be able to retrieve cookies.")
                        # If browser is not connected, context.cookies() will likely fail.
                        # We might try to get cookies from a potentially stored list if we captured them earlier, but we are not.

                except Exception as e_get_cookies:
                    print(f"ERROR: Failed to retrieve cookies from context. Error: {e_get_cookies}")
                    print("INFO: This often means the browser closed too abruptly or the context became invalid.")
                
                if cookies:
                    with open(COOKIES_FILE, "w") as f:
                        json.dump(cookies, f, indent=2)
                    print(f"SUCCESS: Saved {len(cookies)} cookies to {COOKIES_FILE}")
                else:
                    # Check if the failure was due to an error or genuinely no cookies
                    if 'e_get_cookies' in locals():
                        print(f"INFO: Could not save cookies due to previous error: {e_get_cookies}")
                    else:
                        print("INFO: No cookies were found in the session to save.")
            
            except Exception as e_save_generic:
                print(f"ERROR: An unexpected error occurred during the cookie saving process. Error: {e_save_generic}")
                import traceback
                traceback.print_exc()

        print("INFO: Cookie saving script has finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This top-level catch is mostly for if asyncio.run() itself is interrupted before main() fully exits.
        print("\nINFO: Script execution forcefully terminated by KeyboardInterrupt at the top level.") 