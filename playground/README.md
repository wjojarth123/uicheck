# Gemini Visual Web Automator

A Python tool that uses Google's Gemini model to understand and automate web browser interactions based on visual input and a user-defined goal.

## Features

- Captures screenshots of web pages.
- Sends screenshots and a user goal to the Gemini Pro Vision model for action determination.
- Parses Gemini's responses to perform actions like:
    - `CLICK X Y`: Clicks at specified proportional coordinates.
    - `TYPE X Y text`: Clicks at coordinates and types text.
    - `HOVER X Y`: Hovers the mouse at specified coordinates.
    - `SCROLL PIXELS`: Scrolls the page vertically.
    - `GOTO_URL "URL"`: Navigates to a new URL.
    - `DONE`: Indicates the task is complete or the model is stuck.
- Executes actions using Playwright.
- Scales screenshots for consistent processing by Gemini.
- Annotates screenshots with red circles to indicate where CLICK, TYPE, or HOVER actions were performed based on Gemini's coordinates.
- Saves both unannotated and annotated screenshots for each step of the automation process.
- Provides console output detailing the actions being taken.

## Requirements

- Python 3.7+
- Google Generative AI SDK: `google-generativeai`
- Playwright: `playwright`
- Pillow (PIL Fork): `Pillow`
- Python Dotenv: `python-dotenv`

## Installation

1.  Clone or download this repository.
2.  Install the required Python dependencies:
    ```bash
    pip install google-generativeai playwright Pillow python-dotenv
    ```
3.  Install Playwright browsers (will install Chromium, Firefox, WebKit by default):
    ```bash
    playwright install
    ```
4.  Create a `.env` file in the root directory of the project and add your Gemini API key:
    ```
    GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```
    You can obtain an API key from [Google AI Studio](https://aistudio.google.com/app/apikey).

## Usage

To run the web automation script, execute `gemini-visual.py` from your terminal. The script takes a user-defined goal as an argument in the `main` function.

1.  Modify the `user_goal` variable in the `if __name__ == "__main__":` block at the bottom of `gemini-visual.py` with your desired task. For example:
    ```python
    # filepath: c:\Users\HP\Downloads\uicheck\gemini-visual.py
    # ...
    if __name__ == "__main__":
        user_goal = "Navigate to the Google homepage and search for 'Playwright automation'."
        main(user_goal)
    ```
2.  Run the script:
    ```bash
    python gemini-visual.py
    ```

The script will launch a Chromium browser (by default, non-headless) and attempt to achieve the specified goal.

## Configuration

Some parameters can be configured directly in the `gemini-visual.py` script:
- `VIEWPORT_HEIGHT`, `VIEWPORT_WIDTH`: Dimensions of the browser viewport.
- `TARGET_SHORT_DIM`: The target dimension for the shortest side of the scaled screenshot sent to Gemini.
- `SCREENSHOT_DIR`: The directory where screenshots will be saved (defaults to `screenshots`).

## Output

- **Console Logs:** The script prints information about its progress, including the actions recommended by Gemini and the actions being executed.
- **Screenshots:**
    - Unannotated screenshots for each step are saved as `screenshots/unannotated_step_N.png`.
    - Annotated screenshots (for CLICK, TYPE, HOVER actions) are saved as `screenshots/annotated_step_N.png`.
    - The latest unannotated screenshot is also saved as `screenshots/last_screenshot.png`.
    - The latest annotated action screenshot is saved as `screenshots/last_annotated_action.png`.

# UI Organization Analysis Tool

This tool analyzes UI screenshots to measure how well-organized they are based on the alignment of UI elements.

## Features

- Detect UI elements in screenshots using YOLOv8
- Analyze alignment patterns (top, bottom, left, right, and center alignments)
- Identify grid-based layouts
- Generate an organization score (0-1 scale)
- Visualize aligned elements with color coding

## Installation

1. Install requirements:
   ```bash
   pip install flask ultralytics pillow matplotlib torch numpy
   ```

2. Ensure you have the YOLOv8 model in the correct location:
   ```
   weights/icon_detect/model.pt
   ```

## Usage

### Web Interface

Run the Flask application:
```bash
python flask_app.py
```

Then open your browser and go to:
```
http://127.0.0.1:5000/
```

Upload an image through the web interface to see its organization score.

### API Usage

You can also use the API endpoint directly:

```bash
curl -X POST -F "image=@path/to/your/screenshot.png" -F "tolerance=50" http://127.0.0.1:5000/api/analyze
```

### Command Line

Alternatively, you can use the organization score script directly:

```bash
python OmniParser/organization_score.py path/to/your/screenshot.png
```

## Understanding the Score

- **0.8-1.0**: Highly organized UI with clear alignment patterns
- **0.6-0.8**: Well-organized UI with good alignment
- **0.4-0.6**: Moderately organized UI
- **0.2-0.4**: Somewhat disorganized UI
- **0.0-0.2**: Poorly organized UI with few alignment patterns

## License

MIT