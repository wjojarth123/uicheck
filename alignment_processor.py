import os
import numpy as np
import copy
from PIL import Image
from ultralytics import YOLO

# Default paths and parameters, can be overridden if needed
# These are relative to the project root (e.g., where client_endpoint.py runs)
DEFAULT_MODEL_PATH = 'model.pt'
DEFAULT_CONF_THRESHOLD = 0.25
DEFAULT_X_TOLERANCE = 10 # Pixel tolerance for X coordinate clustering
DEFAULT_Y_TOLERANCE = 10 # Pixel tolerance for Y coordinate clustering

def get_alignment_score(screenshot_path: str,
                        model_path: str = DEFAULT_MODEL_PATH,
                        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
                        x_tolerance: int = DEFAULT_X_TOLERANCE,
                        y_tolerance: int = DEFAULT_Y_TOLERANCE) -> float:
    """
    Calculates the alignment score for a given screenshot (scaled to 0-10).

    The process involves:
    1. Detecting UI elements using a YOLO model.
    2. Performing bounding box equalization based on clustering.
    3. Computing a UI consistency score (0-100) based on original vs. equalized boxes.
    4. Scaling the score to a 0-10 range.
    """
    print(f"Alignment Processor: Starting for {screenshot_path} with model {model_path}")

    # Ensure the screenshot path exists
    if not os.path.exists(screenshot_path):
        print(f"Alignment Processor: Screenshot file not found at {screenshot_path}.")
        return 0.0

    # Step 1: Get original bounding boxes
    try:
        original_boxes = get_bounding_boxes(
            image_path=screenshot_path,
            model_path=model_path,
            conf_threshold=conf_threshold
        )
    except FileNotFoundError: # Safeguard, e.g. if model_path is incorrect and YOLO raises this
        print(f"Alignment Processor: File not found error during detection (likely model at {model_path} or screenshot {screenshot_path}).")
        return 0.0
    except Exception as e:
        print(f"Alignment Processor: Error during UI element detection for {screenshot_path}: {e}")
        # Specific check for model file if detection fails broadly
        if not os.path.exists(model_path):
             print(f"Alignment Processor: YOLO model file not found at {model_path}. Ensure it's correctly placed.")
        return 0.0

    if not original_boxes:
        print(f"Alignment Processor: No UI elements detected in {screenshot_path}.")
        return 0.0
    
    print(f"Alignment Processor: Detected {len(original_boxes)} UI elements.")

    # Handle cases with few elements before attempting equalization
    if len(original_boxes) == 1:
        print("Alignment Processor: Only one UI element detected. Max alignment score (10.0).")
        return 10.0 # Perfect alignment for a single element, scaled to 0-10 range.

    # Step 2: Equalize bounding boxes
    # equalize_bounding_boxes returns: (equalized_boxes, x_clusters, y_clusters)
    # or None if len(original_boxes) < 2 (which is handled above for len 0 and 1)
    try:
        equalized_data = equalize_bounding_boxes(
            boxes=original_boxes,
            x_tolerance=x_tolerance,
            y_tolerance=y_tolerance
        )
    except Exception as e:
        print(f"Alignment Processor: Error during bounding box equalization: {e}")
        return 0.0 # Error during equalization, score 0

    if equalized_data:
        equalized_boxes, x_clusters, y_clusters = equalized_data
        print(f"Alignment Processor: Equalization complete. X-clusters: {len(x_clusters)}, Y-clusters: {len(y_clusters)}.")
    else:
        # This case implies original_boxes had >= 2 elements, but equalize_bounding_boxes returned None.
        # This would be unexpected based on its documented behavior (returns None if < 2 boxes).
        # If it occurs, it means no meaningful equalization happened.
        print("Alignment Processor: Bounding box equalization did not proceed or returned no data (unexpected for >=2 elements). Score 0.")
        return 0.0


    # Step 3: Calculate UI consistency score and scale it
    try:        # Our simplified version always returns a score (0-100)
        score_result = calculate_ui_consistency_score(
            original_boxes=original_boxes,
            equalized_boxes=equalized_boxes,
            x_clusters=x_clusters,
            y_clusters=y_clusters
        )

        if isinstance(score_result, tuple):
            raw_score_0_100 = float(score_result[0])
        else:
            raw_score_0_100 = float(score_result)

        # Scale score from 0-100 to 0-10 to match other metrics' apparent scale
        scaled_score_0_10 = raw_score_0_100 / 10.0
        
        # Clamp the score to be strictly within [0, 10]
        final_score = max(0.0, min(10.0, scaled_score_0_10))

        print(f"Alignment Processor: Raw score (0-100): {raw_score_0_100:.2f}. Scaled score (0-10): {final_score:.2f} for {screenshot_path}.")
        return final_score

    except Exception as e:
        print(f"Alignment Processor: Error calculating final UI consistency score for {screenshot_path}: {e}")
        return 0.0 # Error during final score calculation

def get_bounding_boxes(image_path, model_path=DEFAULT_MODEL_PATH, conf_threshold=DEFAULT_CONF_THRESHOLD):
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
        # Load the YOLO model
        print(f"Loading model from {model_path}...")
        model = YOLO(model_path)
        
        # Load the image
        print(f"Loading image from {image_path}...")
        
        # Perform detection with the specified confidence threshold
        print(f"Performing object detection with confidence threshold: {conf_threshold}...")
        results = model.predict(image_path, conf=conf_threshold, verbose=False)
        
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

def cluster_coordinates(coordinates, tolerance):
    """
    Cluster coordinates that are within tolerance of each other.
    
    Args:
        coordinates: List of coordinate values
        tolerance: Maximum difference to consider coordinates similar
        
    Returns:
        List of clusters, where each cluster is a list of indices
    """
    if not coordinates:
        return []
    
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

def remove_subset_clusters(clusters):
    """
    Remove clusters that are subsets of other clusters.
    
    Args:
        clusters: List of clusters
        
    Returns:
        List of clusters with subsets removed
    """
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

def extract_box_coordinates(boxes):
    """
    Extract different coordinate types from boxes.
    
    Args:
        boxes: List of bounding boxes in [x1, y1, x2, y2] format
        
    Returns:
        Dictionary of coordinate lists
    """
    coords = {
        'x_left': [box[0] for box in boxes],
        'y_top': [box[1] for box in boxes],
        'x_right': [box[2] for box in boxes],
        'y_bottom': [box[3] for box in boxes],
        'x_center': [(box[0] + box[2]) / 2 for box in boxes],
        'y_center': [(box[1] + box[3]) / 2 for box in boxes]
    }
    return coords

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
    
    # Extract all coordinate types
    coords = extract_box_coordinates(boxes)
    
    # Cluster boxes by different coordinate types
    x_left_clusters = cluster_coordinates(coords['x_left'], x_tolerance)
    x_right_clusters = cluster_coordinates(coords['x_right'], x_tolerance)
    x_center_clusters = cluster_coordinates(coords['x_center'], x_tolerance)
    
    y_top_clusters = cluster_coordinates(coords['y_top'], y_tolerance)
    y_bottom_clusters = cluster_coordinates(coords['y_bottom'], y_tolerance)
    y_center_clusters = cluster_coordinates(coords['y_center'], y_tolerance)
    
    # Combine all X clusters and all Y clusters
    x_clusters = x_left_clusters + x_right_clusters + x_center_clusters
    y_clusters = y_top_clusters + y_bottom_clusters + y_center_clusters
    
    # Remove duplicates and smaller subsets
    x_clusters = remove_subset_clusters(x_clusters)
    y_clusters = remove_subset_clusters(y_clusters)
    
    return x_clusters, y_clusters

def find_best_alignment_type(boxes, cluster, coord_type='x'):
    """
    Determine the best alignment type (left/right/center for X, top/bottom/center for Y).
    
    Args:
        boxes: List of bounding boxes
        cluster: List of box indices in the cluster
        coord_type: 'x' or 'y' to indicate coordinate type
        
    Returns:
        Tuple of (alignment_type, avg_value)
    """
    if coord_type == 'x':
        # Calculate average positions
        avg_left = sum(boxes[idx][0] for idx in cluster) / len(cluster)
        avg_right = sum(boxes[idx][2] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][0] + boxes[idx][2]) / 2 for idx in cluster) / len(cluster)
        
        # Calculate standard deviations
        left_std = sum((boxes[idx][0] - avg_left) ** 2 for idx in cluster) ** 0.5
        right_std = sum((boxes[idx][2] - avg_right) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][0] + boxes[idx][2]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        # Find which alignment has the smallest standard deviation
        min_std = min(left_std, right_std, center_std)
        
        if min_std == left_std:
            return "left", avg_left
        elif min_std == right_std:
            return "right", avg_right
        else:
            return "center", avg_center
    else:  # Y coordinates
        # Calculate average positions
        avg_top = sum(boxes[idx][1] for idx in cluster) / len(cluster)
        avg_bottom = sum(boxes[idx][3] for idx in cluster) / len(cluster)
        avg_center = sum((boxes[idx][1] + boxes[idx][3]) / 2 for idx in cluster) / len(cluster)
        
        # Calculate standard deviations
        top_std = sum((boxes[idx][1] - avg_top) ** 2 for idx in cluster) ** 0.5
        bottom_std = sum((boxes[idx][3] - avg_bottom) ** 2 for idx in cluster) ** 0.5
        center_std = sum(((boxes[idx][1] + boxes[idx][3]) / 2 - avg_center) ** 2 for idx in cluster) ** 0.5
        
        # Find which alignment has the smallest standard deviation
        min_std = min(top_std, bottom_std, center_std)
        
        if min_std == top_std:
            return "top", avg_top
        elif min_std == bottom_std:
            return "bottom", avg_bottom
        else:
            return "center", avg_center

def align_boxes_in_cluster(boxes, equalized_boxes, cluster, alignment_type, align_value, coord_type='x'):
    """
    Align boxes in a cluster according to the specified alignment type.
    
    Args:
        boxes: Original boxes
        equalized_boxes: Boxes to be modified
        cluster: List of box indices
        alignment_type: 'left', 'right', 'center', 'top', 'bottom'
        align_value: Value to align to
        coord_type: 'x' or 'y'
    """
    # First, find dimensions of elements in this cluster
    if coord_type == 'x':
        dimensions = [round(boxes[idx][2] - boxes[idx][0]) for idx in cluster]
    else:
        dimensions = [round(boxes[idx][3] - boxes[idx][1]) for idx in cluster]
    
    # Count occurrences of each dimension
    dimension_counts = {}
    for dim in dimensions:
        if dim in dimension_counts:
            dimension_counts[dim] += 1
        else:
            dimension_counts[dim] = 1
    
    # Find the most common dimension
    most_common_dim = max(dimension_counts.items(), key=lambda x: x[1])[0] if dimension_counts else 0
    
    # Apply alignment
    for idx in cluster:
        if coord_type == 'x':
            current_width = boxes[idx][2] - boxes[idx][0]
            
            if alignment_type == "left":
                equalized_boxes[idx][0] = align_value
                equalized_boxes[idx][2] = align_value + current_width
            elif alignment_type == "right":
                equalized_boxes[idx][2] = align_value
                equalized_boxes[idx][0] = align_value - current_width
            else:  # center
                half_width = current_width / 2
                equalized_boxes[idx][0] = align_value - half_width
                equalized_boxes[idx][2] = align_value + half_width
        else:  # y coordinates
            current_height = boxes[idx][3] - boxes[idx][1]
            
            if alignment_type == "top":
                equalized_boxes[idx][1] = align_value
                equalized_boxes[idx][3] = align_value + current_height
            elif alignment_type == "bottom":
                equalized_boxes[idx][3] = align_value
                equalized_boxes[idx][1] = align_value - current_height
            else:  # center
                half_height = current_height / 2
                equalized_boxes[idx][1] = align_value - half_height
                equalized_boxes[idx][3] = align_value + half_height

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
        
        # Determine the best alignment type for this cluster
        alignment_type, align_value = find_best_alignment_type(boxes, cluster, 'x')
        
        # Apply the alignment
        align_boxes_in_cluster(boxes, equalized_boxes, cluster, alignment_type, align_value, 'x')
    
    # Process Y clusters
    for i, cluster in enumerate(y_clusters):
        if len(cluster) < 2:
            continue
        
        # Determine the best alignment type for this cluster
        alignment_type, align_value = find_best_alignment_type(boxes, cluster, 'y')
        
        # Apply the alignment
        align_boxes_in_cluster(boxes, equalized_boxes, cluster, alignment_type, align_value, 'y')
    
    return equalized_boxes, x_clusters, y_clusters

def calculate_alignment_consistency_score(original_boxes, equalized_boxes, x_clusters, y_clusters):
    """
    Calculate a score for alignment consistency among UI elements.
    
    Args:
        original_boxes: List of original bounding boxes
        equalized_boxes: List of equalized bounding boxes
        x_clusters: List of X-coordinate clusters
        y_clusters: List of Y-coordinate clusters
    
    Returns:
        A score between 0 and 100 where higher values indicate better alignment
    """
    if not equalized_boxes or (not x_clusters and not y_clusters):
        return 0.0
    
    total_boxes = len(equalized_boxes)
    
    # Count boxes in the clusters (some boxes may be in multiple clusters)
    boxes_in_x_clusters = set()
    for cluster in x_clusters:
        boxes_in_x_clusters.update(cluster)
    
    boxes_in_y_clusters = set()
    for cluster in y_clusters:
        boxes_in_y_clusters.update(cluster)
    
    # Calculate alignment metrics
    
    # 1. Coverage: what percentage of boxes are in at least one alignment cluster
    all_aligned_boxes = boxes_in_x_clusters.union(boxes_in_y_clusters)
    coverage_score = len(all_aligned_boxes) / total_boxes if total_boxes > 0 else 0
    
    # 2. Alignment quality: Measure how much elements needed to be moved to achieve alignment
    
    # Calculate the average movement distance for alignment
    if original_boxes and equalized_boxes and len(original_boxes) == len(equalized_boxes):
        total_x_movement = 0
        total_y_movement = 0
        
        for i in range(len(original_boxes)):
            # X movement - left edge
            total_x_movement += abs(original_boxes[i][0] - equalized_boxes[i][0])
            # X movement - right edge
            total_x_movement += abs(original_boxes[i][2] - equalized_boxes[i][2])
            # Y movement - top edge
            total_y_movement += abs(original_boxes[i][1] - equalized_boxes[i][1])
            # Y movement - bottom edge
            total_y_movement += abs(original_boxes[i][3] - equalized_boxes[i][3])
        
        # Get average movement per edge
        avg_movement = (total_x_movement + total_y_movement) / (4 * len(original_boxes)) 
        
        # Convert movement to a 0-1 score (lower movement is better)
        # Use an exponential decay function: e^(-k*x) where k controls the decay rate
        # and x is the average movement in pixels
        decay_rate = 0.1  # Adjust this for sensitivity
        movement_score = np.exp(-decay_rate * avg_movement)
    else:
        movement_score = 0
    
    # 3. Cluster quality: More and larger clusters are better
    cluster_count_score = min(1.0, (len(x_clusters) + len(y_clusters)) / 10)  # Cap at 10 clusters combined
    
    # Calculate average cluster size
    avg_x_cluster_size = sum(len(cluster) for cluster in x_clusters) / len(x_clusters) if x_clusters else 0
    avg_y_cluster_size = sum(len(cluster) for cluster in y_clusters) / len(y_clusters) if y_clusters else 0
    avg_cluster_size = (avg_x_cluster_size + avg_y_cluster_size) / 2 if (x_clusters or y_clusters) else 0
    
    # Normalize by total boxes
    cluster_size_score = min(1.0, avg_cluster_size / (total_boxes / 2)) if total_boxes > 0 else 0
    
    # Combine all metrics with weights
    final_score = (
        0.4 * coverage_score + 
        0.4 * movement_score + 
        0.1 * cluster_count_score + 
        0.1 * cluster_size_score
    ) * 100  # Scale to 0-100
    
    # Clamp the score between 0 and 100
    final_score = max(0, min(100, final_score))
    
    return final_score

def calculate_ui_consistency_score(original_boxes, equalized_boxes, x_clusters, y_clusters):
    """
    Calculate an overall UI consistency score.
    
    Args:
        original_boxes: List of original bounding boxes
        equalized_boxes: List of equalized bounding boxes
        x_clusters: List of X-coordinate clusters
        y_clusters: List of Y-coordinate clusters
    
    Returns:
        A score between 0 and 100
    """
    alignment_score = calculate_alignment_consistency_score(
        original_boxes, equalized_boxes, x_clusters, y_clusters
    )
    
    # For a complete implementation, we would add:
    # - Size consistency scoring (similar widths/heights)
    # - Spacing consistency scoring (consistent gaps between elements)
    # - Grid alignment scoring (elements forming a grid pattern)
    
    # For simplicity, we'll just return the alignment score for now
    return alignment_score
