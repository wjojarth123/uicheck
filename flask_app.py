from flask import Flask, request, jsonify, render_template
import os
from werkzeug.utils import secure_filename
import tempfile
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import torch
import numpy as np
import collections
import random

app = Flask(__name__)

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
TEMP_FOLDER = tempfile.gettempdir()  # Use system temp folder
MODEL_PATH = 'OmniParser/weights/icon_detect/model.pt'  # Path to the model
ALIGNMENT_TOLERANCE = 50  # Default alignment tolerance

# Function to load and return YOLO model
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

# Alignment Helper Functions
def is_top_aligned(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    # box: [x1, y1, x2, y2]
    return abs(box1[1] - box2[1]) <= tolerance

def is_bottom_aligned(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    return abs(box1[3] - box2[3]) <= tolerance

def is_left_aligned(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    return abs(box1[0] - box2[0]) <= tolerance

def is_right_aligned(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    return abs(box1[2] - box2[2]) <= tolerance

def is_vertically_centered(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    center1_y = (box1[1] + box1[3]) / 2
    center2_y = (box2[1] + box2[3]) / 2
    return abs(center1_y - center2_y) <= tolerance

def is_horizontally_centered(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    center1_x = (box1[0] + box1[2]) / 2
    center2_x = (box2[0] + box2[2]) / 2
    return abs(center1_x - center2_x) <= tolerance

# Calculate distance between two boxes (center-to-center)
def box_distance(box1, box2):
    center1_x = (box1[0] + box1[2]) / 2
    center1_y = (box1[1] + box1[3]) / 2
    center2_x = (box2[0] + box2[2]) / 2
    center2_y = (box2[1] + box2[3]) / 2
    return ((center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2) ** 0.5

def check_any_alignment(box1, box2, tolerance=ALIGNMENT_TOLERANCE):
    is_aligned = (is_top_aligned(box1, box2, tolerance) or
            is_bottom_aligned(box1, box2, tolerance) or
            is_left_aligned(box1, box2, tolerance) or
            is_right_aligned(box1, box2, tolerance) or
            is_vertically_centered(box1, box2, tolerance) or
            is_horizontally_centered(box1, box2, tolerance))
    
    return is_aligned

# Function to find the largest clique of boxes that are all aligned with the same method
def find_alignment_groups(boxes, tolerance=20):
    num_boxes = len(boxes)
    
    # Prepare the data structure to hold alignment groups
    alignment_groups = []
    
    # Check different alignment methods
    alignment_methods = [
        ("top-aligned", lambda b1, b2: is_top_aligned(b1, b2, tolerance)),
        ("bottom-aligned", lambda b1, b2: is_bottom_aligned(b1, b2, tolerance)),
        ("left-aligned", lambda b1, b2: is_left_aligned(b1, b2, tolerance)),
        ("right-aligned", lambda b1, b2: is_right_aligned(b1, b2, tolerance)),
        ("vertically-centered", lambda b1, b2: is_vertically_centered(b1, b2, tolerance)),
        ("horizontally-centered", lambda b1, b2: is_horizontally_centered(b1, b2, tolerance))
    ]
    
    # For each alignment method, find all possible groups
    for alignment_name, alignment_func in alignment_methods:
        # Build adjacency matrix for this alignment method
        adj_matrix = [[False for _ in range(num_boxes)] for _ in range(num_boxes)]
        
        for i in range(num_boxes):
            adj_matrix[i][i] = True  # A box is aligned with itself
            for j in range(i+1, num_boxes):
                if alignment_func(boxes[i], boxes[j]):
                    adj_matrix[i][j] = True
                    adj_matrix[j][i] = True
        
        # Count the potential size of each group to prioritize finding large groups first
        potential_group_sizes = {}
        for i in range(num_boxes):
            potential_group_sizes[i] = sum(adj_matrix[i])
            
        # Sort boxes by their potential group size (descending)
        sorted_boxes = sorted(range(num_boxes), key=lambda i: potential_group_sizes[i], reverse=True)
        
        # Find maximal cliques (groups where all elements are aligned with each other)
        # Start with the largest potential groups and try to form cliques
        remaining_boxes = set(range(num_boxes))
        
        while remaining_boxes:
            if not sorted_boxes:  # If all sorted boxes have been processed
                break
                
            # Start with the box that has the most alignments
            best_box = None
            for box in sorted_boxes:
                if box in remaining_boxes:
                    best_box = box
                    break
                    
            if best_box is None:  # No more boxes to process
                break
                
            # Get all boxes aligned with this box
            possible_group = {best_box}
            for j in remaining_boxes:  # Only check among remaining boxes
                if adj_matrix[best_box][j]:
                    possible_group.add(j)
            
            # Verify that all boxes in the possible group are aligned with each other
            is_clique = True
            for i in possible_group:
                for j in possible_group:
                    if not adj_matrix[i][j]:
                        is_clique = False
                        break
                if not is_clique:
                    break
            
            if is_clique and len(possible_group) > 1:  # Only add groups with at least 2 boxes
                group_list = sorted(list(possible_group))
                alignment_groups.append((alignment_name, group_list))
                # Remove these boxes from consideration to avoid overlapping groups
                remaining_boxes -= possible_group
                # Also remove these boxes from the sorted list
                sorted_boxes = [box for box in sorted_boxes if box not in possible_group]
            else:
                # If not a clique, remove just the best box and try again
                remaining_boxes.remove(best_box)
                sorted_boxes.remove(best_box)
    
    # Sort groups by size (largest first)
    alignment_groups.sort(key=lambda x: len(x[1]), reverse=True)
    return alignment_groups

def find_grid_alignments(boxes, existing_alignment_groups, tolerance=20):
    """
    Find grid alignments - elements that are both horizontally and vertically aligned.
    """
    # Get horizontal and vertical alignment groups
    horizontal_groups = []
    vertical_groups = []
    
    for alignment_type, group in existing_alignment_groups:
        if alignment_type in ["left-aligned", "right-aligned", "horizontally-centered"]:
            horizontal_groups.append(set(group))
        elif alignment_type in ["top-aligned", "bottom-aligned", "vertically-centered"]:
            vertical_groups.append(set(group))
    
    grid_groups = []
    grid_idx = 0
    
    # Find intersections between horizontal and vertical groups
    for h_group in horizontal_groups:
        for v_group in vertical_groups:
            # Elements in both groups form a grid cell
            intersection = h_group.intersection(v_group)
            if len(intersection) >= 2:  # Need at least 2 elements for a grid
                grid_groups.append((f"grid-{grid_idx}", sorted(list(intersection))))
                grid_idx += 1
    
    # Merge overlapping grid groups
    merged_grid_groups = []
    while grid_groups:
        current_group_name, current_group = grid_groups.pop(0)
        current_set = set(current_group)
        
        # Check against remaining groups for potential merge
        i = 0
        while i < len(grid_groups):
            _, other_group = grid_groups[i]
            other_set = set(other_group)
            
            # If there's significant overlap, merge the groups
            if len(current_set.intersection(other_set)) / len(other_set) > 0.5:
                current_set.update(other_set)
                grid_groups.pop(i)
            else:
                i += 1
        
        merged_grid_groups.append((f"grid-aligned", sorted(list(current_set))))
    
    return merged_grid_groups

def calculate_organization_score(boxes, alignment_groups):
    """
    Calculate an organization score between 0 and 1:
    - 0: Completely unorganized (no alignment groups with more than 3 elements)
    - 1: Perfectly organized (all elements can be categorized into a few major groups)
    """
    if not boxes or not alignment_groups:
        return 0.0
    
    num_boxes = len(boxes)
    
    # Calculate percentage of boxes in meaningful groups (groups with > 3 elements)
    meaningful_groups = [group for alignment_type, group in alignment_groups if len(group) > 3]
    boxes_in_meaningful_groups = set()
    for group in meaningful_groups:
        boxes_in_meaningful_groups.update(group)
    
    coverage_score = len(boxes_in_meaningful_groups) / num_boxes
    
    # Calculate group size distribution score
    # Higher score when boxes are concentrated in fewer, larger groups
    if meaningful_groups:
        group_sizes = [len(group) for group in meaningful_groups]
        largest_group_size = max(group_sizes)
        avg_group_size = sum(group_sizes) / len(group_sizes)
        
        # Ideally, we want high average group size and large groups overall
        size_score = (avg_group_size / num_boxes) * (largest_group_size / num_boxes)
    else:
        size_score = 0.0
    
    # Calculate grid alignment bonus
    grid_groups = [group for alignment_type, group in alignment_groups if "grid" in alignment_type]
    if grid_groups:
        boxes_in_grids = set()
        for group in grid_groups:
            boxes_in_grids.update(group)
        
        grid_bonus = 0.1 * (len(boxes_in_grids) / num_boxes)  # 10% bonus for complete grid alignment
    else:
        grid_bonus = 0
    
    # Combine the scores with weights
    # Coverage is most important, followed by size distribution
    final_score = (0.7 * coverage_score) + (0.2 * size_score) + grid_bonus
    
    # Ensure score is between 0 and 1
    return max(0.0, min(1.0, final_score))

def analyze_ui_organization(image_path, model_path=MODEL_PATH, tolerance=ALIGNMENT_TOLERANCE):
    """
    Analyze a UI screenshot and return its organization score and visualization.
    """
    # Configuration
    device = 'cpu'  # Use 'cuda' if a CUDA-enabled GPU is available
    
    # Load the model
    try:
        model = get_yolo_model(model_path)
        model.to(device)
    except Exception as e:
        print(f"Error loading model: {e}")
        return 0, {}, None
    
    # Load the image
    try:
        image = Image.open(image_path).convert('RGB')
    except Exception as e:
        print(f"Error loading image: {e}")
        return 0, {}, None
    
    # Perform detection
    try:
        results = model.predict(image_path, device=device, verbose=False) 
    except Exception as e:
        print(f"Error during model prediction: {e}")
        return 0, {}, None
    
    # Extract bounding boxes
    detected_boxes = []
    if results and hasattr(results[0], 'boxes') and results[0].boxes is not None:
        boxes_tensor = results[0].boxes.xyxy
        if boxes_tensor.numel() > 0:
            detected_boxes = boxes_tensor.cpu().tolist()
    
    if not detected_boxes:
        return 0, {"error": "No boxes detected"}, image
    
    # Find alignment groups
    alignment_groups = find_alignment_groups(detected_boxes, tolerance=tolerance)
    
    # Find grid alignments (boxes aligned both horizontally and vertically)
    grid_groups = find_grid_alignments(detected_boxes, alignment_groups, tolerance=tolerance)
    
    # Add grid groups to alignment groups
    if grid_groups:
        alignment_groups = grid_groups + alignment_groups
        # Re-sort by size
        alignment_groups.sort(key=lambda x: len(x[1]), reverse=True)
    
    # Calculate organization score
    score = calculate_organization_score(detected_boxes, alignment_groups)
    
    # Collect statistics
    stats = {
        "num_boxes": len(detected_boxes),
        "num_groups": len(alignment_groups),
        "group_sizes": [len(group) for _, group in alignment_groups],
        "alignment_types": {}
    }
    
    # Count alignment types
    for alignment_type, _ in alignment_groups:
        stats["alignment_types"][alignment_type] = stats["alignment_types"].get(alignment_type, 0) + 1
    
    # Visualize the groups on the image
    image_copy = image.copy()
    draw = ImageDraw.Draw(image_copy)
    
    # Generate distinct colors for groups
    def get_color(i, total):
        hue = i / total
        r, g, b = plt.cm.hsv(hue)[:3]
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    
    # Special colors for grid alignments
    def get_group_color(alignment_type, idx, total):
        if "grid" in alignment_type:
            # Use a distinctive color palette for grid alignments
            grid_colors = [
                "#FF5733",  # Coral red
                "#33FF57",  # Bright green
                "#3357FF",  # Bright blue
                "#F033FF",  # Magenta
                "#FF33C7",  # Pink
                "#33FFF1"   # Cyan
            ]
            return grid_colors[idx % len(grid_colors)]
        else:
            return get_color(idx, total)
    
    # Draw boxes with colors based on their primary group
    box_to_group = {}
    for group_idx, (alignment_type, group) in enumerate(alignment_groups):
        for box_idx in group:
            if box_idx not in box_to_group or "grid" in alignment_type or group_idx < box_to_group[box_idx][0]:
                box_to_group[box_idx] = (group_idx, get_group_color(alignment_type, group_idx, len(alignment_groups)), alignment_type)
    
    for idx, box_coords in enumerate(detected_boxes):
        x1, y1, x2, y2 = map(int, box_coords[:4])
        if idx in box_to_group:
            _, color, alignment_type = box_to_group[idx]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
            
            # Add a small marker for grid-aligned elements
            if "grid" in alignment_type:
                # Draw a small filled rectangle in the top-left corner
                marker_size = 8
                draw.rectangle([x1, y1, x1 + marker_size, y1 + marker_size], fill=color)
        else:
            draw.rectangle([x1, y1, x2, y2], outline="#AAAAAA", width=1)
    
    return score, stats, image_copy

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Main page with a simple form for image upload"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>UI Organization Analysis</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; }
            .btn { padding: 10px 15px; background: #4CAF50; color: white; border: none; cursor: pointer; }
            .result { margin-top: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>UI Organization Analysis</h1>
        <p>Upload a UI screenshot to analyze its organizational structure and alignment score.</p>
        
        <form action="/analyze" method="post" enctype="multipart/form-data">
            <div class="form-group">
                <label for="image">Select image:</label>
                <input type="file" name="image" id="image" required>
            </div>
            <div class="form-group">
                <label for="tolerance">Alignment Tolerance (pixels):</label>
                <input type="number" name="tolerance" id="tolerance" value="50" min="1" max="200">
            </div>
            <button type="submit" class="btn">Analyze UI Organization</button>
        </form>
    </body>
    </html>
    '''

@app.route('/analyze', methods=['POST'])
def analyze_image():
    """Analyze the uploaded image and return the organization score"""
    # Check if an image file was uploaded
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['image']
    
    # If the user submits an empty form
    if file.filename == '':
        return jsonify({'error': 'No image selected'}), 400
    
    # Get tolerance parameter (default to 50 if not provided)
    try:
        tolerance = int(request.form.get('tolerance', ALIGNMENT_TOLERANCE))
    except ValueError:
        tolerance = ALIGNMENT_TOLERANCE
    
    if file and allowed_file(file.filename):
        # Save the file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(TEMP_FOLDER, filename)
        file.save(temp_path)
        
        try:
            # Analyze the image
            score, stats, _ = analyze_ui_organization(temp_path, MODEL_PATH, tolerance)
            
            # Prepare the response
            response = {
                'organization_score': round(score, 4),
                'interpretation': get_score_interpretation(score),
                'stats': {
                    'num_boxes': stats.get('num_boxes', 0),
                    'num_groups': stats.get('num_groups', 0),
                    'group_sizes': stats.get('group_sizes', []),
                    'alignment_types': stats.get('alignment_types', {})
                }
            }
            
            return jsonify(response)
        
        except Exception as e:
            return jsonify({'error': f'Analysis failed: {str(e)}'}), 500
        
        finally:
            # Clean up the temporary file
            try:
                os.remove(temp_path)
            except:
                pass
    
    return jsonify({'error': 'Invalid file format. Allowed formats: png, jpg, jpeg, gif'}), 400

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """API endpoint that accepts an image and returns the analysis results as JSON"""
    return analyze_image()

def get_score_interpretation(score):
    """Return a text interpretation of the organization score"""
    if score >= 0.8:
        return "Highly organized UI with clear alignment patterns"
    elif score >= 0.6:
        return "Well-organized UI with good alignment"
    elif score >= 0.4:
        return "Moderately organized UI"
    elif score >= 0.2:
        return "Somewhat disorganized UI"
    else:
        return "Poorly organized UI with few alignment patterns"

if __name__ == '__main__':
    # Ensure the necessary directories exist
    os.makedirs('weights/icon_detect', exist_ok=True)
    
    print("Starting UI Organization Analysis server...")
    print(f"Make sure the model exists at: {MODEL_PATH}")
    print("Access the web interface at http://127.0.0.1:5000/")
    
    app.run(debug=True)
