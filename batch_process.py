"""
Web Element Detector - Batch Processing Script

This script processes multiple screenshots in a directory and detects web elements in each.

Usage:
    python batch_process.py --input-dir screenshots --output-dir results

Author: GitHub Copilot
Date: May 21, 2025
"""

import os
import argparse
import glob
import cv2
import numpy as np
import matplotlib.pyplot as plt
from web_element_detector import detect_web_elements


def process_directory(input_dir, output_dir, visualize=False, **kwargs):
    """
    Process all images in a directory and save results to output directory.
    
    Args:
        input_dir: Directory containing input images
        output_dir: Directory to save output images
        visualize: Whether to save visualization of detection pipeline
        **kwargs: Additional parameters to pass to detect_web_elements
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get all image files
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(input_dir, ext)))
    
    print(f"Found {len(image_files)} images to process")
    
    # Process each image
    for i, image_path in enumerate(image_files):
        print(f"Processing image {i+1}/{len(image_files)}: {image_path}")
        
        try:
            # Get filename without extension
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}_detected.png")
            
            # Detect web elements
            result_image, boxes = detect_web_elements(image_path, **kwargs)
            
            # Save result
            cv2.imwrite(output_path, result_image)
            
            # Save visualization if requested
            if visualize:
                # Read the original image
                original = cv2.imread(image_path)
                gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
                blurred = cv2.GaussianBlur(gray, (kwargs.get('gaussian_kernel', 5), kwargs.get('gaussian_kernel', 5)), 0)
                edges = cv2.Canny(blurred, kwargs.get('canny_low', 50), kwargs.get('canny_high', 150))
                
                # Apply morphological operations (simplified from main script)
                kernel = np.ones((5, 5), np.uint8)
                processed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
                processed_edges = cv2.dilate(processed_edges, np.ones((3, 3), np.uint8), iterations=1)
                
                # Save visualization
                viz_path = os.path.join(output_dir, f"{base_name}_visualization.png")
                
                plt.figure(figsize=(20, 10))
                
                plt.subplot(2, 2, 1)
                plt.imshow(cv2.cvtColor(original, cv2.COLOR_BGR2RGB))
                plt.title('Original Image')
                plt.axis('off')
                
                plt.subplot(2, 2, 2)
                plt.imshow(edges, cmap='gray')
                plt.title('Edge Detection')
                plt.axis('off')
                
                plt.subplot(2, 2, 3)
                plt.imshow(processed_edges, cmap='gray')
                plt.title('Processed Edges')
                plt.axis('off')
                
                plt.subplot(2, 2, 4)
                plt.imshow(cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB))
                plt.title(f'Detected Web Elements ({len(boxes)})')
                plt.axis('off')
                
                plt.tight_layout()
                plt.savefig(viz_path)
                plt.close()
            
            print(f"  Detected {len(boxes)} elements")
            print(f"  Saved to {output_path}")
            
        except Exception as e:
            print(f"  Error processing {image_path}: {str(e)}")


def main():
    """
    Main entry point of the script.
    """
    parser = argparse.ArgumentParser(description="Batch process images to detect web elements")
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing input images")
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save output images")
    parser.add_argument("--visualize", action="store_true", help="Save visualization of the detection pipeline")
    parser.add_argument("--gaussian", type=int, default=5, help="Gaussian blur kernel size")
    parser.add_argument("--canny-low", type=int, default=50, help="Canny low threshold")
    parser.add_argument("--canny-high", type=int, default=150, help="Canny high threshold")
    parser.add_argument("--min-area", type=int, default=100, help="Minimum contour area")
    parser.add_argument("--overlap", type=float, default=0.5, help="Overlap threshold for merging boxes")
    
    args = parser.parse_args()
    
    # Process directory
    process_directory(
        args.input_dir,
        args.output_dir,
        visualize=args.visualize,
        gaussian_kernel=args.gaussian,
        canny_low=args.canny_low,
        canny_high=args.canny_high,
        min_contour_area=args.min_area,
        overlap_threshold=args.overlap
    )


if __name__ == "__main__":
    main()
