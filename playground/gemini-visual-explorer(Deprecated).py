import os
import re
from pathlib import Path
import tempfile
from PIL import Image, ImageDraw # Added ImageDraw
import google.generativeai as genai
from playwright.sync_api import sync_playwright, TimeoutError # Added TimeoutError
import io
import shutil

# Configuration
VIEWPORT_HEIGHT = 850
RATIO = 16 / 9
VIEWPORT_WIDTH = int(VIEWPORT_HEIGHT*RATIO)
TARGET_SHORT_DIM = 768
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Set Google API key
from dotenv import load_dotenv
load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("models/gemini-2.0-flash")

def take_screenshot(page, output_path):
    screenshot = page.screenshot(full_page=False)
    with Image.open(io.BytesIO(screenshot)) as img:
        # Ensure scaling is based on the shortest side
        scale_factor = TARGET_SHORT_DIM / min(img.size) 
        new_size = tuple(int(dim * scale_factor) for dim in img.size)
        img.resize(new_size, Image.LANCZOS).save(output_path)
    return new_size

def scale_coordinates(gemini_x, gemini_y, original_size, scaled_size):
    scale_x = original_size[0] / scaled_size[0]
    scale_y = original_size[1] / scaled_size[1]
    return int(gemini_x * scale_x), int(gemini_y * scale_y)

def parse_gemini_response(response):
    response = response.strip()
    action_map = {
        "CLICK": ("click", 2),
        "TYPE": ("type", 3),
        "HOVER": ("hover", 2),
        "SCROLL": ("scroll", 3), # Updated from 1 to 3 arguments
        "GOTO_URL": ("navigate", 1),
        "DONE": ("done", 0)  # Added DONE action
    }
    
    for line in response.split("\n"):
        # Regex to capture action and optional arguments
        match = re.match(r"(\w+)(?:\s+(.*))?$", line.strip())
        if match:
            action_token, args_str = match.groups()
            action_token = action_token.upper()

            if action_token in action_map:
                action_name, expected_arg_count = action_map[action_token]
                
                actual_args = []
                if args_str: # If there are arguments string
                    # For TYPE, the last argument can contain spaces.
                    # maxsplit should be expected_arg_count - 1 unless arg_count is 0 or 1.
                    if expected_arg_count > 1:
                        actual_args = args_str.split(maxsplit=expected_arg_count - 1)
                    elif expected_arg_count == 1: # e.g. SCROLL PIXELS, GOTO_URL URL
                        actual_args = [args_str] 
                
                if len(actual_args) == expected_arg_count:
                    return action_name, actual_args
                # Handle case for DONE (0 args) when args_str is None or empty
                elif expected_arg_count == 0 and not args_str:
                    return action_name, []
    return None, None

def execute_action(page, action, args, original_size, scaled_size):
    if action == "click":
        dec_x, dec_y = float(args[0]), float(args[1])
        pixel_x_on_scaled_img = int(dec_x * scaled_size[0])
        pixel_y_on_scaled_img = int(dec_y * scaled_size[1])
        
        x, y = scale_coordinates(pixel_x_on_scaled_img, pixel_y_on_scaled_img, original_size, scaled_size)
        
        page.mouse.move(x, y) 
        page.mouse.click(x, y)
        print(f"Clicking at page coords ({x}, {y}) (Original Gemini decimals: {args[0]},{args[1]})")
    elif action == "type":
        dec_x, dec_y = float(args[0]), float(args[1])
        pixel_x_on_scaled_img = int(dec_x * scaled_size[0])
        pixel_y_on_scaled_img = int(dec_y * scaled_size[1])

        x, y = scale_coordinates(pixel_x_on_scaled_img, pixel_y_on_scaled_img, original_size, scaled_size)
        
        page.mouse.move(x, y)
        # Triple-click to select all text in the input field before typing
        page.mouse.click(x, y, click_count=3) 
        
        page.keyboard.type(args[2]) 
        print(f"Typing '{args[2]}' at page coords ({x}, {y}) (Original Gemini decimals: {args[0]},{args[1]}) after selecting existing text")
    elif action == "hover":
        dec_x, dec_y = float(args[0]), float(args[1])
        pixel_x_on_scaled_img = int(dec_x * scaled_size[0])
        pixel_y_on_scaled_img = int(dec_y * scaled_size[1])

        x, y = scale_coordinates(pixel_x_on_scaled_img, pixel_y_on_scaled_img, original_size, scaled_size)
        page.mouse.move(x, y)
        print(f"Hovering at page coords ({x}, {y}) (Original Gemini decimals: {args[0]},{args[1]})")
    elif action == "scroll":
        # args are: dec_x, dec_y, pages_to_scroll
        dec_x, dec_y = float(args[0]), float(args[1])
        pages_to_scroll = float(args[2])

        pixel_x_on_scaled_img = int(dec_x * scaled_size[0])
        pixel_y_on_scaled_img = int(dec_y * scaled_size[1])
        
        x, y = scale_coordinates(pixel_x_on_scaled_img, pixel_y_on_scaled_img, original_size, scaled_size)
        
        page.mouse.move(x, y) # Move mouse to the context location
        
        scroll_amount_pixels = int(pages_to_scroll * VIEWPORT_HEIGHT)
        page.mouse.wheel(0, scroll_amount_pixels)
        print(f"Scrolling by {pages_to_scroll} pages ({scroll_amount_pixels} pixels) at context page coords ({x}, {y})")
    elif action == "navigate":
        page.goto(args[0].strip('"'), timeout=60000) # Increased timeout to 60 seconds
        print(f"Navigating to {args[0]}")
    else:
        raise ValueError(f"Unknown action: {action}")

def main(goal):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})
        page.goto("https://homedepot.com", timeout=60000) # Increased timeout to 60 seconds
        
        system_prompt = f"""
        You are a web automation assistant. Your goal is: {goal}
        Respond with ONE and only one action per prompt. You can execute this action using these commands:
        - CLICK X Y
        - TYPE X Y xyz
        - HOVER X Y
        - SCROLL X Y pages
        - GOTO_URL url
        - DONE
        X and Y are decimal values between 0.0 and 1.0, representing the proportional coordinates in the screenshot (e.g., X=0.5, Y=0.25 means halfway across the width and a quarter way down the height).
        pages is a decimal value representing how many pages to scroll (e.g., 1 for one page down, -0.5 for half a page up).
        If the goal is achieved or you are stuck, respond with DONE.
        Utilize up to 4 decimal places for X and Y coordinates. It should be a precise and accurate decimal number for a perfect click.
        Your image only shows to main screen, not the entire page. You can only see the visible part of the screen. You can scroll down to see more results and information, proving very useful when you need to see more.
        """
        instructions = f""""""
        step_counter = 0
        previous_action_timed_out = False # Initialize flag
        last_action_details = None # Initialize variable to store last action

        while True:
            step_counter += 1
            # --- 1. Take Screenshot & Prepare for Gemini ---
            temp_screenshot_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp_screenshot_path = temp_screenshot_file.name
            
            current_scaled_size = take_screenshot(page, temp_screenshot_path)
            temp_screenshot_file.close() # Close the file before copying/uploading

            # Save the step-specific unannotated screenshot
            unannotated_img_path = SCREENSHOT_DIR / f"unannotated_step_{step_counter}.png"
            shutil.copy(temp_screenshot_path, unannotated_img_path)
            
            # Update the generic "last_screenshot.png"
            shutil.copy(temp_screenshot_path, SCREENSHOT_DIR / "last_screenshot.png")

            current_img_part = genai.upload_file(temp_screenshot_path)
            
            # Delete the temporary file now that it's uploaded and copied
            try:
                os.remove(temp_screenshot_path)
            except OSError as e:
                print(f"Error deleting temp screenshot {temp_screenshot_path}: {e}")

            # --- 2. Build Prompt for Gemini (single image) ---
            prompt_content = [system_prompt] + [instructions]

            if last_action_details:
                action_name_for_prompt = last_action_details["action"]
                args_for_prompt = last_action_details["args"]
                if args_for_prompt:
                    prompt_content.append(f"Your previous action was: {action_name_for_prompt.upper()} {' '.join(args_for_prompt)}")
                else: # For actions like DONE that have no args
                    prompt_content.append(f"Your previous action was: {action_name_for_prompt.upper()}")


            prompt_content.extend([
                "Current screen:", current_img_part
            ])
            
            # --- 3. Get Gemini's Response ---
            response = model.generate_content(prompt_content)
            raw_gemini_response_text = response.text.strip()
            print(f"Gemini's recommended action: {raw_gemini_response_text}")

            # Delete the img_part after getting the response
            current_img_part.delete()
            
            action, args = parse_gemini_response(raw_gemini_response_text)
            
            if action == "done":
                print("Goal achieved or Gemini signaled completion with DONE.")
                last_action_details = {"action": action, "args": args} # Store before break
                break

            if not action:
                print("Failed to parse response or unknown action:", raw_gemini_response_text)
                # Not setting last_action_details here as it was an invalid/unparsed action
                break 

            # Store the current action and args to be used in the next prompt
            last_action_details = {"action": action, "args": args}

            # --- 4. Annotate Screenshot (if applicable) ---
            if action in ["click", "type", "hover", "scroll"]: # Added "scroll" for potential annotation
                try:
                    # Convert decimal strings to floats
                    dec_x_for_annotation = float(args[0])
                    dec_y_for_annotation = float(args[1])
                    
                    # Path to the unannotated version of the screenshot Gemini just saw
                    # unannotated_img_path is SCREENSHOT_DIR / f"unannotated_step_{step_counter}.png"
                    
                    # Create the step-specific annotated file
                    step_annotated_path = SCREENSHOT_DIR / f"annotated_step_{step_counter}.png"
                    shutil.copy(unannotated_img_path, step_annotated_path)

                    with Image.open(step_annotated_path) as img_to_annotate:
                        draw = ImageDraw.Draw(img_to_annotate)
                        radius = 10 
                        img_width, img_height = img_to_annotate.size # These are current_scaled_size dimensions

                        # Calculate pixel coordinates for annotation on the scaled image
                        annotation_pixel_x = int(dec_x_for_annotation * img_width)
                        annotation_pixel_y = int(dec_y_for_annotation * img_height)

                        # Clamp coordinates to be within image bounds for drawing the ellipse
                        draw_x = max(radius, min(annotation_pixel_x, img_width - radius -1))
                        draw_y = max(radius, min(annotation_pixel_y, img_height - radius -1))

                        draw.ellipse(
                            (draw_x - radius, draw_y - radius, draw_x + radius, draw_y + radius),
                            outline="red", width=3
                        )
                        img_to_annotate.save(step_annotated_path)
                    
                    shutil.copy(step_annotated_path, SCREENSHOT_DIR / "last_annotated_action.png")
                    
                    print(f"Saved annotated screenshot to {step_annotated_path} with Gemini action at scaled image coords ({annotation_pixel_x},{annotation_pixel_y}) from decimals ({args[0]},{args[1]})")
                except (ValueError, IndexError, FileNotFoundError, Exception) as e:
                    print(f"Warning: Could not annotate screenshot for action {action}: {e}")

            # --- 5. Execute Action ---
            try:
                execute_action(
                    page,
                    action,
                    args,
                    original_size=(VIEWPORT_WIDTH, VIEWPORT_HEIGHT),
                    scaled_size=current_scaled_size 
                )
                # Adjust wait_for_load_state timeout if navigation occurred, otherwise use default
                load_timeout = 60000 if action == "navigate" else 10000
                page.wait_for_load_state("networkidle", timeout=load_timeout)
            except TimeoutError as te: # Specifically catch Playwright's TimeoutError
                print(f"Warning: Page load timeout: {te}. Continuing with the next action.")
                previous_action_timed_out = True # Set flag if timeout occurs
            except Exception as e: # Catch other exceptions
                print(f"Error executing action or during page load (other than timeout): {e}")
                break 
        
        # --- End of While Loop ---
        print("Exiting automation loop.")
        # No complex screenshot_history cleanup needed here as temp files and img_parts are handled per iteration.
        # Persisted unannotated_step_*.png and annotated_step_*.png files remain in SCREENSHOT_DIR.

if __name__ == "__main__":
    user_goal = "Imagine you are an average person. You live around palo alto, and are working on a home improvement project. Go to homedepot.com. You need some spraypaint for your project, Perhaps you might want to look at a few, selecting one that is good. YOu might want to see if its in stock near you, and where it is in the store."
    main(user_goal)