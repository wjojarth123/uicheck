import numpy as np
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import os
import math
import copy
import torch
from sklearn.cluster import DBSCAN

def get_yolo_model(model_path):
    """
    Load a YOLOv8 model from the specified path.
    
    Args:
        model_path: Path to the model weights file
        
    Returns:
        Loaded YOLO model
    """
    try:
        # Try to import the YOLO module from ultralytics
        from ultralytics import YOLO
        
        # Load the model from the specified path
        model = YOLO(model_path)
        return model
    except ImportError:
        raise ImportError("Please install ultralytics package: pip install ultralytics")
    except Exception as e:
        raise Exception(f"Failed to load the YOLO model: {str(e)}")

def get_bounding_boxes(image_path, model_path='weights/icon_detect/model.pt', conf_threshold=0.25):
    """
    Detect UI elements in an image using a YOLO model and return their bounding boxes.
    
    Args:
        image_path: Path to the image file
        model_path: Path to the YOLO model weights file
        conf_threshold: Confidence threshold for YOLO detections (0.0 to 1.0)
        
    Returns:
        List of bounding boxes in [x1, y1, x2, y2] format
    """
    try:
        # Configure device
        device = 'cpu'  # Use 'cuda' if a CUDA-enabled GPU is available
        
        # Load the YOLO model
        print(f"Loading model from {model_path}...")
        model = get_yolo_model(model_path)
        model.to(device)
        print(f"Model loaded and moved to {device}.")
        
        # Load the image
        print(f"Loading image from {image_path}...")
        image = Image.open(image_path).convert('RGB')
        print("Image loaded successfully.")
        
        # Perform detection with the specified confidence threshold
        print(f"Performing object detection with confidence threshold: {conf_threshold}...")
        results = model.predict(image_path, device=device, conf=conf_threshold, verbose=False)
        
        detected_boxes = []
        # Ensure results are in the expected format and contain boxes
        if results and hasattr(results[0], 'boxes') and results[0].boxes is not None:
            boxes_tensor = results[0].boxes.xyxy  # Get boxes in xyxy format (x_min, y_min, x_max, y_max)
            if boxes_tensor.numel() > 0: # Check if the tensor is not empty
                detected_boxes = boxes_tensor.cpu().tolist()
                print(f"Detected {len(detected_boxes)} bounding boxes.")
            else:
                print("No bounding boxes detected in the image.")
        else:
            print("Prediction did not return any boxes or the result format is unexpected.")
        
        return detected_boxes
    
    except Exception as e:
        print(f"Error detecting bounding boxes: {e}")
        return []

def cluster_by_coordinates(boxes, x_tolerance=10, y_tolerance=10):
    """
    Cluster UI elements by their X and Y coordinates independently.
    Find elements with similar X coordinates and similar Y coordinates.
    
    Args:
        boxes: List of bounding boxes in [x1, y1, x2, y2] format
        x_tolerance: Maximum difference in pixels to consider X coordinates similar
        y_tolerance: Maximum difference in pixels to consider Y coordinates similar
        
    Returns:
        A tuple of (x_clusters, y_clusters), where each cluster is a list of box indices
    """
    if not boxes:
        return [], []
    
    num_boxes = len(boxes)
    
    # Extract X and Y coordinates (using left, top, right, bottom edges and centers)
    x_left = [box[0] for box in boxes]
    y_top = [box[1] for box in boxes]
    x_right = [box[2] for box in boxes]
    y_bottom = [box[3] for box in boxes]
    x_center = [(box[0] + box[2]) / 2 for box in boxes]
    y_center = [(box[1] + box[3]) / 2 for box in boxes]
    
    # Function to cluster coordinates
    def cluster_coordinates(coordinates, tolerance):
        # Sort coordinates and their indices
        sorted_coords_with_indices = sorted(enumerate(coordinates), key=lambda x: x[1])
        
        clusters = []
        current_cluster = [sorted_coords_with_indices[0][0]]  # Start with first box index
        current_value = sorted_coords_with_indices[0][1]      # Start with first coordinate value
        
        # Group adjacent coordinates within tolerance
        for i in range(1, len(sorted_coords_with_indices)):
            idx, value = sorted_coords_with_indices[i]
            
            if value - current_value <= tolerance:
                # Add to current cluster if within tolerance
                current_cluster.append(idx)
            else:
                # Start a new cluster if beyond tolerance
                if len(current_cluster) >= 2:  # Only keep clusters with at least 2 elements
                    clusters.append(sorted(current_cluster))
                current_cluster = [idx]
                current_value = value
        
        # Add the last cluster if it has at least 2 elements
        if len(current_cluster) >= 2:
            clusters.append(sorted(current_cluster))
            
        return clusters
    
    # Cluster boxes by different coordinate types
    x_left_clusters = cluster_coordinates(x_left, x_tolerance)
    x_right_clusters = cluster_coordinates(x_right, x_tolerance)
    x_center_clusters = cluster_coordinates(x_center, x_tolerance)
    
    y_top_clusters = cluster_coordinates(y_top, y_tolerance)
    y_bottom_clusters = cluster_coordinates(y_bottom, y_tolerance)
    y_center_clusters = cluster_coordinates(y_center, y_tolerance)
    
    # Combine all X clusters and all Y clusters
    x_clusters = x_left_clusters + x_right_clusters + x_center_clusters
    y_clusters = y_top_clusters + y_bottom_clusters + y_center_clusters
    
    # Remove duplicates and smaller subsets
    def remove_subsets(clusters):
        if not clusters:
            return []
        
        # Sort clusters by size (largest first)
        sorted_clusters = sorted(clusters, key=len, reverse=True)
        
        result = []
        for cluster in sorted_clusters:
            # Check if this cluster is a subset of any existing cluster
            if not any(set(cluster).issubset(set(existing)) for existing in result):
                result.append(cluster)
        
        return result
    
    x_clusters = remove_subsets(x_clusters)
    y_clusters = remove_subsets(y_clusters)
    
    return x_clusters, y_clusters
    
    # Create adjacency matrix for boxes with similar dimensions
    num_boxes = len(boxes)
    adj_matrix = [[False for _ in range(num_boxes)] for _ in range(num_boxes)]
    
    # Two boxes are considered similar if BOTH width and height are within size_tolerance of each other
    for i in range(num_boxes):
        adj_matrix[i][i] = True  # A box is similar to itself
        for j in range(i+1, num_boxes):
            # Calculate width difference as a percentage of the larger width
            width_diff_percent = abs(dimensions[i][0] - dimensions[j][0]) / max(dimensions[i][0], dimensions[j][0]) if max(dimensions[i][0], dimensions[j][0]) > 0 else 0
            
            # Calculate height difference as a percentage of the larger height
            height_diff_percent = abs(dimensions[i][1] - dimensions[j][1]) / max(dimensions[i][1], dimensions[j][1]) if max(dimensions[i][1], dimensions[j][1]) > 0 else 0
            
            # Check if both dimensions are similar enough
            if width_diff_percent <= size_tolerance and height_diff_percent <= size_tolerance:
                adj_matrix[i][j] = True
                adj_matrix[j][i] = True
    
    # Find connected components (groups of similar-sized boxes)
    size_groups = []
    visited = [False] * num_boxes
    
    for i in range(num_boxes):
        if not visited[i]:
            # Start a new group with this box
            group = []
            queue = [i]
            visited[i] = True
            
            # BFS to find all connected boxes (similar size)
            while queue:
                node = queue.pop(0)
                group.append(node)
                
                for j in range(num_boxes):
                    if adj_matrix[node][j] and not visited[j]:
                        visited[j] = True
                        queue.append(j)
            
            # Only add groups with at least 2 boxes
            if len(group) >= 2:
                size_groups.append(sorted(group))
    
    # Sort groups by size (largest first)
    size_groups.sort(key=len, reverse=True)
    
    # Print size groups
    print(f"Found {len(size_groups)} size groups")
    for i, group in enumerate(size_groups):
        # Calculate average dimensions for this group
        total_width = 0
        total_height = 0
        
        for idx in group:
            width, height = dimensions[idx]
            total_width += width
            total_height += height
            
        avg_width = total_width / len(group)
        avg_height = total_height / len(group)
        
        print(f"Size Group {i+1}: {len(group)} boxes, average dimensions: {avg_width:.1f}x{avg_height:.1f} pixels")
    
    # Equalize box sizes within each group
    for group in size_groups:
        if len(group) < 2:
            continue
            
        # Calculate average width and height for this group
        total_width = 0
        total_height = 0
        
        for idx in group:
            width, height = dimensions[idx]
            total_width += width
            total_height += height
            
        avg_width = total_width / len(group)
        avg_height = total_height / len(group)
        
        # Apply the average dimensions to all boxes in the group
        # while preserving their centers
        for idx in group:
            center_x = (boxes[idx][0] + boxes[idx][2]) / 2
            center_y = (boxes[idx][1] + boxes[idx][3]) / 2
            
            # Create new box with average dimensions centered at the same point
            half_width = avg_width / 2
            half_height = avg_height / 2
            
            equalized_boxes[idx][0] = center_x - half_width
            equalized_boxes[idx][1] = center_y - half_height
            equalized_boxes[idx][2] = center_x + half_width
            equalized_boxes[idx][3] = center_y + half_height
    
    return equalized_boxes

def calculate_box_dimensions(box):
    """Calculate width and height of a box [x1, y1, x2, y2]"""
    width = box[2] - box[0]
    height = box[3] - box[1]
    return width, height

def equalize_bounding_boxes(boxes, x_tolerance=10, y_tolerance=10):
    """
    Cluster UI elements by their X and Y coordinates independently and equalize their positions.
    
    Args:
        boxes: List of bounding boxes in [x1, y1, x2, y2] format
        x_tolerance: Maximum difference in pixels to consider X coordinates similar
        y_tolerance: Maximum difference in pixels to consider Y coordinates similar
        
    Returns:
        Tuple of (equalized_boxes, x_clusters, y_clusters)
    """
    if not boxes or len(boxes) < 2:
        return boxes, [], []
    
    # Create a deep copy to avoid modifying the original list
    equalized_boxes = copy.deepcopy(boxes)
    
    # Cluster boxes by X and Y coordinates
    x_clusters, y_clusters = cluster_by_coordinates(boxes, x_tolerance, y_tolerance)
    
    # Print information about clusters
    print(f"Found {len(x_clusters)} X-coordinate clusters and {len(y_clusters)} Y-coordinate clusters")
    
    # Process X clusters
    for i, cluster in enumerate(x_clusters):
        if len(cluster) < 2:
            continue
            
        # Determine if this is a left, right, or center alignment cluster
        # Calculate average positions for all three types
        avg_left = sum(boxes[idx][0] for idx in cluster) / len(cluster)
        avg_right = sum(boxes[idx][2] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][0] + boxes[idx][2]) / 2 for idx in cluster) / len(cluster)
        
        # Find which alignment has the smallest standard deviation
        left_std = sum((boxes[idx][0] - avg_left) ** 2 for idx in cluster) ** 0.5
        right_std = sum((boxes[idx][2] - avg_right) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][0] + boxes[idx][2]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        min_std = min(left_std, right_std, center_std)
        
        if min_std == left_std:
            # Left edge alignment
            print(f"X Cluster {i+1}: {len(cluster)} boxes aligned by left edge at x={avg_left:.1f}")
            for idx in cluster:
                # Calculate the shift in x position
                shift = avg_left - boxes[idx][0]
                # Apply the shift to both left and right coordinates
                equalized_boxes[idx][0] = avg_left
                equalized_boxes[idx][2] = boxes[idx][2] + shift
                
        elif min_std == right_std:
            # Right edge alignment
            print(f"X Cluster {i+1}: {len(cluster)} boxes aligned by right edge at x={avg_right:.1f}")
            for idx in cluster:
                # Calculate the shift in x position
                shift = avg_right - boxes[idx][2]
                # Apply the shift to both left and right coordinates
                equalized_boxes[idx][2] = avg_right
                equalized_boxes[idx][0] = boxes[idx][0] + shift
                
        else:
            # Center alignment
            print(f"X Cluster {i+1}: {len(cluster)} boxes aligned by center at x={avg_center:.1f}")
            for idx in cluster:
                # Calculate the current width
                width = boxes[idx][2] - boxes[idx][0]
                # Center the box at the average center
                equalized_boxes[idx][0] = avg_center - width / 2
                equalized_boxes[idx][2] = avg_center + width / 2
    
    # Process Y clusters
    for i, cluster in enumerate(y_clusters):
        if len(cluster) < 2:
            continue
            
        # Determine if this is a top, bottom, or center alignment cluster
        # Calculate average positions for all three types
        avg_top = sum(boxes[idx][1] for idx in cluster) / len(cluster)
        avg_bottom = sum(boxes[idx][3] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][1] + boxes[idx][3]) / 2 for idx in cluster) / len(cluster)
        
        # Find which alignment has the smallest standard deviation
        top_std = sum((boxes[idx][1] - avg_top) ** 2 for idx in cluster) ** 0.5
        bottom_std = sum((boxes[idx][3] - avg_bottom) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][1] + boxes[idx][3]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        min_std = min(top_std, bottom_std, center_std)
        
        if min_std == top_std:
            # Top edge alignment
            print(f"Y Cluster {i+1}: {len(cluster)} boxes aligned by top edge at y={avg_top:.1f}")
            for idx in cluster:
                # Calculate the shift in y position
                shift = avg_top - boxes[idx][1]
                # Apply the shift to both top and bottom coordinates
                equalized_boxes[idx][1] = avg_top
                equalized_boxes[idx][3] = boxes[idx][3] + shift
                
        elif min_std == bottom_std:
            # Bottom edge alignment
            print(f"Y Cluster {i+1}: {len(cluster)} boxes aligned by bottom edge at y={avg_bottom:.1f}")
            for idx in cluster:
                # Calculate the shift in y position
                shift = avg_bottom - boxes[idx][3]
                # Apply the shift to both top and bottom coordinates
                equalized_boxes[idx][3] = avg_bottom
                equalized_boxes[idx][1] = boxes[idx][1] + shift
                  else:
            # Center alignment
            print(f"Y Cluster {i+1}: {len(cluster)} boxes aligned by center at y={avg_center:.1f}")
            for idx in cluster:
                # Calculate the current height
                height = boxes[idx][3] - boxes[idx][1]
                # Center the box at the average center
                equalized_boxes[idx][1] = avg_center - height / 2
                equalized_boxes[idx][3] = avg_center + height / 2
    
    return equalized_boxes, x_clusters, y_clusters

def display_bounding_boxes(image_path, boxes, equalized_boxes=None, ladder_rungs=None, title="Detected UI Elements"):
    """
    Display the image with bounding boxes.
    
    Args:
        image_path: Path to the image file
        boxes: Original bounding boxes
        equalized_boxes: Equalized bounding boxes (optional)
        ladder_rungs: Tuple of (x_values, y_values, common_widths, common_heights) for alignment grid (optional)
        title: Plot title
    """
    try:
        # Load the image with PIL for display
        image = Image.open(image_path).convert('RGB')
        
        if equalized_boxes is not None:
            # Create two subplots
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
            
            # Draw original boxes on the left subplot
            img1 = image.copy()
            draw1 = ImageDraw.Draw(img1)
            for box in boxes:
                draw1.rectangle([box[0], box[1], box[2], box[3]], outline='red', width=2)
            
            ax1.imshow(img1)
            ax1.set_title("Original Bounding Boxes")
            ax1.axis('off')
            
            # Draw equalized boxes on the right subplot
            img2 = image.copy()
            draw2 = ImageDraw.Draw(img2)
            
            # Draw the alignment grid if provided
            if ladder_rungs:
                x_values, y_values, common_widths, common_heights = ladder_rungs
                
                # Draw vertical lines for X coordinates (position ladder rungs)
                for x in x_values:
                    for y_start in range(0, image.height, 10):  # Dashed line
                        y_end = min(y_start + 5, image.height)
                        draw2.line([(x, y_start), (x, y_end)], fill='#FF00FF80', width=1)  # Light magenta
                
                # Draw horizontal lines for Y coordinates (position ladder rungs)
                for y in y_values:
                    for x_start in range(0, image.width, 10):  # Dashed line
                        x_end = min(x_start + 5, image.width)
                        draw2.line([(x_start, y), (x_end, y)], fill='#FF00FF80', width=1)  # Light magenta
                
                # Add width dimension ladder rungs at the top
                for idx, (width_val, count, _) in enumerate(common_widths[:3]):  # Show top 3 common widths
                    # Draw at the top of the image with some padding
                    y_pos = 20 + idx * 30
                    x_center = image.width // 2
                    x_start = x_center - width_val / 2
                    x_end = x_center + width_val / 2
                    
                    # Draw the width line
                    draw2.line([(x_start, y_pos), (x_end, y_pos)], fill='#00FF00', width=2)  # Green
                    
                    # Draw the end ticks
                    draw2.line([(x_start, y_pos-5), (x_start, y_pos+5)], fill='#00FF00', width=2)
                    draw2.line([(x_end, y_pos-5), (x_end, y_pos+5)], fill='#00FF00', width=2)
                    
                    # Add text label
                    draw2.text((x_center, y_pos-15), f"W: {width_val:.1f}px ({count})", fill='#00FF00', anchor="mm")
                
                # Add height dimension ladder rungs at the left side
                for idx, (height_val, count, _) in enumerate(common_heights[:3]):  # Show top 3 common heights
                    # Draw at the left of the image with some padding
                    x_pos = 20 + idx * 30
                    y_center = image.height // 2
                    y_start = y_center - height_val / 2
                    y_end = y_center + height_val / 2
                    
                    # Draw the height line
                    draw2.line([(x_pos, y_start), (x_pos, y_end)], fill='#00FFFF', width=2)  # Cyan
                    
                    # Draw the end ticks
                    draw2.line([(x_pos-5, y_start), (x_pos+5, y_start)], fill='#00FFFF', width=2)
                    draw2.line([(x_pos-5, y_end), (x_pos+5, y_end)], fill='#00FFFF', width=2)
                    
                    # Add text label (rotated)
                    # Since PIL doesn't easily support rotated text, we'll use a horizontal label
                    draw2.text((x_pos-15, y_center), f"H: {height_val:.1f}px ({count})", fill='#00FFFF', anchor="rm")
            
            # Draw the equalized boxes on top of the grid
            for box in equalized_boxes:
                draw2.rectangle([box[0], box[1], box[2], box[3]], outline='blue', width=2)
            
            # Add legend
            legend_y = image.height - 60
            # Position rungs
            draw2.line([(10, legend_y), (30, legend_y)], fill='#FF00FF80', width=1)
            draw2.text((35, legend_y), "Position ladder rungs", fill='#FF00FF')
            # Width rungs
            draw2.line([(10, legend_y+15), (30, legend_y+15)], fill='#00FF00', width=2)
            draw2.text((35, legend_y+15), "Width ladder rungs", fill='#00FF00')
            # Height rungs
            draw2.line([(10, legend_y+30), (30, legend_y+30)], fill='#00FFFF', width=2)
            draw2.text((35, legend_y+30), "Height ladder rungs", fill='#00FFFF')
            
            ax2.imshow(img2)
            grid_text = " with Alignment Grid" if ladder_rungs else ""
            ax2.set_title(f"Equalized Bounding Boxes{grid_text}")
            ax2.axis('off')
            
        else:
            # Single plot for original boxes only
            fig, ax = plt.subplots(figsize=(10, 8))
            img = image.copy()
            draw = ImageDraw.Draw(img)
            
            for box in boxes:
                draw.rectangle([box[0], box[1], box[2], box[3]], outline='red', width=2)
            
            ax.imshow(img)
            ax.set_title(title)
            ax.axis('off')
        
        plt.tight_layout()
        plt.show()
        
        # Save the output
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract the image filename without extension
        img_filename = os.path.basename(image_path)
        img_name, _ = os.path.splitext(img_filename)
        
        if equalized_boxes is not None:
            output_path = os.path.join(output_dir, f"{img_name}_equalized.png")
            img2.save(output_path)
            print(f"Image with equalized boxes saved to: {output_path}")
        
    except Exception as e:
        print(f"Error displaying bounding boxes: {e}")

def display_alignment_grid(equalized_boxes, x_clusters, y_clusters, boxes):
    """
    Prints the "ladder rungs" - the X and Y values that elements were aligned to.
    Also identifies common widths and heights of boxes.
    
    Args:
        equalized_boxes: List of equalized bounding boxes
        x_clusters: List of X-coordinate clusters
        y_clusters: List of Y-coordinate clusters
        boxes: Original list of boxes
    
    Returns:
        Tuple of (x_values, y_values, common_widths, common_heights) for visualization
    """
    # Get all the unique X and Y alignment values from the equalized boxes
    x_values = set()
    y_values = set()
    
    # Process X clusters
    for i, cluster in enumerate(x_clusters):
        if len(cluster) < 2:
            continue
            
        # Determine if this is a left, right, or center alignment
        avg_left = sum(boxes[idx][0] for idx in cluster) / len(cluster)
        avg_right = sum(boxes[idx][2] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][0] + boxes[idx][2]) / 2 for idx in cluster) / len(cluster)
        
        # Find which alignment has the smallest standard deviation
        left_std = sum((boxes[idx][0] - avg_left) ** 2 for idx in cluster) ** 0.5
        right_std = sum((boxes[idx][2] - avg_right) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][0] + boxes[idx][2]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        min_std = min(left_std, right_std, center_std)
        
        if min_std == left_std:
            x_values.add(round(avg_left, 1))
        elif min_std == right_std:
            x_values.add(round(avg_right, 1))
        else:
            x_values.add(round(avg_center, 1))
    
    # Process Y clusters
    for i, cluster in enumerate(y_clusters):
        if len(cluster) < 2:
            continue
            
        # Determine if this is a top, bottom, or center alignment
        avg_top = sum(boxes[idx][1] for idx in cluster) / len(cluster)
        avg_bottom = sum(boxes[idx][3] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][1] + boxes[idx][3]) / 2 for idx in cluster) / len(cluster)
        
        # Find which alignment has the smallest standard deviation
        top_std = sum((boxes[idx][1] - avg_top) ** 2 for idx in cluster) ** 0.5
        bottom_std = sum((boxes[idx][3] - avg_bottom) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][1] + boxes[idx][3]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        min_std = min(top_std, bottom_std, center_std)
        
        if min_std == top_std:
            y_values.add(round(avg_top, 1))
        elif min_std == bottom_std:
            y_values.add(round(avg_bottom, 1))
        else:
            y_values.add(round(avg_center, 1))
    
    # Sort the values
    sorted_x = sorted(list(x_values))
    sorted_y = sorted(list(y_values))
    
    # Calculate common widths and heights (dimension "ladder rungs")
    width_values = []
    height_values = []
    
    # Extract all widths and heights
    for box in boxes:
        width = box[2] - box[0]
        height = box[3] - box[1]
        width_values.append(round(width, 1))
        height_values.append(round(height, 1))
    
    # Find common widths and heights using clustering
    def find_common_dimensions(dimension_values, tolerance=5.0):
        if not dimension_values:
            return []
            
        # Sort the values
        sorted_values = sorted(dimension_values)
        
        # Group similar values
        groups = []
        current_group = [sorted_values[0]]
        
        for i in range(1, len(sorted_values)):
            if sorted_values[i] - sorted_values[i-1] <= tolerance:
                current_group.append(sorted_values[i])
            else:
                if len(current_group) >= 2:  # Only keep groups with at least 2 members
                    groups.append(current_group)
                current_group = [sorted_values[i]]
                
        # Add the last group if it has at least 2 members
        if len(current_group) >= 2:
            groups.append(current_group)
            
        # Calculate average for each group
        common_values = []
        for group in groups:
            avg_value = sum(group) / len(group)
            count = len(group)  # How many in this group
            freq = count / len(dimension_values)  # Frequency as a proportion
            common_values.append((round(avg_value, 1), count, freq))
            
        # Sort by frequency (most common first)
        return sorted(common_values, key=lambda x: x[1], reverse=True)
    
    common_widths = find_common_dimensions(width_values)
    common_heights = find_common_dimensions(height_values)
    
    # Print the alignment grid
    print("\n=== UI ELEMENT ALIGNMENT GRID ===")
    print("X-coordinate 'ladder rungs':")
    for i, x in enumerate(sorted_x):
        print(f"  X{i+1}: {x}")
    
    print("\nY-coordinate 'ladder rungs':")
    for i, y in enumerate(sorted_y):
        print(f"  Y{i+1}: {y}")
    
    # Print the dimension ladder rungs
    print("\n=== UI ELEMENT DIMENSION LADDER RUNGS ===")
    print("Common widths:")
    for i, (width, group_size, freq) in enumerate(common_widths):
        percentage = freq * 100
        print(f"  Width{i+1}: {width} pixels (found in {group_size} elements, {percentage:.1f}% of elements)")
    
    print("\nCommon heights:")
    for i, (height, group_size, freq) in enumerate(common_heights):
        percentage = freq * 100
        print(f"  Height{i+1}: {height} pixels (found in {group_size} elements, {percentage:.1f}% of elements)")
    
    # Calculate grid density statistics
    if sorted_x and sorted_y:
        # Calculate average spacing
        avg_x_spacing = (sorted_x[-1] - sorted_x[0]) / (len(sorted_x) - 1) if len(sorted_x) > 1 else 0
        avg_y_spacing = (sorted_y[-1] - sorted_y[0]) / (len(sorted_y) - 1) if len(sorted_y) > 1 else 0
        
        print(f"\nGrid statistics:")
        print(f"  Total ladder rungs: {len(sorted_x)} horizontal, {len(sorted_y)} vertical")
        if len(sorted_x) > 1:
            print(f"  Horizontal spacing: min={min([sorted_x[i+1]-sorted_x[i] for i in range(len(sorted_x)-1)]):.1f}, " +
                  f"max={max([sorted_x[i+1]-sorted_x[i] for i in range(len(sorted_x)-1)]):.1f}, " +
                  f"avg={avg_x_spacing:.1f}")
        if len(sorted_y) > 1:
            print(f"  Vertical spacing: min={min([sorted_y[i+1]-sorted_y[i] for i in range(len(sorted_y)-1)]):.1f}, " +
                  f"max={max([sorted_y[i+1]-sorted_y[i] for i in range(len(sorted_y)-1)]):.1f}, " +
                  f"avg={avg_y_spacing:.1f}")
    
    return sorted_x, sorted_y, common_widths, common_heights

def main(image_path=None, model_path=None, conf_threshold=0.25, x_tolerance=10, y_tolerance=10):
    """
    Main function to process the image and display results.
    
    Args:
        image_path: Path to the image file (optional)
        model_path: Path to the YOLO model weights file (optional)
        conf_threshold: Confidence threshold for YOLO detections (0.0 to 1.0)
        x_tolerance: Maximum difference in pixels to consider X coordinates similar
        y_tolerance: Maximum difference in pixels to consider Y coordinates similar
    """
    # Default paths
    if image_path is None:
        image_path = 'imgs/teams.png'
    
    if model_path is None:
        model_path = 'weights/icon_detect/model.pt'
    
    print(f"Processing image: {image_path}")
    print(f"Using model: {model_path}")
    print(f"Confidence threshold: {conf_threshold}")
    print(f"X tolerance: {x_tolerance} pixels, Y tolerance: {y_tolerance} pixels")
    
    # Get original bounding boxes using YOLO model with the specified confidence threshold
    original_boxes = get_bounding_boxes(image_path, model_path, conf_threshold)
    
    if not original_boxes:
        print("No UI elements detected. Please try a different image, model, or lower the confidence threshold.")
        return
    
    # Print sample boxes for debugging
    print("\nSample Box Coordinates:")
    for i in range(min(5, len(original_boxes))):
        print(f"Box {i}: {original_boxes[i]}")
    
    # Equalize by X and Y coordinates
    equalized_boxes, x_clusters, y_clusters = equalize_bounding_boxes(original_boxes, x_tolerance, y_tolerance)
    
    # Print the alignment grid (ladder rungs)
    ladder_rungs = display_alignment_grid(equalized_boxes, x_clusters, y_clusters, original_boxes)
    
    # Display results
    display_bounding_boxes(image_path, original_boxes, equalized_boxes, ladder_rungs,
                          title=f"UI Elements (conf={conf_threshold}, x_tol={x_tolerance}, y_tol={y_tolerance})")
    
    print("Processing complete.")

if __name__ == "__main__":
    import sys
    import argparse
    
    # Create command-line argument parser
    parser = argparse.ArgumentParser(description='UI Element Equalizer')
    parser.add_argument('--image', type=str, help='Path to the image file')
    parser.add_argument('--model', type=str, help='Path to the YOLO model weights file')
    parser.add_argument('--conf', type=float, default=0.25, help='Confidence threshold for YOLO (0.0-1.0)')
    parser.add_argument('--xtol', type=int, default=10, help='X coordinate tolerance in pixels')
    parser.add_argument('--ytol', type=int, default=10, help='Y coordinate tolerance in pixels')
    
    # Parse arguments
    args = parser.parse_args()
    
    if args.image:
        main(args.image, args.model, args.conf, args.xtol, args.ytol)
    else:
        main()
