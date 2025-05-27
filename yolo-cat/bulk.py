from paddleocr import PaddleOCR
import numpy as np
import cv2
import os
import argparse
from pathlib import Path

# Configuration
OCR_CONFIDENCE_THRESHOLD = 0.85
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}

# Initialize OCR
ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False
)

def get_edge_bounding_boxes(edges, min_contour_area=50, approx_epsilon_factor=0.02):
    """
    Generate bounding boxes for edge shapes/contours
    """
    # Find contours from the edge image
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bounding_boxes = []
    
    for contour in contours:
        # Filter out very small contours
        area = cv2.contourArea(contour)
        if area < min_contour_area:
            continue
            
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        
        # Optional: Use approx polygon to get better fitting boxes for specific shapes
        epsilon = approx_epsilon_factor * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        
        # For pill/rounded shapes, the bounding rect works well
        # You could add shape classification here if needed
        
        bounding_boxes.append({
            'bbox': (x, y, w, h),
            'contour': contour,
            'area': area,
            'approx_vertices': len(approx)
        })
    
    return bounding_boxes

def draw_bounding_boxes(img, text_boxes, edge_boxes):
    """
    Draw both text and edge bounding boxes on the image
    """
    result_img = img.copy()
    
    # Draw text bounding boxes in green
    for box in text_boxes:
        poly = box['poly']
        text = box['text']
        score = box['score']
        
        # Convert polygon to bounding rectangle
        poly_np = np.array(poly)
        x_coords = poly_np[:, 0]
        y_coords = poly_np[:, 1]
        
        x_min = int(np.min(x_coords))
        y_min = int(np.min(y_coords))
        x_max = int(np.max(x_coords))
        y_max = int(np.max(y_coords))
        
        # Draw rectangle and label
        cv2.rectangle(result_img, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
        cv2.putText(result_img, f"TEXT: {score:.2f}", (x_min, y_min-5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    
    # Draw edge bounding boxes in red
    for i, box in enumerate(edge_boxes):
        x, y, w, h = box['bbox']
        area = box['area']
        vertices = box['approx_vertices']
        
        cv2.rectangle(result_img, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(result_img, f"EDGE: A={int(area)}", (x, y-5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    
    return result_img

def process_single_image(img_path, output_dir, debug=False):
    """
    Process a single image for OCR and edge detection
    """
    print(f"\nProcessing: {img_path}")
    
    # Load the image
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"Error: Could not load image from {img_path}")
        return False
    
    print(f"Image dimensions: {img.shape[1]}x{img.shape[0]}")
    
    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Perform Canny edge detection
    edges = cv2.Canny(gray, 20, 100)
    
    try:
        # OCR Processing
        result = ocr.predict(str(img_path))
        
        # Create a mask to remove text areas
        mask = np.zeros_like(edges)
        text_boxes = []
        
        print("--- OCR Results ---")
        text_boxes_found = 0
        
        for poly, text, score in zip(result[0]['rec_polys'], result[0]['rec_texts'], result[0]['rec_scores']):
            if score > OCR_CONFIDENCE_THRESHOLD:
                text_boxes_found += 1
                print(f"Text: '{text}', Score: {score:.3f}")
                
                text_boxes.append({
                    'poly': poly,
                    'text': text,
                    'score': score
                })
                
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
        
        print(f"Total high-confidence text boxes found: {text_boxes_found}")
        
        # Clean edges by removing text areas
        inverted_mask = cv2.bitwise_not(mask)
        edges_without_text = cv2.bitwise_and(edges, inverted_mask)
        
        # Generate bounding boxes for edge shapes
        edge_boxes = get_edge_bounding_boxes(edges_without_text)
        print(f"Edge bounding boxes found: {len(edge_boxes)}")
        
        # Draw all bounding boxes on the image
        annotated_img = draw_bounding_boxes(img, text_boxes, edge_boxes)
        
        # Save the annotated image
        img_name = Path(img_path).stem
        output_path = output_dir / f"{img_name}_annotated.png"
        cv2.imwrite(str(output_path), annotated_img)
        print(f"Annotated image saved to: {output_path}")
        
        # Save debug images if debug flag is set
        if debug:
            # Save cleaned edges
            edges_path = output_dir / f"{img_name}_edges_cleaned.png"
            cv2.imwrite(str(edges_path), edges_without_text)
            print(f"Cleaned edges saved to: {edges_path}")
            
            # Save original edges for comparison
            original_edges_path = output_dir / f"{img_name}_edges_original.png"
            cv2.imwrite(str(original_edges_path), edges)
            print(f"Original edges saved to: {original_edges_path}")
            
            # Save text mask for debugging
            mask_path = output_dir / f"{img_name}_text_mask.png"
            cv2.imwrite(str(mask_path), mask)
            print(f"Text mask saved to: {mask_path}")
        
        return True
        
    except Exception as e:
        print(f"Error during processing: {e}")
        return False

def process_directory(input_dir, output_dir=None, debug=False):
    """
    Process all images in a directory
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        return
    
    if not input_path.is_dir():
        print(f"Error: '{input_dir}' is not a directory")
        return
    
    # Create output directory
    if output_dir is None:
        output_dir = input_path / "annotated_output"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # Find all image files
    image_files = []
    for ext in SUPPORTED_EXTENSIONS:
        image_files.extend(input_path.glob(f"*{ext}"))
        image_files.extend(input_path.glob(f"*{ext.upper()}"))
    
    if not image_files:
        print(f"No image files found in '{input_dir}'")
        print(f"Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
        return
    
    print(f"Found {len(image_files)} image files to process")
    if debug:
        print("DEBUG MODE: Will export cleaned edges and intermediate images")
    
    # Process each image
    successful = 0
    failed = 0
    
    for img_file in image_files:
        if process_single_image(img_file, output_dir, debug):
            successful += 1
        else:
            failed += 1
    
    print(f"\n=== Processing Complete ===")
    print(f"Successfully processed: {successful}")
    print(f"Failed: {failed}")
    print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Process images with OCR and edge detection')
    parser.add_argument('input_dir', help='Input directory containing images')
    parser.add_argument('-o', '--output', help='Output directory (default: input_dir/annotated_output)')
    parser.add_argument('--debug', action='store_true', help='Export cleaned edges and intermediate images')
    
    args = parser.parse_args()
    
    # Process the directory with the specified arguments
    process_directory(args.input_dir, args.output, args.debug)