# Web Element Detector

This tool detects and generates bounding boxes around web UI elements in screenshots using computer vision techniques. It uses edge detection with Canny, Gaussian blur, and other image processing techniques to identify rectangular UI elements.

## Features

- **Gaussian Blur**: Reduces noise and improves edge detection quality
- **Canny Edge Detection**: Identifies element boundaries
- **Morphological Operations**: Enhances detection by closing small gaps and connecting edges
- **Contour Detection**: Finds the outlines of web elements
- **Optional Box Merging**: Can optionally merge overlapping boxes or keep them separate (great for text with large fonts)
- **Visualization**: Optional pipeline visualization showing each step of the process

## Installation

1. Make sure you have Python 3.6+ installed
2. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Basic usage:

```bash
python web_element_detector.py --image path/to/screenshot.png --output path/to/output.png
```

Advanced usage with all parameters:

```bash
python web_element_detector.py \
    --image path/to/screenshot.png \
    --output path/to/output.png \
    --visualize \
    --gaussian 5 \
    --canny-low 50 \
    --canny-high 150 \
    --min-area 100 \
    --merge-boxes \
    --overlap 0.5
```

## Parameters

- `--image`: Path to the input image (required)
- `--output`: Path to save the output image (default: output.png)
- `--visualize`: Save visualization of the detection pipeline (optional)
- `--gaussian`: Gaussian blur kernel size (default: 5)
- `--canny-low`: Canny low threshold (default: 50)
- `--canny-high`: Canny high threshold (default: 150)
- `--min-area`: Minimum contour area (default: 100)
- `--merge-boxes`: Whether to merge overlapping boxes (disabled by default)
- `--overlap`: Overlap threshold for merging boxes (default: 0.5, only used if --merge-boxes is specified)

## How It Works

1. **Preprocessing**: The input image is converted to grayscale and blurred with a Gaussian filter to reduce noise.
2. **Edge Detection**: Canny edge detection identifies edges in the image.
3. **Morphological Operations**: Closing and dilation operations enhance edges and close small gaps.
4. **Contour Detection**: External contours are found in the processed edge map.
5. **Filtering**: Contours are filtered based on area and aspect ratio to eliminate noise.
6. **Bounding Box Extraction**: Bounding boxes are generated from the filtered contours.
7. **Box Merging (Optional)**: If enabled, overlapping boxes are merged based on the Intersection over Union (IoU) metric. For text with large fonts, disable this to keep each word in its own bounding box.
8. **Visualization**: The final bounding boxes are drawn on the original image.

## Example

```bash
python web_element_detector.py --image screenshots/webpage.png --output detected_elements.png --visualize
```

This will:
1. Process the screenshot at `screenshots/webpage.png`
2. Draw bounding boxes around detected web elements
3. Save the result to `detected_elements.png`
4. Create a visualization of the detection pipeline at `detected_elements_visualization.png`

## Integration with Other Tools

You can easily integrate this detector with other tools in your web UI testing pipeline:

```python
from web_element_detector import detect_web_elements

# Detect elements in a screenshot without merging boxes (great for text)
image, boxes = detect_web_elements('screenshot.png', merge_boxes=False)

# Or with box merging for other UI elements
# image, boxes = detect_web_elements('screenshot.png', merge_boxes=True, overlap_threshold=0.5)

# Process the detected boxes
for box in boxes:
    x1, y1, x2, y2 = box
    # Do something with the detected element...
```

## Tuning for Different Websites

Different websites may require different parameter tuning:

- For websites with low contrast, try decreasing `--canny-low` and `--canny-high`
- For websites with small UI elements, decrease `--min-area`
- For text-heavy websites with large fonts, disable box merging to keep each word in its own bounding box (don't use `--merge-boxes`)
- For websites with densely packed elements that should be merged, use `--merge-boxes` and adjust `--overlap` as needed
