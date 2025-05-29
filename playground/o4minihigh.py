import cv2
import numpy as np
import matplotlib.pyplot as plt
from paddleocr import PaddleOCR
import sys
import os

def get_text_mask(img_path, ocr_conf=0.85, margin=4):
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error: Could not load image from {img_path} in get_text_mask")
        return np.zeros((100, 100), dtype=np.uint8) # Return a dummy mask

    mask = np.zeros(img.shape[:2], np.uint8)
    
    try:
        result = ocr.predict(img_path) # Use predict instead of ocr
        # Ensure result is not None and has the expected structure
        if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            ocr_results = result[0]
            
            # Check if the necessary keys exist in the dictionary
            if 'rec_polys' in ocr_results and 'rec_texts' in ocr_results and 'rec_scores' in ocr_results:
                for poly, text, score in zip(ocr_results['rec_polys'], ocr_results['rec_texts'], ocr_results['rec_scores']):
                    if score < ocr_conf:
                        continue
                    
                    poly_np = np.array(poly, dtype=np.int32)
                    x_coords = poly_np[:, 0]
                    y_coords = poly_np[:, 1]
                    x_min = int(np.min(x_coords))
                    y_min = int(np.min(y_coords))
                    x_max = int(np.max(x_coords))
                    y_max = int(np.max(y_coords))
                    
                    x_min_margin = max(0, x_min - margin)
                    y_min_margin = max(0, y_min - margin)
                    x_max_margin = min(img.shape[1], x_max + margin)
                    y_max_margin = min(img.shape[0], y_max + margin)
                    
                    cv2.rectangle(mask, (x_min_margin, y_min_margin), (x_max_margin, y_max_margin), 255, -1)
            else:
                print("OCR result dictionary does not contain expected keys ('rec_polys', 'rec_texts', 'rec_scores').")
        else:
            print("OCR result is empty or not in the expected format.")
            
    except Exception as e:
        print(f"Error during OCR processing in get_text_mask: {e}")
        # Return an empty mask or handle error as appropriate
        return np.zeros(img.shape[:2], dtype=np.uint8)
        
    return mask

def contour_difference_sum(hsv, contour, margin=5, mask_text=None):
    mask_in = np.zeros(hsv.shape[:2], np.uint8)
    cv2.drawContours(mask_in, [contour], -1, 255, -1)
    if mask_text is not None:
        mask_in = cv2.bitwise_and(mask_in, cv2.bitwise_not(mask_text))
    pixels_in = hsv[mask_in.astype(bool)]
    if len(pixels_in) == 0:
        return 0
    x, y, w, h = cv2.boundingRect(contour)
    x0, y0 = max(x-margin, 0), max(y-margin, 0)
    x1, y1 = min(x+w+margin, hsv.shape[1]), min(y+h+margin, hsv.shape[0])
    mask_outer = np.zeros(hsv.shape[:2], np.uint8)
    cv2.rectangle(mask_outer, (x0, y0), (x1, y1), 255, -1)
    mask_outer = cv2.subtract(mask_outer, mask_in)
    if mask_text is not None:
        mask_outer = cv2.bitwise_and(mask_outer, cv2.bitwise_not(mask_text))
    pixels_out = hsv[mask_outer.astype(bool)]
    mean_out = pixels_out.mean(axis=0) if len(pixels_out) > 0 else pixels_in.mean(axis=0)
    diff_sum = np.sum(np.linalg.norm(pixels_in - mean_out, axis=1))
    return diff_sum

def process_image_with_text_mask(image_path, top_n=12, ratio_thresh=1.0, canny_lo=1, canny_hi=600, margin=5, ocr_conf=0.85):
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image at {image_path}")
        sys.exit(1)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Step 1: Get text mask
    print("Running OCR to get text mask...")
    mask_text = get_text_mask(image_path, ocr_conf=ocr_conf)

    # Step 2: Canny edge detection
    edges = cv2.Canny(blurred, canny_lo, canny_hi)

    # Step 3: Remove any edge pixels inside the text mask
    edges_masked = edges.copy()
    edges_masked[mask_text > 0] = 0

    # Step 4: Find contours only from the cleaned edge map
    contours_loose, _ = cv2.findContours(edges_masked, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Draw unfiltered contours for visualization
    img_unfiltered_contours = img.copy()
    cv2.drawContours(img_unfiltered_contours, contours_loose, -1, (0, 0, 255), 2)

    # Show unfiltered contours
    cv2.imshow("Unfiltered Contours", img_unfiltered_contours)

    # Step 5: Score contours (using HSV, ignoring text regions)
    contour_diff_sums = [
        contour_difference_sum(hsv, cnt, margin=margin, mask_text=mask_text)
        for cnt in contours_loose
    ]
    top_indices_sum = np.argsort(contour_diff_sums)[::-1][:top_n]
    final_contours_filtered = []
    for i in top_indices_sum:
        cnt = contours_loose[i]
        area = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        if perimeter > 0 and area / perimeter >= ratio_thresh:
            final_contours_filtered.append(cnt)

    # Step 6: Draw and display results
    img_final_filtered = img.copy()
    cv2.drawContours(img_final_filtered, final_contours_filtered, -1, (255, 0, 255), 3)
    
    # Optionally save output
    out_path = os.path.splitext(image_path)[0] + "_edges_masked.png"
    cv2.imwrite(out_path, img_final_filtered)
    print(f"Saved result image to {out_path}")

    # Show using OpenCV window (press any key to close)
    cv2.imshow("Result - Contours w/o Text", img_final_filtered)
    cv2.imshow("Masked Edges (no text)", edges_masked)
    cv2.imshow("Original Image", img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # Optionally show with matplotlib (remove if only using OpenCV):
    # plt.figure(figsize=(16, 8))
    # plt.imshow(cv2.cvtColor(img_final_filtered, cv2.COLOR_BGR2RGB))
    # plt.title(f'{image_path}: HSV Diff + Area/Perimeter ≥ {ratio_thresh} (Magenta) - Text masked')
    # plt.axis('off')
    # plt.show()
    return img_final_filtered, final_contours_filtered

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <image_path>")
        sys.exit(1)
    image_path = sys.argv[1]
    process_image_with_text_mask(image_path)
