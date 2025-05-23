import cv2
import numpy as np

class ImageProcessor:
    def __init__(self):
        # Initialize parameters with default values
        self.blur_value = 5
        self.min_area = 500
        self.max_area = 50000
        self.canny_low = 50
        self.canny_high = 150
        self.edge_dilation = 3
        self.edge_erosion = 1
        self.kernel_size = 3
        self.enable_merge = True
        self.height_tolerance = 0.3
        self.vertical_tolerance = 0.5
        self.horizontal_gap_ratio = 1.0
        self.enable_vertical_merge = False
        self.left_align_tolerance = 0.1
        self.paragraph_height_tolerance = 0.4
        self.vertical_gap_ratio = 0.5
        self.enable_alignment_lines = True
        self.align_left_tol = 10
        self.align_right_tol = 10
        self.align_top_tol = 10
        self.align_bottom_tol = 10
        self.align_center_x_tol = 10
        self.align_center_y_tol = 10

    def process_image(self, original_image):
        """
        Performs the core image processing: grayscale conversion, blurring, Canny edge detection,
        morphological operations, contour finding, bounding box generation, merging,
        and finally drawing bounding boxes and alignment lines.
        """
        if original_image is None:
            return None, []

        # Create a copy to work with, so original image is not modified
        image = original_image.copy()

        # Convert to grayscale for edge detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to smooth the image and reduce noise
        blur_size = max(1, int(self.blur_value))
        if blur_size % 2 == 0:  # Ensure kernel size is odd for GaussianBlur
            blur_size += 1
        blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)

        # Canny edge detection to find strong and weak edges
        edges = cv2.Canny(blurred, self.canny_low, self.canny_high)

        # Morphological operations (dilation and erosion) on edges
        kernel_size = max(1, int(self.kernel_size))
        if kernel_size % 2 == 0:  # Ensure kernel size is odd for getStructuringElement
            kernel_size += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))

        if self.edge_dilation > 0:
            edges = cv2.dilate(edges, kernel, iterations=self.edge_dilation)
        if self.edge_erosion > 0:
            edges = cv2.erode(edges, kernel, iterations=self.edge_erosion)

        # Find contours from the processed edges
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Get bounding boxes for detected contours
        boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            # Filter contours by area to exclude very small noise or very large irrelevant regions
            if self.min_area <= area <= self.max_area:
                x, y, w, h = cv2.boundingRect(contour)
                boxes.append((x, y, w, h))

        # Merge horizontally aligned text boxes if enabled
        if self.enable_merge:
            boxes = self.merge_text_boxes(boxes)

        # Merge vertically aligned paragraphs if enabled
        if self.enable_vertical_merge:
            boxes = self.merge_paragraphs(boxes)

        # Draw bounding boxes on the image
        for x, y, w, h in boxes:
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2)  # Red bounding boxes

        # Draw alignment lines if the feature is enabled
        if self.enable_alignment_lines:
            self.draw_alignment_lines(image, boxes)

        return image, boxes

    def merge_text_boxes(self, boxes):
        """Merge bounding boxes that are likely part of the same text line."""
        if not boxes:
            return boxes

        # Sort boxes by y-coordinate (top to bottom) to process lines sequentially
        boxes = sorted(boxes, key=lambda b: b[1])
        merged = []  # List to hold the merged boxes

        for current_box in boxes:
            x1, y1, w1, h1 = current_box

            merged_with_existing = False
            # Try to merge the current box with any already merged box
            for i, merged_box in enumerate(merged):
                x2, y2, w2, h2 = merged_box

                # Calculate height similarity: ratio of smaller height to larger height
                height_ratio = min(h1, h2) / max(h1, h2) if max(h1, h2) > 0 else 0

                # Calculate vertical alignment based on center Y coordinates
                center1_y = y1 + h1 / 2
                center2_y = y2 + h2 / 2
                max_height = max(h1, h2)
                vertical_distance = abs(center1_y - center2_y)
                # Vertical alignment is 1 if centers are perfectly aligned, decreases with distance
                vertical_alignment = 1 - (vertical_distance / max_height) if max_height > 0 else 0

                # Calculate horizontal gap between boxes
                right_edge1 = x1 + w1
                right_edge2 = x2 + w2
                left_edge1 = x1
                left_edge2 = x2

                horizontal_gap = float('inf')
                if right_edge2 < left_edge1:  # merged_box is to the left of current_box
                    horizontal_gap = left_edge1 - right_edge2
                elif right_edge1 < left_edge2:  # current_box is to the left of merged_box
                    horizontal_gap = left_edge2 - right_edge1
                else:  # boxes overlap horizontally
                    horizontal_gap = 0

                # Calculate maximum allowed horizontal gap based on height and user ratio
                max_allowed_gap = max_height * self.horizontal_gap_ratio

                # Check all merging conditions
                if (height_ratio >= (1 - self.height_tolerance)) and vertical_alignment >= (1 - self.vertical_tolerance) and horizontal_gap <= max_allowed_gap:

                    # Merge the boxes by taking the min/max of their coordinates
                    new_x = min(x1, x2)
                    new_y = min(y1, y2)
                    new_right = max(x1 + w1, x2 + w2)
                    new_bottom = max(y1 + h1, y2 + h2)
                    new_w = new_right - new_x
                    new_h = new_bottom - new_y

                    merged[i] = (new_x, new_y, new_w, new_h)  # Update the merged box
                    merged_with_existing = True
                    break  # Stop checking once merged

            if not merged_with_existing:
                merged.append(current_box)  # If no merge occurred, add as a new box

        return merged

    def merge_paragraphs(self, boxes):
        """Merge text line boxes that are vertically aligned and could be part of the same paragraph."""
        if not boxes:
            return boxes

        # Sort boxes by y-coordinate (top to bottom)
        boxes = sorted(boxes, key=lambda b: b[1])
        merged = []

        for current_box in boxes:
            x1, y1, w1, h1 = current_box

            merged_with_existing = False
            for i, merged_box in enumerate(merged):
                x2, y2, w2, h2 = merged_box

                # Calculate left alignment similarity
                left_edge1 = x1
                left_edge2 = x2
                max_width = max(w1, w2)
                left_distance = abs(left_edge1 - left_edge2)
                # Max allowed left distance is relative to the wider box's width
                max_allowed_left_distance = max_width * self.left_align_tolerance

                # Calculate height similarity
                height_ratio = min(h1, h2) / max(h1, h2) if max(h1, h2) > 0 else 0

                # Calculate vertical gap between boxes
                bottom_edge1 = y1 + h1
                bottom_edge2 = y2 + h2
                top_edge1 = y1
                top_edge2 = y2

                vertical_gap = float('inf')
                if bottom_edge2 < top_edge1:  # merged_box is above current_box
                    vertical_gap = top_edge1 - bottom_edge2
                elif bottom_edge1 < top_edge2:  # current_box is above merged_box
                    vertical_gap = top_edge2 - bottom_edge1
                else:  # boxes overlap vertically (shouldn't happen for distinct lines, but for robustness)
                    vertical_gap = 0

                # Calculate maximum allowed vertical gap based on height and user ratio
                max_height = max(h1, h2)
                max_allowed_vertical_gap = max_height * self.vertical_gap_ratio

                # Check all merging conditions for paragraphs
                if (left_distance <= max_allowed_left_distance and
                    height_ratio >= (1 - self.paragraph_height_tolerance) and
                    vertical_gap <= max_allowed_vertical_gap):

                    # Merge the boxes
                    new_x = min(x1, x2)
                    new_y = min(y1, y2)
                    new_right = max(x1 + w1, x2 + w2)
                    new_bottom = max(y1 + h1, y2 + h2)
                    new_w = new_right - new_x
                    new_h = new_bottom - new_y

                    merged[i] = (new_x, new_y, new_w, new_h)
                    merged_with_existing = True
                    break

            if not merged_with_existing:
                merged.append(current_box)

        return merged

    def _get_alignment_groups(self, coords, tolerance):
        """Helper function to group coordinates that are within a given tolerance."""
        if not coords:
            return []

        aligned_groups = []
        # Sort coordinates to make grouping easier
        sorted_coords = sorted(coords)

        for coord in sorted_coords:
            found_group = False
            for group in aligned_groups:
                # Check if the current coordinate is close to the reference point of an existing group
                if abs(coord - group[0]) <= tolerance:
                    group.append(coord)
                    found_group = True
                    break
            if not found_group:
                # If no suitable group found, start a new group with the current coordinate
                aligned_groups.append([coord])
        return aligned_groups

    def draw_alignment_lines(self, image, boxes):
        """Draws alignment lines on the image based on detected bounding boxes."""
        if not boxes or image is None:
            return

        img_height, img_width, _ = image.shape

        # Define colors for different alignment lines (BGR format)
        COLOR_LEFT = (0, 255, 0)      # Green
        COLOR_RIGHT = (255, 255, 0)   # Cyan
        COLOR_TOP = (255, 0, 0)       # Blue
        COLOR_BOTTOM = (255, 0, 255)  # Magenta
        COLOR_CENTER_X = (0, 255, 255) # Yellow
        COLOR_CENTER_Y = (0, 165, 255) # Orange

        line_thickness = 1

        # Collect coordinates for each type of alignment from all bounding boxes
        left_coords = [x for x, y, w, h in boxes]
        right_coords = [x + w for x, y, w, h in boxes]
        top_coords = [y for x, y, w, h in boxes]
        bottom_coords = [y + h for x, y, w, h in boxes]
        center_x_coords = [x + w // 2 for x, y, w, h in boxes]
        center_y_coords = [y + h // 2 for x, y, w, h in boxes]

        # Draw lines for each alignment type
        for coords, tolerance, color, is_horizontal_line in [
            (left_coords, self.align_left_tol, COLOR_LEFT, False),
            (right_coords, self.align_right_tol, COLOR_RIGHT, False),
            (top_coords, self.align_top_tol, COLOR_TOP, True),
            (bottom_coords, self.align_bottom_tol, COLOR_BOTTOM, True),
            (center_x_coords, self.align_center_x_tol, COLOR_CENTER_X, False),
            (center_y_coords, self.align_center_y_tol, COLOR_CENTER_Y, True)
        ]:
            aligned_groups = self._get_alignment_groups(coords, tolerance)
            for group in aligned_groups:
                if len(group) > 1:  # Only draw if there are at least two aligned elements
                    avg_coord = int(np.mean(group))
                    if is_horizontal_line:
                        cv2.line(image, (0, avg_coord), (img_width, avg_coord), color, line_thickness)
                    else:
                        cv2.line(image, (avg_coord, 0), (avg_coord, img_height), color, line_thickness)

    def calculate_alignment_ratio(self, boxes):
        """Calculate alignment ratio based on X and Y alignments."""
        if not boxes or len(boxes) < 2:
            return 0.0

        # Get all alignment coordinates
        left_coords = [b[0] for b in boxes]  # left x
        right_coords = [b[0] + b[2] for b in boxes]  # right x
        top_coords = [b[1] for b in boxes]  # top y
        bottom_coords = [b[1] + b[3] for b in boxes]  # bottom y
        center_x_coords = [b[0] + b[2] // 2 for b in boxes]  # center x
        center_y_coords = [b[1] + b[3] // 2 for b in boxes]  # center y

        # Check X-axis alignments (left, right, center_x)
        x_aligned = False
        for coords, tolerance in [
            (left_coords, self.align_left_tol),
            (right_coords, self.align_right_tol),
            (center_x_coords, self.align_center_x_tol)
        ]:
            groups = self._get_alignment_groups(coords, tolerance)
            if any(len(group) == len(boxes) for group in groups):
                x_aligned = True
                break

        # Check Y-axis alignments (top, bottom, center_y)
        y_aligned = False
        for coords, tolerance in [
            (top_coords, self.align_top_tol),
            (bottom_coords, self.align_bottom_tol),
            (center_y_coords, self.align_center_y_tol)
        ]:
            groups = self._get_alignment_groups(coords, tolerance)
            if any(len(group) == len(boxes) for group in groups):
                y_aligned = True
                break

        # Calculate alignment ratio
        alignment_ratio = 0.0
        if x_aligned and y_aligned:
            alignment_ratio = 1.0
        elif x_aligned:
            alignment_ratio = 0.5
        elif y_aligned:
            alignment_ratio = 0.5

        return alignment_ratio

    def calculate_organization_score(self, boxes):
        """
        Calculates an organization score based on alignment ratio.
        The score is the alignment ratio raised to the power of 0.3 (to make it less sensitive),
        then scaled to 0-100.
        """
        if not boxes:
            return 0.0

        alignment_ratio = self.calculate_alignment_ratio(boxes)
        score = (alignment_ratio ** 0.3) * 100
        return min(100, max(0, score))
