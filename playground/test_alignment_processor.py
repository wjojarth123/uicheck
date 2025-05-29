#!/usr/bin/env python3

import os
import sys
import argparse
from PIL import Image, ImageDraw
import numpy as np
from alignment_processor import (
    get_alignment_score,
    get_bounding_boxes, 
    equalize_bounding_boxes
)

def visualize_boxes(image_path, original_boxes, equalized_boxes=None, output_path=None):
    """
    Visualize the original and equalized bounding boxes on the image.
    
    Args:
        image_path: Path to the input image
        original_boxes: List of original bounding boxes
        equalized_boxes: List of equalized bounding boxes (optional)
        output_path: Path to save the visualization (optional)
    """
    try:
        # Load the image
        img = Image.open(image_path)
        
        # Create a drawing context for the original boxes
        draw = ImageDraw.Draw(img)
        
        # Draw original boxes in red
        for box in original_boxes:
            draw.rectangle([box[0], box[1], box[2], box[3]], outline='red', width=2)
        
        # If equalized boxes are provided, draw them in blue
        if equalized_boxes:
            for box in equalized_boxes:
                draw.rectangle([box[0], box[1], box[2], box[3]], outline='blue', width=1)
        
        # If output path is provided, save the image
        if output_path:
            img.save(output_path)
            print(f"Visualization saved to {output_path}")
        
        # Display the image
        img.show()
        
    except Exception as e:
        print(f"Error visualizing boxes: {e}")

def main():
    parser = argparse.ArgumentParser(description='Test the alignment processor on a screenshot')
    parser.add_argument('--image', '-i', type=str, required=True, help='Path to the screenshot to analyze')
    parser.add_argument('--model', '-m', type=str, default='model.pt', help='Path to the YOLO model weights')
    parser.add_argument('--conf', '-c', type=float, default=0.25, help='Confidence threshold for detection')
    parser.add_argument('--xtol', '-x', type=int, default=10, help='X-coordinate tolerance for clustering')
    parser.add_argument('--ytol', '-y', type=int, default=10, help='Y-coordinate tolerance for clustering')
    parser.add_argument('--visualize', '-v', action='store_true', help='Visualize the detected elements')
    parser.add_argument('--output', '-o', type=str, help='Path to save the visualization')
    
    args = parser.parse_args()
    
    # Check if the image exists
    if not os.path.exists(args.image):
        print(f"Error: Image file {args.image} not found")
        return 1
    
    # Get the alignment score
    score = get_alignment_score(
        screenshot_path=args.image,
        model_path=args.model,
        conf_threshold=args.conf,
        x_tolerance=args.xtol,
        y_tolerance=args.ytol
    )
    
    print(f"\n===== ALIGNMENT SCORE RESULTS =====")
    print(f"Image: {args.image}")
    print(f"Alignment Score (0-10): {score:.2f}")
    
    # Optionally visualize the detected elements
    if args.visualize:
        print("\nGenerating visualization...")
        
        # Get bounding boxes
        original_boxes = get_bounding_boxes(
            image_path=args.image,
            model_path=args.model,
            conf_threshold=args.conf
        )
        
        if not original_boxes:
            print("No UI elements detected for visualization.")
            return 0
        
        # Get equalized boxes
        equalized_data = equalize_bounding_boxes(
            boxes=original_boxes,
            x_tolerance=args.xtol,
            y_tolerance=args.ytol
        )
        
        if equalized_data:
            equalized_boxes, _, _ = equalized_data
            
            # Generate output path if not provided
            output_path = args.output
            if not output_path and args.image:
                base_name = os.path.splitext(args.image)[0]
                output_path = f"{base_name}_alignment_viz.png"
            
            # Visualize the boxes
            visualize_boxes(args.image, original_boxes, equalized_boxes, output_path)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
