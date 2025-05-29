from paddleocr import PaddleOCR
import numpy as np
import cv2
import os

# Configuration
OCR_CONFIDENCE_THRESHOLD = 0.85

# Initialize OCR
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False
)

img_path = "OmniParser/pls_backup.png"

# Check if image exists
if not os.path.exists(img_path):
    print(f"Error: Image file not found at {img_path}")
    exit()

# Load the image for OpenCV processing
img = cv2.imread(img_path)
if img is None:
    print(f"Error: Could not load image from {img_path}")
    exit()

print(f"Processing image: {img_path}")
print(f"Image dimensions: {img.shape[1]}x{img.shape[0]}")

# Convert to grayscale for edge detection
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Perform Canny edge detection
edges = cv2.Canny(gray, 20, 100)

try:
    result = ocr.predict(img_path)
    np.set_printoptions(threshold=10000)

    # Create a mask to remove text areas
    mask = np.zeros_like(edges)

    print("\n--- OCR Results ---")
    text_boxes_found = 0

    for poly, text, score in zip(result[0]['rec_polys'], result[0]['rec_texts'], result[0]['rec_scores']):
        if score > OCR_CONFIDENCE_THRESHOLD:
            text_boxes_found += 1
            print(f"Text: '{text}', Score: {score:.3f}")
            print(f"Bounding box: {poly}")

            # Get bounding box coordinates
            poly_np = np.array(poly)
            x_coords = poly_np[:, 0]
            y_coords = poly_np[:, 1]

            x_min = int(np.min(x_coords))
            y_min = int(np.min(y_coords))
            x_max = int(np.max(x_coords))
            y_max = int(np.max(y_coords))

            # Expand the bounding box by a 4px margin
            margin = 4
            x_min_margin = max(0, x_min - margin)
            y_min_margin = max(0, y_min - margin)
            x_max_margin = min(img.shape[1], x_max + margin)
            y_max_margin = min(img.shape[0], y_max + margin)

            # Fill the mask within the expanded bounding box
            cv2.rectangle(mask, (x_min_margin, y_min_margin), (x_max_margin, y_max_margin), 255, -1)

    print(f"\nTotal high-confidence text boxes found: {text_boxes_found}")

    # Invert the mask so that the areas *inside* the bounding boxes are black (0)
    # and areas *outside* are white (255)
    inverted_mask = cv2.bitwise_not(mask)

    # Apply the inverted mask to the edges
    # This will keep only the edges that are *outside* the bounding boxes
    edges_without_text = cv2.bitwise_and(edges, inverted_mask)

    # Export the cleaned edge detection image
    output_path = "edges_without_text_boxes.png"
    cv2.imwrite(output_path, edges_without_text)
    print(f"\nCleaned edge detection image saved to: {output_path}")

    # Optional: Save original edges for comparison
    original_edges_path = "original_edges.png"
    cv2.imwrite(original_edges_path, edges)
    print(f"Original edges saved to: {original_edges_path}")

    # Display the results
    print("\nDisplaying results... Press any key to close windows.")
    cv2.imshow("Edges Without Text", edges_without_text)
    cv2.imshow("Original Edges", edges)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

except Exception as e:
    print(f"Error during OCR processing: {e}")