import os
import numpy as np
from paddleocr import PaddleOCR
import traceback # Ensure traceback is imported
from collections import defaultdict # For SITE_FONT_DATA_ACCUMULATOR updates

# Configuration
OCR_CONFIDENCE_THRESHOLD = 0.85

# Global accumulators for site-wide analysis
SITE_FONT_DATA_ACCUMULATOR = defaultdict(int) # Stores {font_size: total_character_count}
PROCESSED_PAGE_SCORES = [] # To store individual page font_score (1-10 scale)
PROCESSED_PAGE_COUNT = 0 # To count pages processed for site analysis

# Initialize OCR instance
try:
    # Updated initialization based on user's snippet
    ocr_instance = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang='en'
    )
    print("OCR instance initialized successfully with new parameters.")
except Exception as e:
    print(f"Error initializing OCR instance: {e}")
    print(f"Initialization traceback: {traceback.format_exc()}")
    try:
        # Fallback with minimal parameters, also removing show_log
        ocr_instance = PaddleOCR(lang='en') 
        print("Fallback OCR instance initialized")
    except Exception as fallback_e:
        print(f"Critical error: Could not initialize fallback OCR instance: {fallback_e}")
        ocr_instance = None # Set to None if critical failure

def calculate_font_consistency_score(ocr_data):
    """
    Calculates a font consistency score based on clustered font sizes detected in the OCR data.
    Sizes are clustered if they are within +/- 3px of a cluster's representative.
    """
    try:
        if not ocr_data:
            return 0.0, {}
        if not isinstance(ocr_data, list):
            return 0.0, {}

        # 1. Count occurrences of each original size
        original_size_counts = defaultdict(int)
        for item in ocr_data:
            size = item.get("size")
            if size is not None: # Ensure size is a valid number
                try:
                    # Attempt to convert size to int, as it might be float/str from OCR
                    valid_size = int(size)
                    original_size_counts[valid_size] += 1
                except ValueError:
                    print(f"Warning: Could not convert size '{size}' to int. Skipping.")
                    continue
        
        if not original_size_counts:
            return 0.0, {}

        # 2. Get unique sorted sizes
        unique_sorted_sizes = sorted(original_size_counts.keys())

        # 3. Create clusters and map original sizes to cluster representatives
        cluster_map = {}  # {original_size: representative_size}
        
        if not unique_sorted_sizes:
             return 0.0, {}

        current_cluster_rep = unique_sorted_sizes[0]
        cluster_map[current_cluster_rep] = current_cluster_rep

        for size_idx in range(len(unique_sorted_sizes)):
            size = unique_sorted_sizes[size_idx]
            if size == current_cluster_rep: # First element or already assigned
                cluster_map[size] = current_cluster_rep
                continue

            # Check if current size can merge with the current_cluster_rep
            if abs(size - current_cluster_rep) <= 3:
                cluster_map[size] = current_cluster_rep
            else:
                # Start a new cluster
                current_cluster_rep = size
                cluster_map[size] = current_cluster_rep
        
        # 4. Create clustered_font_counts: {representative_size: total_count_for_this_cluster}
        clustered_font_counts = defaultdict(int)
        for original_size, count in original_size_counts.items():
            representative = cluster_map.get(original_size)
            if representative is not None: # Ensure all original sizes were mapped
                clustered_font_counts[representative] += count
            else:
                # This case should ideally not happen if all sizes are processed
                print(f"Warning: Original size {original_size} was not mapped to a cluster. Assigning to itself.")
                clustered_font_counts[original_size] += count


        if not clustered_font_counts:
            return 0.0, {}

        # 5. Calculate consistency score based on clustered_font_counts
        total_items_in_clusters = sum(clustered_font_counts.values())
        if total_items_in_clusters == 0:
            return 0.0, {}

        most_frequent_cluster_rep = max(clustered_font_counts, key=clustered_font_counts.get)
        most_frequent_cluster_count = clustered_font_counts[most_frequent_cluster_rep]

        consistency_score = (most_frequent_cluster_count / total_items_in_clusters) * 100

        # 6. Prepare grouped_font_sizes_output using string keys for representatives
        grouped_font_sizes_output = {
            str(rep): count for rep, count in clustered_font_counts.items()
        }

        return consistency_score, grouped_font_sizes_output

    except Exception as e:
        print(f"Error in calculate_font_consistency_score: {e}")
        print(f"Calculation traceback: {traceback.format_exc()}")
        return 0.0, {}

def process_font_data(screenshot_path):
    """
    Processes font data from a screenshot using OCR and calculates font consistency.

    Args:
        screenshot_path (str): Path to the screenshot image.

    Returns:
        tuple: Contains font_data_for_analysis (list), 
               consistency_score_value (float), 
               grouped_font_sizes_value (dict).
    """
    font_data_for_analysis = []
    consistency_score_value = 0.0
    grouped_font_sizes_value = {}

    if not os.path.exists(screenshot_path): # Ensure os is imported
        print(f"Screenshot not found at {screenshot_path}")
        return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value # Return defaults
    
    if ocr_instance is None:
        print("OCR instance is not available. Cannot process font data.")
        return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value # Return defaults
        
    try:
        ocr_results_outer = ocr_instance.predict(screenshot_path)
        
        if not ocr_results_outer or not ocr_results_outer[0]:
            print(f"OCR returned no results or empty results for {screenshot_path}")
            return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value

        ocr_results_dict = ocr_results_outer[0]

        required_keys = ['rec_polys', 'rec_texts', 'rec_scores']
        if not isinstance(ocr_results_dict, dict) or not all(key in ocr_results_dict for key in required_keys):
            print(f"OCR results format unexpected for {screenshot_path}. Missing keys.")
            return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value

        rec_polys_val = ocr_results_dict['rec_polys']
        rec_texts_val = ocr_results_dict['rec_texts']
        rec_scores_val = ocr_results_dict['rec_scores']

        if not (isinstance(rec_polys_val, list) and isinstance(rec_texts_val, list) and isinstance(rec_scores_val, list) and \
                len(rec_polys_val) == len(rec_texts_val) == len(rec_scores_val)):
            print(f"OCR results data type or length mismatch for {screenshot_path}.")
            return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value
        
        if not rec_polys_val:
            print(f"OCR processing yielded no text boxes for {screenshot_path}")
            # No data to process, defaults will be returned.
        
        for poly, text_content, score in zip(rec_polys_val, rec_texts_val, rec_scores_val):
            if score >= OCR_CONFIDENCE_THRESHOLD:
                # Approximate font size from bounding box height
                ys = [p[1] for p in poly]
                height = int(max(ys) - min(ys)) if ys else 0 # Basic height calculation
                font_data_for_analysis.append({
                    "text": text_content,
                    "size": height, # Using height as a proxy for size
                    "confidence": score,
                    "bbox": poly
                })
        
        if font_data_for_analysis:
            score_and_groups = calculate_font_consistency_score(font_data_for_analysis)
            # calculate_font_consistency_score now always returns a tuple (score, groups)
            consistency_score_value, grouped_font_sizes_value = score_and_groups
        else:
            print(f"No font data extracted after OCR confidence filtering for {screenshot_path}")
            # Defaults (0.0, {}) are already set for consistency_score_value, grouped_font_sizes_value

    except Exception as e:
        print(f"Error during OCR or font analysis in font_processor for {screenshot_path}: {e}")
        print(f"Detailed traceback: {traceback.format_exc()}") # Ensure traceback is imported
        # Defaults (0.0, {}) are already set

    return font_data_for_analysis, consistency_score_value, grouped_font_sizes_value

def get_page_font_score(screenshot_path):
    """Get the font score for a single page.
    This is the main function for exporting a single page's font metrics.
    Updates global accumulators for site-wide analysis.
    
    Args:
        screenshot_path (str): Path to the screenshot image
    
    Returns:
        dict: Dictionary with font metrics for the page on a 1-10 scale
    """
    global SITE_FONT_DATA_ACCUMULATOR, PROCESSED_PAGE_SCORES, PROCESSED_PAGE_COUNT
    default_return = {
        "font_score": 1.0,
        "consistency_percentage": 0.0,
        "grouped_font_sizes": {},
        "font_data_detail": []
    }

    try:
        font_data, page_consistency_percentage, page_grouped_sizes_by_instance = process_font_data(screenshot_path)
        
        if font_data: # Check if any font data was processed at all
            for item in font_data:
                size = item.get("size")
                text_len = len(item.get("text", ""))
                if size is not None and text_len > 0:
                    SITE_FONT_DATA_ACCUMULATOR[str(size)] += text_len
        
        page_font_score_scaled = max(1.0, min(10.0, page_consistency_percentage / 7.0)) # Adjusted divisor
        
        # Update global accumulators for site-wide analysis if this page yielded data
        if page_consistency_percentage > 0 or page_grouped_sizes_by_instance: # Check if page had meaningful font data
            PROCESSED_PAGE_SCORES.append(page_font_score_scaled)
            PROCESSED_PAGE_COUNT +=1 # Increment only if page had some font data to contribute

        return {
            "font_score": page_font_score_scaled,
            "consistency_percentage": page_consistency_percentage,
            "grouped_font_sizes": page_grouped_sizes_by_instance, # This is the key part
            "font_data_detail": font_data
        }
    except Exception as e:
        print(f"Error in get_page_font_score for {screenshot_path}: {e}")
        print(f"Traceback: {traceback.format_exc()}") # Ensure traceback is imported
        return default_return

def analyze_site_fonts(): # Argument screenshots_dir removed
    """
    Analyzes aggregated font data to generate site-wide font metrics.
    Font sizes from the site-wide accumulator are clustered (+/- 3px) before calculating consistency and variety.
    Uses global accumulators: SITE_FONT_DATA_ACCUMULATOR, PROCESSED_PAGE_SCORES, PROCESSED_PAGE_COUNT.
        
    Returns:
        dict: Site-wide font information with scores on a 1-10 scale.
    """
    global SITE_FONT_DATA_ACCUMULATOR, PROCESSED_PAGE_SCORES, PROCESSED_PAGE_COUNT

    default_site_metrics = {
        "total_pages_analyzed": PROCESSED_PAGE_COUNT, # Still show how many pages contributed
        "site_font_consistency_score": 1.0,
        "site_font_variety_score": 10.0, # Max score for no/low variety
        "avg_page_font_score": 1.0,
        "font_groups_by_char_count": {}
    }

    if PROCESSED_PAGE_COUNT == 0 or not SITE_FONT_DATA_ACCUMULATOR:
        # If no pages were processed, or if accumulator is empty, return defaults
        # Update total_pages_analyzed in default if PROCESSED_PAGE_COUNT is already set
        default_site_metrics["total_pages_analyzed"] = PROCESSED_PAGE_COUNT
        if PROCESSED_PAGE_SCORES: # Calculate avg_page_score if available even if accumulator is empty
            avg_score = sum(PROCESSED_PAGE_SCORES) / len(PROCESSED_PAGE_SCORES)
            default_site_metrics["avg_page_font_score"] = max(1.0, min(10.0, avg_score))
        return default_site_metrics

    # 1. Prepare site_original_int_sizes_with_char_counts from SITE_FONT_DATA_ACCUMULATOR
    site_original_int_sizes_with_char_counts = defaultdict(int)
    for size_str, char_count in SITE_FONT_DATA_ACCUMULATOR.items():
        try:
            int_size = int(size_str)
            site_original_int_sizes_with_char_counts[int_size] += char_count
        except ValueError:
            print(f"Warning: Could not convert site-wide font size '{size_str}' to int during site analysis. Skipping.")
            continue
    
    if not site_original_int_sizes_with_char_counts:
        # This case implies SITE_FONT_DATA_ACCUMULATOR had only unparseable keys
        return default_site_metrics

    site_unique_sorted_sizes = sorted(site_original_int_sizes_with_char_counts.keys())

    # 2. Create site-level clusters and map original sizes to cluster representatives
    site_cluster_map = {}  # {original_int_size: representative_int_size}
    if not site_unique_sorted_sizes: # Should be caught by previous check, but as a safeguard
        return default_site_metrics
        
    current_site_cluster_rep = site_unique_sorted_sizes[0]
    site_cluster_map[current_site_cluster_rep] = current_site_cluster_rep

    for size_val in site_unique_sorted_sizes:
        if size_val == current_site_cluster_rep:
            site_cluster_map[size_val] = current_site_cluster_rep
            continue
        if abs(size_val - current_site_cluster_rep) <= 3:
            site_cluster_map[size_val] = current_site_cluster_rep
        else:
            current_site_cluster_rep = size_val
            site_cluster_map[size_val] = current_site_cluster_rep
    
    # 3. Create site_clustered_char_counts: {representative_int_size: total_char_count_for_this_cluster}
    site_clustered_char_counts = defaultdict(int)
    for original_int_size, char_count in site_original_int_sizes_with_char_counts.items():
        representative = site_cluster_map.get(original_int_size)
        if representative is not None:
            site_clustered_char_counts[representative] += char_count
        else:
            print(f"Warning: Site-wide original size {original_int_size} was not mapped to a cluster. Assigning to itself.")
            site_clustered_char_counts[original_int_size] += char_count

    if not site_clustered_char_counts:
        return default_site_metrics

    # 4. Site-wide Font Consistency (based on clustered character counts)
    total_chars_site_wide_clustered = sum(site_clustered_char_counts.values())
    site_consistency_score_scaled = 1.0
    if total_chars_site_wide_clustered > 0:
        most_frequent_site_cluster_rep = max(site_clustered_char_counts, key=site_clustered_char_counts.get)
        most_frequent_site_cluster_char_count = site_clustered_char_counts[most_frequent_site_cluster_rep]
        site_consistency_percentage = (most_frequent_site_cluster_char_count / total_chars_site_wide_clustered) * 100
        # Adjusted scaling: site_consistency_percentage / 7.0 makes the score less harsh
        # A 70% consistency now results in a score of 10.0
        site_consistency_score_scaled = max(1.0, min(10.0, site_consistency_percentage / 7.0))

    # 5. Site-wide Font Variety (based on number of unique font size clusters)
    num_distinct_font_clusters_site_wide = len(site_clustered_char_counts)
    site_font_variety_score_scaled = 10.0 # Default for 0 or 1 cluster (max score, low variety)

    if num_distinct_font_clusters_site_wide <= 1:
        site_font_variety_score_scaled = 10.0 
    elif num_distinct_font_clusters_site_wide <= 3:
        site_font_variety_score_scaled = 8.0
    elif num_distinct_font_clusters_site_wide <= 5:
        site_font_variety_score_scaled = 6.0
    elif num_distinct_font_clusters_site_wide <= 8:
        site_font_variety_score_scaled = 4.0
    else: # Very diverse
        site_font_variety_score_scaled = 2.0

    # 6. Average Page Font Score (from PROCESSED_PAGE_SCORES list of 1-10 scaled scores)
    avg_page_score_scaled = 1.0 # Default
    if PROCESSED_PAGE_SCORES:
        avg_page_score_scaled = sum(PROCESSED_PAGE_SCORES) / len(PROCESSED_PAGE_SCORES)
        avg_page_score_scaled = max(1.0, min(10.0, avg_page_score_scaled)) # Ensure it's within 1-10

    # 7. Prepare the site-wide font groups (palette) using clustered data
    clustered_font_groups_by_char_count_output = {
        str(rep): count for rep, count in site_clustered_char_counts.items()
    }

    return {
        "total_pages_analyzed": PROCESSED_PAGE_COUNT,
        "site_font_consistency_score": float(site_consistency_score_scaled),
        "site_font_variety_score": float(site_font_variety_score_scaled),
        "avg_page_font_score": float(avg_page_score_scaled),
        "font_groups_by_char_count": clustered_font_groups_by_char_count_output
    }

def get_site_font_scores(): # Argument screenshots_dir removed
    """
    Get the site-wide font scores based on globally accumulated data.
    
    Returns:
        dict: Dictionary with site-wide font metrics on a 1-10 scale.
    """
    try:
        return analyze_site_fonts() # Directly call analyze_site_fonts
    except Exception as e:
        print(f"Error in get_site_font_scores: {e}")
        print(f"Traceback: {traceback.format_exc()}") # Ensure traceback is imported
        return { # Return default structure on error
            "total_pages_analyzed": 0,
            "site_font_consistency_score": 1.0,
            "site_font_variety_score": 1.0,
            "avg_page_font_score": 1.0,
            "font_groups_by_char_count": {}
        }

def reset_site_font_accumulators():
    """
    Resets the global accumulators for site-wide font analysis.
    Should be called at the beginning of a new analysis session.
    """
    global SITE_FONT_DATA_ACCUMULATOR, PROCESSED_PAGE_SCORES, PROCESSED_PAGE_COUNT
    
    SITE_FONT_DATA_ACCUMULATOR.clear()
    # SITE_FONT_DATA_ACCUMULATOR = defaultdict(int) # Re-assign to ensure it's a new defaultdict
    # Clearing and then re-assigning is good practice if the object type could change or if specific
    # re-initialization logic for defaultdict is complex. For simple defaultdict(int), .clear() is often enough
    # as it retains its factory. However, to be absolutely safe and explicit:
    SITE_FONT_DATA_ACCUMULATOR = defaultdict(int)
    
    PROCESSED_PAGE_SCORES.clear()
    PROCESSED_PAGE_COUNT = 0
    print("Site font accumulators have been reset.")
