import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from skimage.feature import canny
from skimage.morphology import dilation, closing, square
from scipy import ndimage

def detect_ui_elements(image, edge_threshold=0.2, min_area=100, max_area=None):
    """
    Detect UI elements by finding edges and grouping them.

    Parameters:
    - edge_threshold: Threshold for edge detection (0-1, lower = more sensitive)
    - min_area: Minimum area to consider as a UI element
    - max_area: Maximum area to consider as a UI element (None = no limit)
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # Apply edge detection (Canny)
    edges = canny(gray, sigma=1, low_threshold=edge_threshold*255, high_threshold=edge_threshold*255*2)

    # Dilate the edges to connect nearby components
    dilated_edges = dilation(edges, square(5))

    # Close small gaps
    closed_edges = closing(dilated_edges, square(5))

    # Label connected components
    labeled_array, num_features = ndimage.label(closed_edges)

    # Calculate properties for each component
    ui_boxes = []
    for label in range(1, num_features + 1):
        component = (labeled_array == label)
        y_indices, x_indices = np.where(component)
        if len(y_indices) == 0:
            continue

        # Calculate bounding box
        x_min, x_max = np.min(x_indices), np.max(x_indices)
        y_min, y_max = np.min(y_indices), np.max(y_indices)
        width = x_max - x_min
        height = y_max - y_min
        area = width * height

        if area >= min_area and (max_area is None or area <= max_area):
            ui_boxes.append((int(x_min), int(y_min), int(width), int(height)))

    # Merge overlapping boxes
    ui_boxes = merge_overlapping_boxes(ui_boxes)

    return ui_boxes, edges, closed_edges

def merge_overlapping_boxes(boxes, overlap_threshold=0.0):
    """
    Merge overlapping UI element boxes.
    """
    if not boxes:
        return []

    boxes = sorted(boxes, key=lambda b: b[2] * b[3])  # sort by area

    def calculate_iou(box1, box2):
        x1, y1, w1, h1 = box1
        x2, y2, w2, h2 = box2
        x_left = max(x1, x2)
        y_top = max(y1, y2)
        x_right = min(x1 + w1, x2 + w2)
        y_bottom = min(y1 + h1, y2 + h2)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection = (x_right - x_left) * (y_bottom - y_top)
        union = (w1 * h1 + w2 * h2 - intersection)
        return intersection / float(union)

    i = 0
    while i < len(boxes):
        j = i + 1
        while j < len(boxes):
            if calculate_iou(boxes[i], boxes[j]) > overlap_threshold:
                x1, y1, w1, h1 = boxes[i]
                x2, y2, w2, h2 = boxes[j]
                x_new = min(x1, x2)
                y_new = min(y1, y2)
                w_new = max(x1 + w1, x2 + w2) - x_new
                h_new = max(y1 + h1, y2 + h2) - y_new
                boxes[i] = (x_new, y_new, w_new, h_new)
                boxes.pop(j)
            else:
                j += 1
        i += 1
    return boxes

def visualize_ui_detection(image, ui_boxes, edges, closed_edges):
    """
    Visualize detected UI elements and the edge maps.
    """
    plt.figure(figsize=(14, 10))
    plt.imshow(image)
    for x, y, w, h in ui_boxes:
        rect = Rectangle((x, y), w, h, linewidth=2, edgecolor='red', facecolor='none')
        plt.gca().add_patch(rect)
    plt.title('Detected UI Elements (Red)')
    plt.axis('off')
    plt.tight_layout()
    plt.show()

    # Show edge and post-processed edge images
    plt.figure(figsize=(14, 6))
    plt.subplot(1, 2, 1)
    plt.imshow(edges, cmap='gray')
    plt.title('Edge Detection')
    plt.axis('off')

    plt.subplot(1, 2, 2)
    plt.imshow(closed_edges, cmap='gray')
    plt.title('Edges After Dilation & Closing')
    plt.axis('off')

    plt.tight_layout()
    plt.show()

def analyze_image(image_path, edge_threshold=0.2, min_area=100, max_area=None):
    """
    Analyze an image to detect UI elements only.
    """
    img = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    ui_boxes, edges, closed_edges = detect_ui_elements(
        img_rgb, edge_threshold=edge_threshold, min_area=min_area, max_area=max_area
    )

    visualize_ui_detection(img_rgb, ui_boxes, edges, closed_edges)

    return ui_boxes

# Example usage
if __name__ == "__main__":
    image_path = "OmniParser/screx.png"

    ui_elements = analyze_image(
        image_path,
        edge_threshold=0.05,
        min_area=100,
        max_area=500000
    )

    print(f"Found {len(ui_elements)} UI elements")
