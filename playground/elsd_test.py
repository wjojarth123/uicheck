import cv2
import numpy as np
import matplotlib.pyplot as plt

def dynamic_edge_detection(image):
    # Convert to grayscale for processing
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Parameters for local complexity and difference calculation
    kernel_size = 15  # Size of the local region

    # Calculate local complexity (variance in local region)
    local_complexity = np.zeros_like(gray, dtype=np.float32)
    for i in range(0, gray.shape[0], kernel_size):
        for j in range(0, gray.shape[1], kernel_size):
            roi = gray[i:i+kernel_size, j:j+kernel_size]
            local_variance = np.var(roi)
            local_complexity[i:i+kernel_size, j:j+kernel_size] = local_variance

    # Normalize local complexity for visualization
    local_complexity_normalized = cv2.normalize(local_complexity, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Calculate difference map (gradient magnitude) on the full-color image
    # Split the color image into its BGR channels
    b, g, r = cv2.split(image)

    # Calculate gradient magnitude for each channel
    grad_x_b = cv2.Sobel(b, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_b = cv2.Sobel(b, cv2.CV_64F, 0, 1, ksize=3)
    difference_map_b = cv2.magnitude(grad_x_b, grad_y_b)

    grad_x_g = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_g = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    difference_map_g = cv2.magnitude(grad_x_g, grad_y_g)

    grad_x_r = cv2.Sobel(r, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_r = cv2.Sobel(r, cv2.CV_64F, 0, 1, ksize=3)
    difference_map_r = cv2.magnitude(grad_x_r, grad_y_r)

    # Combine the gradient magnitudes from all channels
    difference_map = cv2.merge((difference_map_b, difference_map_g, difference_map_r))

    # Normalize difference map for visualization
    difference_map_normalized = cv2.normalize(difference_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Dynamically adjust thresholds based on local complexity and difference map
    high_threshold = 100 + (local_complexity_normalized / 255.0) * 100  # High threshold varies with complexity
    low_threshold = high_threshold * 0.5  # Low threshold is half of high threshold

    # Apply Canny edge detection with dynamic thresholds
    edges = np.zeros_like(gray, dtype=np.uint8)
    for i in range(0, gray.shape[0], kernel_size):
        for j in range(0, gray.shape[1], kernel_size):
            roi = gray[i:i+kernel_size, j:j+kernel_size]
            roi_high_thresh = high_threshold[i:i+kernel_size, j:j+kernel_size].mean()
            roi_low_thresh = low_threshold[i:i+kernel_size, j:j+kernel_size].mean()
            edges[i:i+kernel_size, j:j+kernel_size] = cv2.Canny(roi, roi_low_thresh, roi_high_thresh)

    return edges, local_complexity_normalized, difference_map_normalized, difference_map_b, difference_map_g, difference_map_r

def calculate_consistency_map(image, kernel_size=15, similarity_threshold=30):
    # Convert the image to grayscale for simplicity
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Initialize the consistency map
    consistency_map = np.zeros_like(gray, dtype=np.float32)

    # Iterate over the image in blocks of kernel_size
    for i in range(0, gray.shape[0], kernel_size):
        for j in range(0, gray.shape[1], kernel_size):
            roi = gray[i:i+kernel_size, j:j+kernel_size]
            center_pixel = roi[kernel_size // 2, kernel_size // 2] if roi.size > 0 else 0

            # Count similar pixels in the region
            similar_pixels = np.sum(np.abs(roi - center_pixel) <= similarity_threshold)
            consistency_map[i:i+kernel_size, j:j+kernel_size] = similar_pixels

    # Normalize the consistency map for visualization
    consistency_map_normalized = cv2.normalize(consistency_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return consistency_map_normalized

def compute_local_complexity(lab_img, patch_size=32):
    """Compute color complexity based on local variance in a* and b* channels."""
    # Convert a* and b* channels to float32 for more accurate arithmetic
    a_channel = lab_img[:, :, 1].astype(np.float32)
    b_channel = lab_img[:, :, 2].astype(np.float32)

    # Compute local mean
    # cv2.blur output will be float32 if input is float32
    a_mean = cv2.blur(a_channel, (patch_size, patch_size))
    b_mean = cv2.blur(b_channel, (patch_size, patch_size))

    # Compute variance: mean of (value - mean)^2
    # (a_channel - a_mean) will be float32. Squaring it is float32.
    a_var_term_sq = (a_channel - a_mean) ** 2
    b_var_term_sq = (b_channel - b_mean) ** 2

    # cv2.blur will compute the mean of these squared differences (variance)
    a_var = cv2.blur(a_var_term_sq, (patch_size, patch_size))
    b_var = cv2.blur(b_var_term_sq, (patch_size, patch_size))

    # color_complexity is sqrt(sum of variances). Result is float32.
    color_complexity = np.sqrt(a_var + b_var)

    # Ensure valid input for normalization
    if not np.isfinite(color_complexity).all():
        color_complexity = np.nan_to_num(color_complexity, nan=0.0, posinf=0.0, neginf=0.0)

    min_val = np.min(color_complexity)
    max_val = np.max(color_complexity)

    if min_val == max_val:
        # If all values are the same (e.g., all zeros), normalization is problematic (div by zero).
        # Return a zero image of the same shape, as uint8.
        return np.zeros_like(color_complexity, dtype=np.uint8)

    # Normalize complexity to [0, 255]
    # color_complexity is float32 here.
    complexity_norm = cv2.normalize(color_complexity, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return complexity_norm

def create_binary_difference_map(image):
    """Create a binary difference map where every difference is 1 and no difference is 0."""
    # Convert the image to grayscale for simplicity
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Compute the absolute difference between adjacent pixels
    diff_x = cv2.absdiff(gray[:, 1:], gray[:, :-1])
    diff_y = cv2.absdiff(gray[1:, :], gray[:-1, :])

    # Pad the differences to match the original image size
    diff_x = cv2.copyMakeBorder(diff_x, 0, 0, 0, 1, cv2.BORDER_CONSTANT, value=0)
    diff_y = cv2.copyMakeBorder(diff_y, 0, 1, 0, 0, cv2.BORDER_CONSTANT, value=0)

    # Combine the differences
    binary_diff_map = np.maximum(diff_x, diff_y)

    # Threshold the map to make it binary (1 for differences, 0 for no differences)
    _, binary_diff_map = cv2.threshold(binary_diff_map, 1, 1, cv2.THRESH_BINARY)

    return binary_diff_map

def create_filtered_difference_map(image, threshold=200):
    """Create filtered difference maps where HSV and RGB channels."""
    # Convert the image to HSV and RGB color spaces
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Compute gradient magnitudes for HSV channels
    h, s, v = cv2.split(hsv_image)
    grad_x_h = cv2.Sobel(h, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_h = cv2.Sobel(h, cv2.CV_64F, 0, 1, ksize=3)
    diff_h = cv2.magnitude(grad_x_h, grad_y_h)

    grad_x_s = cv2.Sobel(s, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_s = cv2.Sobel(s, cv2.CV_64F, 0, 1, ksize=3)
    diff_s = cv2.magnitude(grad_x_s, grad_y_s)

    grad_x_v = cv2.Sobel(v, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_v = cv2.Sobel(v, cv2.CV_64F, 0, 1, ksize=3)
    diff_v = cv2.magnitude(grad_x_v, grad_y_v)

    # Combine HSV differences
    hsv_diff = cv2.merge((diff_h, diff_s, diff_v))
    hsv_diff_normalized = cv2.normalize(hsv_diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Compute gradient magnitudes for RGB channels
    r, g, b = cv2.split(rgb_image)
    grad_x_r = cv2.Sobel(r, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_r = cv2.Sobel(r, cv2.CV_64F, 0, 1, ksize=3)
    diff_r = cv2.magnitude(grad_x_r, grad_y_r)

    grad_x_g = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_g = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    diff_g = cv2.magnitude(grad_x_g, grad_y_g)

    grad_x_b = cv2.Sobel(b, cv2.CV_64F, 1, 0, ksize=3)
    grad_y_b = cv2.Sobel(b, cv2.CV_64F, 0, 1, ksize=3)
    diff_b = cv2.magnitude(grad_x_b, grad_y_b)

    # Combine RGB differences
    rgb_diff = cv2.merge((diff_r, diff_g, diff_b))
    rgb_diff_normalized = cv2.normalize(rgb_diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Apply a threshold to highlight prominent differences for HSV and RGB
    _, hsv_filtered_diff_map = cv2.threshold(hsv_diff_normalized, threshold, 255, cv2.THRESH_BINARY)
    _, rgb_filtered_diff_map = cv2.threshold(rgb_diff_normalized, threshold, 255, cv2.THRESH_BINARY)

    return hsv_filtered_diff_map, rgb_filtered_diff_map

# Load the attached screenshot as the test image
image_path = "yolo-cat/website_screenshots/anthropic.com.png"  # Replace with the actual path to the screenshot
background = cv2.imread(image_path)

# Perform normal Canny edge detection
edges = cv2.Canny(cv2.cvtColor(background, cv2.COLOR_BGR2GRAY), 100, 200)

# Run dynamic edge detection to get the difference map
_, _, difference_map, _, _, _ = dynamic_edge_detection(background)

# Apply Gaussian blur to denoise the main difference map
difference_map_denoised = cv2.GaussianBlur(difference_map, (5, 5), 0)

# Threshold the denoised difference map to highlight prominent edges
_, difference_map_denoised_thresholded = cv2.threshold(difference_map_denoised, 5, 255, cv2.THRESH_BINARY)

# Calculate the consistency map
consistency_map = calculate_consistency_map(background)

# Convert the image to LAB color space
lab_image = cv2.cvtColor(background, cv2.COLOR_BGR2Lab)

# Compute the local color complexity
color_complexity_map = compute_local_complexity(lab_image)

# Calculate difference map (gradient magnitude) on the HSV color space
hsv_image = cv2.cvtColor(background, cv2.COLOR_BGR2HSV)
h, s, v = cv2.split(hsv_image)

# Calculate gradient magnitude for each HSV channel
grad_x_h = cv2.Sobel(h, cv2.CV_64F, 1, 0, ksize=3)
grad_y_h = cv2.Sobel(h, cv2.CV_64F, 0, 1, ksize=3)
difference_map_h = cv2.magnitude(grad_x_h, grad_y_h)

grad_x_s = cv2.Sobel(s, cv2.CV_64F, 1, 0, ksize=3)
grad_y_s = cv2.Sobel(s, cv2.CV_64F, 0, 1, ksize=3)
difference_map_s = cv2.magnitude(grad_x_s, grad_y_s)

grad_x_v = cv2.Sobel(v, cv2.CV_64F, 1, 0, ksize=3)
grad_y_v = cv2.Sobel(v, cv2.CV_64F, 0, 1, ksize=3)
difference_map_v = cv2.magnitude(grad_x_v, grad_y_v)

# Combine the gradient magnitudes from all HSV channels
difference_map_hsv = cv2.merge((difference_map_h, difference_map_s, difference_map_v))

# Normalize the combined HSV difference map for visualization
difference_map_hsv_normalized = cv2.normalize(difference_map_hsv, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

# Create the binary difference map
binary_diff_map = create_binary_difference_map(background)

# Create the filtered difference maps for HSV and RGB
hsv_filtered_diff_map, rgb_filtered_diff_map = create_filtered_difference_map(background)

# Apply Gaussian blur to denoise the filtered maps
hsv_filtered_diff_map_denoised = cv2.GaussianBlur(hsv_filtered_diff_map, (5, 5), 0)
rgb_filtered_diff_map_denoised = cv2.GaussianBlur(rgb_filtered_diff_map, (5, 5), 0)

# Display the original image
plt.figure(figsize=(10, 5))
plt.title("Original Image")
plt.imshow(cv2.cvtColor(background, cv2.COLOR_BGR2RGB)) # Convert BGR to RGB for correct display
plt.axis("off")

# Display the difference map with blue, red, and green edges
plt.figure(figsize=(10, 5))
plt.title("Difference Map")
plt.imshow(difference_map)
plt.axis("off")

# Display the denoised main difference map
plt.figure(figsize=(10, 5))
plt.title("Denoised Difference Map")
plt.imshow(difference_map_denoised)
plt.axis("off")

# Display the denoised and thresholded main difference map
plt.figure(figsize=(10, 5))
plt.title("Denoised and Thresholded Difference Map")
plt.imshow(difference_map_denoised_thresholded, cmap="gray")
plt.axis("off")

# Display the consistency map
plt.figure(figsize=(10, 5))
plt.title("Consistency Map")
plt.imshow(consistency_map, cmap="gray")
plt.axis("off")

# Display the color complexity map
plt.figure(figsize=(10, 5))
plt.title("Color Complexity Map")
plt.imshow(color_complexity_map, cmap="viridis")
plt.axis("off")

# Display the difference map and color complexity map side by side
plt.figure(figsize=(15, 5))

plt.subplot(1, 2, 1)
plt.title("Difference Map")
plt.imshow(difference_map)
plt.axis("off")

plt.subplot(1, 2, 2)
plt.title("Color Complexity Map")
plt.imshow(color_complexity_map, cmap="viridis")
plt.axis("off")

# Display the HSV difference map
plt.figure(figsize=(10, 5))
plt.title("HSV Difference Map")
plt.imshow(difference_map_hsv_normalized)
plt.axis("off")

# Display the binary difference map
plt.figure(figsize=(10, 5))
plt.title("Binary Difference Map")
plt.imshow(binary_diff_map, cmap="gray")
plt.axis("off")

# Ensure the thresholded difference map is single-channel
difference_map_denoised_thresholded_gray = cv2.cvtColor(difference_map_denoised_thresholded, cv2.COLOR_BGR2GRAY) if len(difference_map_denoised_thresholded.shape) == 3 else difference_map_denoised_thresholded

# Find contours on the single-channel thresholded main difference map
contours, _ = cv2.findContours(difference_map_denoised_thresholded_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Draw contours on a copy of the original image
contour_image = background.copy()
cv2.drawContours(contour_image, contours, -1, (0, 255, 0), 2)

# Display the image with contours
plt.figure(figsize=(10, 5))
plt.title("Contours on Denoised Difference Map")
plt.imshow(cv2.cvtColor(contour_image, cv2.COLOR_BGR2RGB))
plt.axis("off")

# Filter contours based on size and shape (perimeter and aspect ratio)
filtered_contours = []
min_area = 600  # Minimum area threshold

for contour in contours:
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)

    # Calculate aspect ratio (bounding rectangle width/height)
    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = float(w) / h if h > 0 else 0

    # Keep contours that meet the area and shape criteria
    if min_area <= area and .3 <= aspect_ratio <= 5 and perimeter / area < .3:
        filtered_contours.append(contour)

# Draw the filtered contours on a copy of the original image
filtered_contour_image = background.copy()
cv2.drawContours(filtered_contour_image, filtered_contours, -1, (0, 255, 0), 2)

# Display the image with filtered contours
plt.figure(figsize=(10, 5))
plt.title("Filtered Contours")
plt.imshow(cv2.cvtColor(filtered_contour_image, cv2.COLOR_BGR2RGB))
plt.axis("off")

# Add a feature to increase certainty for contours that are consistently and significantly different from their surroundings
certainty_map = np.zeros_like(difference_map_denoised_thresholded, dtype=np.float32)
for contour in contours:
    # Ensure the mask is properly initialized and of type CV_8U
    mask = np.zeros_like(difference_map_denoised_thresholded, dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    mask = mask.astype(np.uint8)

    # Calculate the mean difference value within the contour
    mean_difference = cv2.mean(difference_map_denoised, mask=mask)[0]

    # Calculate the mean difference value in the surrounding area
    dilated_mask = cv2.dilate(mask, kernel=np.ones((5, 5), np.uint8), iterations=1)
    surrounding_mask = cv2.subtract(dilated_mask, mask)
    mean_surrounding_difference = cv2.mean(difference_map_denoised, mask=surrounding_mask)[0]

    # Increase certainty if the contour is significantly different from its surroundings
    if mean_difference - mean_surrounding_difference > 20:  # Threshold for significant difference
        certainty_map = cv2.add(certainty_map, mask.astype(np.float32))

# Normalize the certainty map for visualization
certainty_map_normalized = cv2.normalize(certainty_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

# Display the certainty map
plt.figure(figsize=(10, 5))
plt.title("Certainty Map")
plt.imshow(certainty_map_normalized, cmap="hot")
plt.axis("off")
plt.show()