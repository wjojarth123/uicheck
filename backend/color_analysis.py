from PIL import Image
import numpy as np
from sklearn.cluster import KMeans
from collections import Counter

# --- Global State for Site-Wide Color Analysis ---
SITE_WIDE_AGGREGATED_PIXELS = Counter()  # Stores sum of (percentage * RESIZED_IMAGE_TOTAL_PIXELS) for each color
PROCESSED_PAGE_COUNT = 0
RESIZED_IMAGE_TOTAL_PIXELS = 150 * 150  # Based on resize in get_color_palette

# --- Utility Functions ---
def rgb_to_hex(rgb):
    """Convert RGB tuple to hexadecimal color code."""
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))

def hex_to_rgb(hex_color):
    """Convert hexadecimal color code to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def calculate_color_distance(color1, color2):
    """Calculate Euclidean distance between two RGB colors."""
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(color1, color2)))

# --- Core Palette Extraction (Simplified) ---
def get_color_palette(image_path, n_colors=10, min_prominence=0.05):
    """Extract a color palette from an image.
    
    Args:
        image_path (str): Path to the image file.
        n_colors (int): Maximum number of K-means clusters.
        min_prominence (float): Minimum percentage for a color to be "prominent".
        
    Returns:
        dict: Palette information including prominent colors, color ranges, and unique color count.
              Returns {"error": ...} if an issue occurs.
    """
    try:
        with Image.open(image_path) as img:
            img_rgb = img.convert('RGB')
            
            img_resized = img_rgb.resize((150, 150))  # Resize for K-means processing
            
            img_array = np.array(img_resized)
            pixels = img_array.reshape(-1, 3)
            total_pixels_in_resized = len(pixels)

            # Use K-means clustering
            actual_n_clusters = min(n_colors, len(np.unique(pixels, axis=0)))
            if actual_n_clusters == 0: 
                 return {
                    "unique_colors_in_image": 0,
                    "prominent_colors": [],
                    "color_ranges": [],
                }

            kmeans = KMeans(n_clusters=actual_n_clusters, n_init='auto', random_state=0)
            kmeans.fit(pixels)
            
            cluster_colors = kmeans.cluster_centers_.astype(int)
            labels = kmeans.labels_
            color_counts = Counter(labels)
            
            percentages = {i: count / total_pixels_in_resized for i, count in color_counts.items()}
            
            prominent_colors_list = []
            non_prominent_indices = []

            for i, pct in percentages.items():
                if pct >= min_prominence:
                    prominent_colors_list.append({
                        "color": rgb_to_hex(tuple(cluster_colors[i])),
                        "percentage": float(pct)
                    })
                else:
                    non_prominent_indices.append(i)
            
            color_ranges_list = []
            if non_prominent_indices:
                range_candidate_colors = np.array([cluster_colors[i] for i in non_prominent_indices])
                range_candidate_percentages = np.array([percentages[i] for i in non_prominent_indices])

                if len(range_candidate_colors) > 0:
                    num_ranges_to_form = min(5, len(range_candidate_colors))
                    if len(range_candidate_colors) == 1: 
                        center_c = tuple(range_candidate_colors[0])
                        color_ranges_list.append({
                            "start": rgb_to_hex(center_c),
                            "end": rgb_to_hex(center_c),
                            "center": rgb_to_hex(center_c),
                            "percentage": float(range_candidate_percentages[0])
                        })
                    else:
                        range_kmeans = KMeans(n_clusters=num_ranges_to_form, n_init='auto', random_state=0)
                        range_kmeans.fit(range_candidate_colors)
                        
                        range_centers_rgb = range_kmeans.cluster_centers_.astype(int)
                        range_labels = range_kmeans.labels_
                        
                        for r_idx in range(num_ranges_to_form):
                            mask = (range_labels == r_idx)
                            if not np.any(mask): continue
                                
                            colors_in_this_range = range_candidate_colors[mask]
                            percentages_in_this_range = range_candidate_percentages[mask]
                            
                            min_color_in_range = np.min(colors_in_this_range, axis=0).tolist()
                            max_color_in_range = np.max(colors_in_this_range, axis=0).tolist()
                            center_color_of_range = tuple(range_centers_rgb[r_idx]) 
                            
                            color_ranges_list.append({
                                "start": rgb_to_hex(tuple(min_color_in_range)),
                                "end": rgb_to_hex(tuple(max_color_in_range)),
                                "center": rgb_to_hex(center_color_of_range),
                                "percentage": float(np.sum(percentages_in_this_range))
                            })
        return {
                "unique_colors_in_image": actual_n_clusters, 
                "prominent_colors": prominent_colors_list,
                "color_ranges": color_ranges_list
            }
    except Exception as e:
        print(f"Error in get_color_palette for {image_path}: {str(e)}")
        return {
            "error": str(e),
            "unique_colors_in_image": 0,
            "prominent_colors": [],
            "color_ranges": []
        }

# --- Helper to Flatten Palette Data ---
def _flatten_palette_data(palette_data):
    """Converts prominent colors and color range centers into a single list."""
    flat_palette = []
    if palette_data.get("prominent_colors"):
        for color_info in palette_data["prominent_colors"]:
            flat_palette.append({"hex": color_info["color"], "percentage": color_info["percentage"]})
    if palette_data.get("color_ranges"):
        for range_info in palette_data["color_ranges"]: 
            flat_palette.append({"hex": range_info["center"], "percentage": range_info["percentage"]})
    return flat_palette

# --- New Scoring Function ---
def calculate_palette_score(flat_color_list, context="page"):
    """Calculates a score for a palette based on the prominence of top N colors.
    
    Args:
        flat_color_list (list): List of dicts, each {'hex': str, 'percentage': float}.
                                Percentages should ideally sum to 1.0 for the input scope.
        context (str): 'page' or 'site'. Determines N and calculation method.
    
    Returns:
        float: Score from 0.0 to 10.0.
    """
    if not flat_color_list:
        return 0.0

    # Sort colors by percentage in descending order
    sorted_colors = sorted(flat_color_list, key=lambda x: x['percentage'], reverse=True)

    total_percentage_all_colors = sum(item['percentage'] for item in sorted_colors)
    if total_percentage_all_colors == 0: # Avoid division by zero
        return 0.0

    if context == "page":
        n_top_colors = 3
    elif context == "site":
        n_top_colors = 8
    else:
        raise ValueError("Invalid context for calculate_palette_score. Must be 'page' or 'site'.")

    # Sum percentages of the top N colors (or fewer if not enough colors)
    sum_top_n_percentages = sum(item['percentage'] for item in sorted_colors[:n_top_colors])

    # Calculate the ratio
    ratio = sum_top_n_percentages / total_percentage_all_colors

    if context == "page":
        # Square the ratio for page score
        score_basis = ratio ** 4
    else: # context == "site"
        # Use the ratio directly for site score
        score_basis = ratio **2

    # Scale to 0-10
    final_score = score_basis * 10.0
    return max(0.0, min(10.0, round(final_score, 2))) # Clamp to 0-10

# --- Page-Level Processing ---
def process_page_colors(image_path):
    """Processes a single page's image to get color score and update site-wide aggregates."""
    global SITE_WIDE_AGGREGATED_PIXELS, PROCESSED_PAGE_COUNT

    try:
        raw_palette_data = get_color_palette(image_path)
        if "error" in raw_palette_data:
            return {
                "page_score": 0.0,
                "palette_details": raw_palette_data, 
                "flat_palette": [],
                "error": raw_palette_data["error"]
            }

        flattened_page_palette = _flatten_palette_data(raw_palette_data)
        
        # Calculate page score using the new context-aware function
        page_score = calculate_palette_score(flattened_page_palette, context="page")

        # Aggregate for site-wide analysis
        for color_item in flattened_page_palette:
            pixel_contribution = color_item['percentage'] * RESIZED_IMAGE_TOTAL_PIXELS
            SITE_WIDE_AGGREGATED_PIXELS[color_item['hex']] += pixel_contribution
        
        PROCESSED_PAGE_COUNT += 1

        return {
            "page_score": page_score,
            "palette_details": raw_palette_data, 
            "flat_palette": flattened_page_palette    
        }
    except Exception as e:
        print(f"Error in process_page_colors for {image_path}: {str(e)}")
        return {
            "page_score": 0.0,
            "palette_details": {"error": str(e)},
            "flat_palette": [],
            "error": str(e)
        }

# --- Site-Wide Metrics ---
def get_site_color_metrics():
    """Calculates site-wide color score and other metrics from aggregated data."""
    global SITE_WIDE_AGGREGATED_PIXELS, PROCESSED_PAGE_COUNT

    if PROCESSED_PAGE_COUNT == 0:
        return {
            "site_color_score": 0.0,
            "site_total_distinct_colors": 0,
            "site_palette_representation": [],
            "processed_pages_for_site_color": 0
        }

    # Convert aggregated pixel counts back to percentages for the site
    total_aggregated_pixel_values = sum(SITE_WIDE_AGGREGATED_PIXELS.values())
    if total_aggregated_pixel_values == 0:
        site_flat_palette = []
    else:
        site_flat_palette = [
            {"hex": hex_color, "percentage": count / total_aggregated_pixel_values}
            for hex_color, count in SITE_WIDE_AGGREGATED_PIXELS.items()
        ]

    # Calculate site score using the new context-aware function
    site_score = calculate_palette_score(site_flat_palette, context="site")

    # Sort for consistent output if needed for "site_palette_representation"
    # For now, just pass the calculated flat palette
    # sorted_site_palette = sorted(site_flat_palette, key=lambda x: x[\'percentage\'], reverse=True)

    return {
        "site_color_score": site_score,
        "site_total_distinct_colors": len(site_flat_palette),
        "site_palette_representation": site_flat_palette, # Could be sorted_site_palette if preferred
        "processed_pages_for_site_color": PROCESSED_PAGE_COUNT
    }

# --- Global State Reset ---
def reset_color_analysis_globals():
    """Resets global variables used for site-wide analysis."""
    global SITE_WIDE_AGGREGATED_PIXELS, PROCESSED_PAGE_COUNT
    SITE_WIDE_AGGREGATED_PIXELS.clear()
    PROCESSED_PAGE_COUNT = 0
    print("Color analysis global state has been reset.")

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    print("Running a simplified test without actual image processing...")
    reset_color_analysis_globals()

    mock_palette_page1 = {
        "prominent_colors": [
            {"color": "#ff0000", "percentage": 0.6}, 
            {"color": "#00ff00", "percentage": 0.3}  
        ],
        "color_ranges": [
            {"center": "#0000ff", "percentage": 0.1} 
        ]
    }
    mock_palette_page2 = {
        "prominent_colors": [
            {"color": "#ff0000", "percentage": 0.5}, 
            {"color": "#ffff00", "percentage": 0.4}  
        ],
        "color_ranges": [
            {"center": "#0000ff", "percentage": 0.05},
            {"center": "#00FF00", "percentage": 0.05} 
        ]
    }
    
    # Page 1
    flat_p1 = _flatten_palette_data(mock_palette_page1)
    score_p1 = calculate_palette_score(flat_p1)
    for item in flat_p1: SITE_WIDE_AGGREGATED_PIXELS[item['hex']] += item['percentage'] * RESIZED_IMAGE_TOTAL_PIXELS
    PROCESSED_PAGE_COUNT +=1
    print(f"Page 1 (mocked) - Score: {score_p1}, Palette: {flat_p1}")

    # Page 2
    flat_p2 = _flatten_palette_data(mock_palette_page2)
    score_p2 = calculate_palette_score(flat_p2)
    for item in flat_p2: SITE_WIDE_AGGREGATED_PIXELS[item['hex']] += item['percentage'] * RESIZED_IMAGE_TOTAL_PIXELS
    PROCESSED_PAGE_COUNT +=1
    print(f"Page 2 (mocked) - Score: {score_p2}, Palette: {flat_p2}")
    
    site_summary = get_site_color_metrics()
    print("\nSite Metrics (mocked):")
    print(f"  Site Score: {site_summary['site_score']}")
    print(f"  Pages Analyzed: {site_summary['pages_analyzed']}")
    print(f"  Site Palette Summary: {site_summary['site_palette_summary']}")
    
    print("\nNote: The __main__ block provides a simplified test. For full testing, provide image paths.")
