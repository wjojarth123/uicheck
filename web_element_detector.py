import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
import json

# Helper class for a scrollable frame
class VerticalScrolledFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that can be used to contain other widgets.
    A canvas is created and a frame is placed inside it. The canvas is scrolled
    by the scrollbar, and the frame is scrolled with the canvas.
    """
    def __init__(self, parent, *args, **kw):
        ttk.Frame.__init__(self, parent, *args, **kw)

        # Create a canvas object and a vertical scrollbar for scrolling it
        vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=tk.FALSE)
        canvas = tk.Canvas(self, bd=0, highlightthickness=0,
                           yscrollcommand=vscrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.TRUE)
        vscrollbar.config(command=canvas.yview)

        # Reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        # Create a frame inside the canvas which will be scrolled with it
        self.interior = ttk.Frame(canvas)
        self.interior_id = canvas.create_window(0, 0, window=self.interior,
                                           anchor=tk.NW)

        # Bind the canvas to the scrollbar
        self.interior.bind('<Configure>', self._configure_interior)
        canvas.bind('<Configure>', self._configure_canvas)
        self.canvas = canvas # Store canvas for later use

    def _configure_interior(self, event):
        # Update the scrollbars to match the size of the interior frame.
        size = (self.interior.winfo_reqwidth(), self.interior.winfo_reqheight())
        self.canvas.config(scrollregion="0 0 %s %s" % size)
        if self.interior.winfo_reqwidth() != self.canvas.winfo_width():
            # Update the canvas's width to fit the interior frame.
            self.canvas.itemconfigure(self.interior_id, width=self.canvas.winfo_width())

    def _configure_canvas(self, event):
        if self.interior.winfo_reqwidth() != self.canvas.winfo_width():
            # Update the interior frame's width to fill the canvas.
            self.canvas.itemconfigure(self.interior_id, width=self.canvas.winfo_width())


class ElementDetector:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Edge Detection with Text Line Merging and Alignment Lines")
        self.root.geometry("1600x900") # Increased width for new panel

        # Initialize variables
        self.original_image = None
        self.processed_image = None
        self.display_image = None
        self.photo = None
        self.boxes = [] # Store detected boxes for alignment drawing and scoring

        # Parameters for basic detection (OpenCV)
        self.blur_value = tk.IntVar(value=5)
        self.min_area = tk.IntVar(value=500)
        self.max_area = tk.IntVar(value=50000)

        # NEW: Additional filtering parameters for OpenCV
        self.min_width = tk.IntVar(value=10)
        self.max_width = tk.IntVar(value=10000)
        self.min_height = tk.IntVar(value=10)
        self.max_height = tk.IntVar(value=10000)
        self.min_aspect_ratio = tk.DoubleVar(value=0.1) # min width/height ratio
        self.max_aspect_ratio = tk.DoubleVar(value=10.0) # max width/height ratio
        self.min_solidity = tk.DoubleVar(value=0.1) # min contour area / convex hull area

        # Edge-specific parameters (OpenCV)
        self.canny_low = tk.IntVar(value=50)
        self.canny_high = tk.IntVar(value=150)
        self.edge_dilation = tk.IntVar(value=3)
        self.edge_erosion = tk.IntVar(value=1)
        self.kernel_size = tk.IntVar(value=3)

        # Merging parameters for horizontal text lines
        self.enable_merge = tk.BooleanVar(value=True)
        self.height_tolerance = tk.DoubleVar(value=0.3)
        self.vertical_tolerance = tk.DoubleVar(value=0.5)
        self.horizontal_gap_ratio = tk.DoubleVar(value=1.0)  # Relative to height

        # Vertical merging parameters (for paragraphs)
        self.enable_vertical_merge = tk.BooleanVar(value=False)
        self.left_align_tolerance = tk.DoubleVar(value=0.1)  # Relative to width
        self.paragraph_height_tolerance = tk.DoubleVar(value=0.4)
        self.vertical_gap_ratio = tk.DoubleVar(value=0.5)  # Relative to height

        # Alignment line parameters
        self.enable_alignment_lines = tk.BooleanVar(value=True)
        self.align_left_tol = tk.IntVar(value=10) # Pixel tolerance for left alignment
        self.align_right_tol = tk.IntVar(value=10) # Pixel tolerance for right alignment
        self.align_top_tol = tk.IntVar(value=10) # Pixel tolerance for top alignment
        self.align_bottom_tol = tk.IntVar(value=10) # Pixel tolerance for bottom alignment
        self.align_center_x_tol = tk.IntVar(value=10) # Pixel tolerance for center X alignment
        self.align_center_y_tol = tk.IntVar(value=10) # Pixel tolerance for center Y alignment

        # Organization Score variables
        self.organization_score_label = None # To display the score
        self.current_organization_score = tk.StringVar(value="N/A")

        self.setup_ui()

    def setup_ui(self):
        # Main frame to hold all other frames
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Left Control Panel ---
        # This frame will contain the notebook for various settings
        control_panel_left = ttk.Frame(main_frame, width=350) # Fixed width for consistent layout
        control_panel_left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        control_panel_left.pack_propagate(False) # Prevent frame from resizing to content

        # Load image button
        ttk.Button(control_panel_left, text="Load Image", command=self.load_image).pack(pady=5, fill=tk.X)

        # Settings save/load buttons
        settings_frame = ttk.Frame(control_panel_left)
        settings_frame.pack(pady=5, fill=tk.X)
        ttk.Button(settings_frame, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT, expand=True, padx=(0, 5))
        ttk.Button(settings_frame, text="Load Settings", command=self.load_settings).pack(side=tk.RIGHT, expand=True)

        # Notebook for collapsible sections (tabs)
        self.notebook = ttk.Notebook(control_panel_left)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Tab 1: Basic Parameters (OpenCV) ---
        basic_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(basic_frame_tab, text="Basic Params")
        basic_frame = basic_frame_tab.interior # Get the interior frame to place widgets

        ttk.Label(basic_frame, text="Blur Kernel Size:").pack(pady=(5,0))
        blur_scale = ttk.Scale(basic_frame, from_=1, to=21, orient=tk.HORIZONTAL,
                               variable=self.blur_value, command=self.on_parameter_change)
        blur_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.blur_value).pack()

        ttk.Label(basic_frame, text="Min Area:").pack(pady=(5,0))
        min_area_scale = ttk.Scale(basic_frame, from_=10, to=5000, orient=tk.HORIZONTAL,
                                   variable=self.min_area, command=self.on_parameter_change)
        min_area_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_area).pack()

        ttk.Label(basic_frame, text="Max Area:").pack(pady=(5,0))
        max_area_scale = ttk.Scale(basic_frame, from_=1000, to=100000, orient=tk.HORIZONTAL,
                                   variable=self.max_area, command=self.on_parameter_change)
        max_area_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.max_area).pack()

        # NEW: Min/Max Width
        ttk.Label(basic_frame, text="Min Width:").pack(pady=(5,0))
        min_width_scale = ttk.Scale(basic_frame, from_=1, to=500, orient=tk.HORIZONTAL,
                                    variable=self.min_width, command=self.on_parameter_change)
        min_width_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_width).pack()

        ttk.Label(basic_frame, text="Max Width:").pack(pady=(5,0))
        max_width_scale = ttk.Scale(basic_frame, from_=100, to=2000, orient=tk.HORIZONTAL,
                                    variable=self.max_width, command=self.on_parameter_change)
        max_width_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.max_width).pack()

        # NEW: Min/Max Height
        ttk.Label(basic_frame, text="Min Height:").pack(pady=(5,0))
        min_height_scale = ttk.Scale(basic_frame, from_=1, to=500, orient=tk.HORIZONTAL,
                                     variable=self.min_height, command=self.on_parameter_change)
        min_height_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_height).pack()

        ttk.Label(basic_frame, text="Max Height:").pack(pady=(5,0))
        max_height_scale = ttk.Scale(basic_frame, from_=100, to=2000, orient=tk.HORIZONTAL,
                                     variable=self.max_height, command=self.on_parameter_change)
        max_height_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.max_height).pack()

        # NEW: Aspect Ratio
        ttk.Label(basic_frame, text="Min Aspect Ratio (W/H):").pack(pady=(5,0))
        min_aspect_ratio_scale = ttk.Scale(basic_frame, from_=0.01, to=1.0, orient=tk.HORIZONTAL,
                                           variable=self.min_aspect_ratio, command=self.on_parameter_change)
        min_aspect_ratio_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_aspect_ratio).pack()

        ttk.Label(basic_frame, text="Max Aspect Ratio (W/H):").pack(pady=(5,0))
        max_aspect_ratio_scale = ttk.Scale(basic_frame, from_=1.0, to=20.0, orient=tk.HORIZONTAL,
                                           variable=self.max_aspect_ratio, command=self.on_parameter_change)
        max_aspect_ratio_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.max_aspect_ratio).pack()

        # NEW: Min Solidity
        ttk.Label(basic_frame, text="Min Solidity (0-1):").pack(pady=(5,0))
        # Removed 'resolution' option as ttk.Scale does not support it
        min_solidity_scale = ttk.Scale(basic_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL,
                                       variable=self.min_solidity, command=self.on_parameter_change)
        min_solidity_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_solidity).pack()


        # --- Tab 2: Edge Detection Parameters (OpenCV) ---
        edge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(edge_frame_tab, text="Edge Detection")
        edge_frame = edge_frame_tab.interior

        ttk.Label(edge_frame, text="Canny Low Threshold:").pack(pady=(5,0))
        canny_low_scale = ttk.Scale(edge_frame, from_=10, to=200, orient=tk.HORIZONTAL,
                                     variable=self.canny_low, command=self.on_parameter_change)
        canny_low_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.canny_low).pack()

        ttk.Label(edge_frame, text="Canny High Threshold:").pack(pady=(5,0))
        canny_high_scale = ttk.Scale(edge_frame, from_=50, to=400, orient=tk.HORIZONTAL,
                                      variable=self.canny_high, command=self.on_parameter_change)
        canny_high_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.canny_high).pack()

        ttk.Label(edge_frame, text="Edge Dilation:").pack(pady=(5,0))
        edge_dil_scale = ttk.Scale(edge_frame, from_=0, to=10, orient=tk.HORIZONTAL,
                                    variable=self.edge_dilation, command=self.on_parameter_change)
        edge_dil_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.edge_dilation).pack()

        ttk.Label(edge_frame, text="Edge Erosion:").pack(pady=(5,0))
        edge_ero_scale = ttk.Scale(edge_frame, from_=0, to=10, orient=tk.HORIZONTAL,
                                    variable=self.edge_erosion, command=self.on_parameter_change)
        edge_ero_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.edge_erosion).pack()

        ttk.Label(edge_frame, text="Morphology Kernel Size:").pack(pady=(5,0))
        kernel_scale = ttk.Scale(edge_frame, from_=1, to=15, orient=tk.HORIZONTAL,
                                 variable=self.kernel_size, command=self.on_parameter_change)
        kernel_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.kernel_size).pack()

        # --- Tab 3: Text Line Merging Parameters ---
        merge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(merge_frame_tab, text="Text Merging")
        merge_frame = merge_frame_tab.interior

        ttk.Checkbutton(merge_frame, text="Enable Merging", variable=self.enable_merge,
                        command=self.on_parameter_change).pack(pady=(5,0))

        ttk.Label(merge_frame, text="Height Tolerance (0-1):").pack(pady=(5,0))
        height_tol_scale = ttk.Scale(merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                     variable=self.height_tolerance, command=self.on_parameter_change)
        height_tol_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.height_tolerance).pack()

        ttk.Label(merge_frame, text="Vertical Alignment Tolerance (0-1):").pack(pady=(5,0))
        vert_tol_scale = ttk.Scale(merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                   variable=self.vertical_tolerance, command=self.on_parameter_change)
        vert_tol_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.vertical_tolerance).pack()

        ttk.Label(merge_frame, text="Horizontal Gap Ratio (relative to height):").pack(pady=(5,0))
        gap_scale = ttk.Scale(merge_frame, from_=0.1, to=5.0, orient=tk.HORIZONTAL,
                              variable=self.horizontal_gap_ratio, command=self.on_parameter_change)
        gap_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.horizontal_gap_ratio).pack()

        # --- Tab 4: Paragraph Merging Parameters (Vertical) ---
        vertical_merge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(vertical_merge_frame_tab, text="Paragraph Merging")
        vertical_merge_frame = vertical_merge_frame_tab.interior

        ttk.Checkbutton(vertical_merge_frame, text="Enable Vertical Merging", variable=self.enable_vertical_merge,
                        command=self.on_parameter_change).pack(pady=(5,0))

        ttk.Label(vertical_merge_frame, text="Left Alignment Tolerance (relative to width):").pack(pady=(5,0))
        left_align_scale = ttk.Scale(vertical_merge_frame, from_=0.01, to=0.5, orient=tk.HORIZONTAL,
                                     variable=self.left_align_tolerance, command=self.on_parameter_change)
        left_align_scale.pack(fill=tk.X)
        ttk.Label(vertical_merge_frame, textvariable=self.left_align_tolerance).pack()

        ttk.Label(vertical_merge_frame, text="Paragraph Height Tolerance (0-1):").pack(pady=(5,0))
        para_height_scale = ttk.Scale(vertical_merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                      variable=self.paragraph_height_tolerance, command=self.on_parameter_change)
        para_height_scale.pack(fill=tk.X)
        ttk.Label(vertical_merge_frame, textvariable=self.paragraph_height_tolerance).pack()

        ttk.Label(vertical_merge_frame, text="Vertical Gap Ratio (relative to height):").pack(pady=(5,0))
        vert_gap_scale = ttk.Scale(vertical_merge_frame, from_=0.1, to=3.0, orient=tk.HORIZONTAL,
                                   variable=self.vertical_gap_ratio, command=self.on_parameter_change)
        vert_gap_scale.pack(fill=tk.X)
        ttk.Label(vertical_merge_frame, textvariable=self.vertical_gap_ratio).pack()


        # Information label
        info_frame = ttk.LabelFrame(control_panel_left, text="Information", padding=5)
        info_frame.pack(pady=10, fill=tk.X)

        explanation_text = """EDGE DETECTION THRESHOLDS:

Canny edge detection uses two thresholds:
• Low Threshold: Pixels with gradient below this are not edges
• High Threshold: Pixels with gradient above this are strong edges
• Pixels between thresholds become edges only if connected to strong edges

MERGING PARAMETERS:
• Height Tolerance: How different heights can be (0=same, 1=any)
• Vertical Tolerance: How aligned centers must be (0=perfect, 1=loose)
• Horizontal Gap Ratio: Max gap as multiple of box height

PARAGRAPH MERGING:
• Left Alignment Tolerance: How aligned left edges must be (relative to width)
• Paragraph Height Tolerance: How different line heights can be
• Vertical Gap Ratio: Max vertical gap as multiple of box height

ADDITIONAL FILTERS:
• Min/Max Width/Height: Filter boxes by absolute dimensions.
• Aspect Ratio: Filter boxes by width/height ratio (e.g., to remove very thin or wide boxes).
• Solidity: Filter boxes by how "solid" their shape is (contour area / convex hull area).
"""

        # Using tk.Label for wraplength support
        explanation_label = tk.Label(info_frame, text=explanation_text, wraplength=280, justify=tk.LEFT)
        explanation_label.pack()

        self.info_label = tk.Label(info_frame, text="No image loaded", wraplength=200, font=('TkDefaultFont', 9, 'bold'))
        self.info_label.pack(pady=(10, 0))

        # --- Image display frame ---
        image_frame = ttk.LabelFrame(main_frame, text="Image", padding=10)
        image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 10)) # Adjusted packing

        # Canvas for image display
        self.canvas = tk.Canvas(image_frame, bg='gray')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Scrollbars for canvas
        v_scrollbar = ttk.Scrollbar(image_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar = ttk.Scrollbar(image_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # --- Right Control Panel (Alignment Settings & Score) ---
        # This frame will contain the alignment settings and the new score tool
        control_panel_right = ttk.Frame(main_frame, width=350) # Fixed width
        control_panel_right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        control_panel_right.pack_propagate(False)

        # Alignment settings are in a scrollable frame
        alignment_settings_frame_tab = VerticalScrolledFrame(control_panel_right)
        alignment_settings_frame_tab.pack(fill=tk.BOTH, expand=True)
        alignment_settings_frame = alignment_settings_frame_tab.interior

        ttk.Label(alignment_settings_frame, text="Alignment Line Settings").pack(pady=(5,0))
        ttk.Checkbutton(alignment_settings_frame, text="Enable Alignment Lines", variable=self.enable_alignment_lines,
                        command=self.on_parameter_change).pack(pady=(5,0))

        ttk.Label(alignment_settings_frame, text="Left Alignment Tolerance (px):").pack(pady=(5,0))
        align_left_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                     variable=self.align_left_tol, command=self.on_parameter_change)
        align_left_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_left_tol).pack()

        ttk.Label(alignment_settings_frame, text="Right Alignment Tolerance (px):").pack(pady=(5,0))
        align_right_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                      variable=self.align_right_tol, command=self.on_parameter_change)
        align_right_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_right_tol).pack()

        ttk.Label(alignment_settings_frame, text="Top Alignment Tolerance (px):").pack(pady=(5,0))
        align_top_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                    variable=self.align_top_tol, command=self.on_parameter_change)
        align_top_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_top_tol).pack()

        ttk.Label(alignment_settings_frame, text="Bottom Alignment Tolerance (px):").pack(pady=(5,0))
        align_bottom_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                       variable=self.align_bottom_tol, command=self.on_parameter_change)
        align_bottom_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_bottom_tol).pack()

        ttk.Label(alignment_settings_frame, text="Center X Alignment Tolerance (px):").pack(pady=(5,0))
        align_center_x_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                        variable=self.align_center_x_tol, command=self.on_parameter_change)
        align_center_x_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_center_x_tol).pack()

        ttk.Label(alignment_settings_frame, text="Center Y Alignment Tolerance (px):").pack(pady=(5,0))
        align_center_y_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                        variable=self.align_center_y_tol, command=self.on_parameter_change)
        align_center_y_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_center_y_tol).pack()

        # Organization Score Section
        score_frame = ttk.LabelFrame(alignment_settings_frame, text="Organization Score", padding=5)
        score_frame.pack(pady=10, fill=tk.X)

        ttk.Button(score_frame, text="Calculate Score", command=self.calculate_organization_score).pack(pady=5, fill=tk.X)
        ttk.Label(score_frame, text="Score:").pack(side=tk.LEFT, padx=(0, 5))
        self.organization_score_label = ttk.Label(score_frame, textvariable=self.current_organization_score, font=('TkDefaultFont', 12, 'bold'))
        self.organization_score_label.pack(side=tk.LEFT, expand=True)


    def load_image(self):
        """
        Opens a file dialog to select an image and loads it.
        Triggers image processing upon successful load.
        """
        file_path = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif")]
        )

        if file_path:
            try:
                self.original_image = cv2.imread(file_path)
                if self.original_image is None:
                    messagebox.showerror("Error", "Could not load the image. Please check the file path and format.")
                    return

                # Reset score when new image is loaded
                self.current_organization_score.set("N/A")

                # Start image processing in a separate thread to keep UI responsive
                threading.Thread(target=self.process_image, daemon=True).start()
                self.info_label.config(text=f"Image loaded: {self.original_image.shape[1]}x{self.original_image.shape[0]}")

            except Exception as e:
                messagebox.showerror("Error", f"Error loading image: {str(e)}")

    def process_image(self):
        """
        Performs the core image processing using the OpenCV pipeline,
        including new filtering parameters.
        """
        if self.original_image is None:
            return

        image = self.original_image.copy()
        
        # --- OpenCV Edge Detection Pipeline ---
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_size = max(1, int(self.blur_value.get()))
        if blur_size % 2 == 0:
            blur_size += 1
        blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
        edges = cv2.Canny(blurred, self.canny_low.get(), self.canny_high.get())
        kernel_size = max(1, int(self.kernel_size.get()))
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))

        if self.edge_dilation.get() > 0:
            edges = cv2.dilate(edges, kernel, iterations=self.edge_dilation.get())
        if self.edge_erosion.get() > 0:
            edges = cv2.erode(edges, kernel, iterations=self.edge_erosion.get())

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detected_boxes_raw = []
        for contour in contours:
            area = cv2.contourArea(contour)
            x, y, w, h = cv2.boundingRect(contour)
            
            # Calculate solidity (area of contour / area of its convex hull)
            # A value of 1 indicates a convex shape. Lower values indicate concavities.
            solidity = 0.0
            if cv2.contourArea(cv2.convexHull(contour)) > 0:
                solidity = area / cv2.contourArea(cv2.convexHull(contour))

            # Calculate aspect ratio (width / height)
            aspect_ratio = w / h if h > 0 else 0.0

            # Apply all filters
            if (self.min_area.get() <= area <= self.max_area.get() and
                self.min_width.get() <= w <= self.max_width.get() and
                self.min_height.get() <= h <= self.max_height.get() and
                self.min_aspect_ratio.get() <= aspect_ratio <= self.max_aspect_ratio.get() and
                solidity >= self.min_solidity.get()):
                detected_boxes_raw.append((x, y, w, h))

        # Apply merging to filtered boxes
        detected_boxes_merged = detected_boxes_raw
        if self.enable_merge.get():
            detected_boxes_merged = self.merge_text_boxes(detected_boxes_merged)

        if self.enable_vertical_merge.get():
            detected_boxes_merged = self.merge_paragraphs(detected_boxes_merged)

        self.boxes = detected_boxes_merged # Store the final set of boxes

        # Draw bounding boxes
        count = 0
        for x, y, w, h in self.boxes:
            cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2) # Red bounding boxes
            cv2.putText(image, f'#{count}', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            count += 1

        # Draw alignment lines if enabled
        if self.enable_alignment_lines.get():
            self.draw_alignment_lines(image, self.boxes)

        self.processed_image = image
        # Update the display and info label on the main thread
        self.root.after(0, self.update_display)
        self.root.after(0, lambda: self.info_label.config(text=f"Detected {count} elements using OpenCV"))

    def merge_text_boxes(self, boxes):
        """
        Merge bounding boxes that are likely part of the same text line.
        Boxes are merged if they have similar heights and vertical alignment.
        Horizontal gap is now relative to box height.
        """
        if not boxes:
            return boxes

        # Sort boxes by y-coordinate (top to bottom) to process lines sequentially
        boxes = sorted(boxes, key=lambda b: b[1])
        merged = [] # List to hold the merged boxes

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
                max_allowed_gap = max_height * self.horizontal_gap_ratio.get()

                # Check all merging conditions
                if (height_ratio >= (1 - self.height_tolerance.get()) and
                    vertical_alignment >= (1 - self.vertical_tolerance.get()) and
                    horizontal_gap <= max_allowed_gap):

                    # Merge the boxes by taking the min/max of their coordinates
                    new_x = min(x1, x2)
                    new_y = min(y1, y2)
                    new_right = max(x1 + w1, x2 + w2)
                    new_bottom = max(y1 + h1, y2 + h2)
                    new_w = new_right - new_x
                    new_h = new_bottom - new_y

                    merged[i] = (new_x, new_y, new_w, new_h) # Update the merged box
                    merged_with_existing = True
                    break # Stop checking once merged

            if not merged_with_existing:
                merged.append(current_box) # If no merge occurred, add as a new box

        return merged

    def merge_paragraphs(self, boxes):
        """
        Merge text line boxes that are vertically aligned and could be part of the same paragraph.
        Boxes are merged if they have similar left alignment and compatible heights.
        """
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
                max_allowed_left_distance = max_width * self.left_align_tolerance.get()

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
                max_allowed_vertical_gap = max_height * self.vertical_gap_ratio.get()

                # Check all merging conditions for paragraphs
                if (left_distance <= max_allowed_left_distance and
                    height_ratio >= (1 - self.paragraph_height_tolerance.get()) and
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
        """
        Helper function to group coordinates that are within a given tolerance.
        Returns a list of lists, where each inner list is a group of aligned coordinates.
        """
        if not coords:
            return []

        aligned_groups = []
        # Sort coordinates to make grouping easier
        sorted_coords = sorted(coords)

        for coord in sorted_coords:
            found_group = False
            for group in aligned_groups:
                # Check if the current coordinate is close to the reference point of an existing group.
                # We use the first element of the group as the reference.
                if abs(coord - group[0]) <= tolerance:
                    group.append(coord)
                    found_group = True
                    break
            if not found_group:
                # If no suitable group found, start a new group with the current coordinate
                aligned_groups.append([coord])
        return aligned_groups

    def draw_alignment_lines(self, image, boxes):
        """
        Draws alignment lines on the image based on detected bounding boxes.
        Lines appear when multiple elements are aligned (left, right, top, bottom, center).
        """
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
        for coords, tolerance_var, color, is_horizontal_line in [
            (left_coords, self.align_left_tol, COLOR_LEFT, False),
            (right_coords, self.align_right_tol, COLOR_RIGHT, False),
            (top_coords, self.align_top_tol, COLOR_TOP, True),
            (bottom_coords, self.align_bottom_tol, COLOR_BOTTOM, True),
            (center_x_coords, self.align_center_x_tol, COLOR_CENTER_X, False),
            (center_y_coords, self.align_center_y_tol, COLOR_CENTER_Y, True)
        ]:
            tolerance = tolerance_var.get()
            aligned_groups = self._get_alignment_groups(coords, tolerance)
            for group in aligned_groups:
                if len(group) > 1: # Only draw if there are at least two aligned elements
                    avg_coord = int(np.mean(group))
                    if is_horizontal_line:
                        cv2.line(image, (0, avg_coord), (img_width, avg_coord), color, line_thickness)
                    else:
                        cv2.line(image, (avg_coord, 0), (avg_coord, img_height), color, line_thickness)

    def calculate_organization_score(self):
        """
        Calculates an organization score based on alignment and overlap of bounding boxes.
        The score is normalized to 0-100.
        """
        if not self.boxes:
            self.current_organization_score.set("N/A (No elements)")
            return

        num_boxes = len(self.boxes)
        alignment_score = 0
        max_possible_alignment_score = 0

        # --- Calculate Alignment Score ---
        # Iterate through each alignment type (left, right, top, bottom, center X, center Y)
        alignment_types = [
            (self.align_left_tol, [b[0] for b in self.boxes]), # Left edge x-coordinates
            (self.align_right_tol, [b[0] + b[2] for b in self.boxes]), # Right edge x-coordinates
            (self.align_top_tol, [b[1] for b in self.boxes]), # Top edge y-coordinates
            (self.align_bottom_tol, [b[1] + b[3] for b in self.boxes]), # Bottom edge y-coordinates
            (self.align_center_x_tol, [b[0] + b[2] // 2 for b in self.boxes]), # Center x-coordinates
            (self.align_center_y_tol, [b[1] + b[3] // 2 for b in self.boxes]) # Center y-coordinates
        ]

        for tolerance_var, coords in alignment_types:
            tolerance = tolerance_var.get()
            # Get groups of coordinates that are aligned within the given tolerance
            groups = self._get_alignment_groups(coords, tolerance)
            for group in groups:
                if len(group) > 1:
                    # For each group of aligned elements, add points to the alignment score.
                    # A group of N elements means N-1 "alignments" (e.g., 2 elements = 1 alignment, 3 elements = 2 alignments).
                    alignment_score += (len(group) - 1)
            # Calculate the maximum possible alignment score for this axis.
            # If all boxes could perfectly align on this axis, the score would be (num_boxes - 1).
            if num_boxes > 1:
                max_possible_alignment_score += (num_boxes - 1)

        # Normalize the alignment score to a value between 0 and 1.
        # This makes it independent of the number of boxes or alignment types.
        normalized_alignment_score = 0
        if max_possible_alignment_score > 0:
            normalized_alignment_score = alignment_score / max_possible_alignment_score

        # --- Calculate Overlap Penalty ---
        total_overlap_area = 0
        # Calculate the sum of areas of all individual bounding boxes.
        total_box_area = sum(b[2] * b[3] for b in self.boxes)

        # Iterate through all unique pairs of bounding boxes to find overlaps.
        for i in range(num_boxes):
            for j in range(i + 1, num_boxes): # Start from i+1 to avoid duplicate pairs and self-comparison
                box1 = self.boxes[i]
                box2 = self.boxes[j]

                # Extract coordinates for readability
                x1, y1, w1, h1 = box1
                x2, y2, w2, h2 = box2

                # Calculate the intersection rectangle's coordinates
                # The rightmost left edge
                intersect_x1 = max(x1, x2)
                # The bottommost top edge
                intersect_y1 = max(y1, y2)
                # The leftmost right edge
                intersect_x2 = min(x1 + w1, x2 + w2)
                # The topmost bottom edge
                intersect_y2 = min(y1 + h1, y2 + h2)

                # Calculate overlap width and height. If no overlap, these will be 0 or negative.
                x_overlap = max(0, intersect_x2 - intersect_x1)
                y_overlap = max(0, intersect_y2 - intersect_y1)

                # If there's overlap in both dimensions, add the overlap area to the total.
                if x_overlap > 0 and y_overlap > 0:
                    total_overlap_area += (x_overlap * y_overlap)

        # Normalize the overlap penalty.
        # This is the ratio of the total overlapping area to the sum of all individual box areas.
        normalized_overlap_penalty = 0
        if total_box_area > 0:
            # Cap the penalty at 1.0 to prevent scores from becoming excessively negative
            # if there's extreme overlap (e.g., many small boxes inside one large box).
            normalized_overlap_penalty = min(1.0, total_overlap_area / total_box_area)

        # --- Combine Scores ---
        # The final score is a weighted combination of alignment and overlap.
        # Alignment contributes positively, overlap contributes negatively.
        # The weights (0.8 and 0.2) can be adjusted to emphasize one aspect over the other.
        # For example, if alignment is more crucial, increase 0.8 and decrease 0.2.
        final_score = (normalized_alignment_score * 0.8 - normalized_overlap_penalty * 0.2) * 100

        # Ensure the final score is within the 0-100 range.
        final_score = max(0, min(100, final_score))

        # Update the UI with the calculated score and show a message box.
        self.current_organization_score.set(f"{final_score:.2f}")
        messagebox.showinfo("Organization Score", f"The calculated organization score is: {final_score:.2f}")


    def get_settings(self):
        """
        Retrieves all current parameter values and returns them as a dictionary.
        This dictionary can be used for saving the application's state.
        """
        return {
            'blur_value': self.blur_value.get(),
            'min_area': self.min_area.get(),
            'max_area': self.max_area.get(),
            'min_width': self.min_width.get(),
            'max_width': self.max_width.get(),
            'min_height': self.min_height.get(),
            'max_height': self.max_height.get(),
            'min_aspect_ratio': self.min_aspect_ratio.get(),
            'max_aspect_ratio': self.max_aspect_ratio.get(),
            'min_solidity': self.min_solidity.get(),
            'canny_low': self.canny_low.get(),
            'canny_high': self.canny_high.get(),
            'edge_dilation': self.edge_dilation.get(),
            'edge_erosion': self.edge_erosion.get(),
            'kernel_size': self.kernel_size.get(),
            'enable_merge': self.enable_merge.get(),
            'height_tolerance': self.height_tolerance.get(),
            'vertical_tolerance': self.vertical_tolerance.get(),
            'horizontal_gap_ratio': self.horizontal_gap_ratio.get(),
            'enable_vertical_merge': self.enable_vertical_merge.get(),
            'left_align_tolerance': self.left_align_tolerance.get(),
            'paragraph_height_tolerance': self.paragraph_height_tolerance.get(),
            'vertical_gap_ratio': self.vertical_gap_ratio.get(),
            # Alignment settings
            'enable_alignment_lines': self.enable_alignment_lines.get(),
            'align_left_tol': self.align_left_tol.get(),
            'align_right_tol': self.align_right_tol.get(),
            'align_top_tol': self.align_top_tol.get(),
            'align_bottom_tol': self.align_bottom_tol.get(),
            'align_center_x_tol': self.align_center_x_tol.get(),
            'align_center_y_tol': self.align_center_y_tol.get(),
        }

    def set_settings(self, settings):
        """
        Applies settings from a provided dictionary to the application's parameters.
        Used for loading a previously saved state.
        """
        try:
            self.blur_value.set(settings.get('blur_value', 5))
            self.min_area.set(settings.get('min_area', 500))
            self.max_area.set(settings.get('max_area', 50000))
            self.min_width.set(settings.get('min_width', 10))
            self.max_width.set(settings.get('max_width', 10000))
            self.min_height.set(settings.get('min_height', 10))
            self.max_height.set(settings.get('max_height', 10000))
            self.min_aspect_ratio.set(settings.get('min_aspect_ratio', 0.1))
            self.max_aspect_ratio.set(settings.get('max_aspect_ratio', 10.0))
            self.min_solidity.set(settings.get('min_solidity', 0.1))
            self.canny_low.set(settings.get('canny_low', 50))
            self.canny_high.set(settings.get('canny_high', 150))
            self.edge_dilation.set(settings.get('edge_dilation', 3))
            self.edge_erosion.set(settings.get('edge_erosion', 1))
            self.kernel_size.set(settings.get('kernel_size', 3))
            self.enable_merge.set(settings.get('enable_merge', True))
            self.height_tolerance.set(settings.get('height_tolerance', 0.3))
            self.vertical_tolerance.set(settings.get('vertical_tolerance', 0.5))
            self.horizontal_gap_ratio.set(settings.get('horizontal_gap_ratio', 1.0))
            self.enable_vertical_merge.set(settings.get('enable_vertical_merge', False))
            self.left_align_tolerance.set(settings.get('left_align_tolerance', 0.1))
            self.paragraph_height_tolerance.set(settings.get('paragraph_height_tolerance', 0.4))
            self.vertical_gap_ratio.set(settings.get('vertical_gap_ratio', 0.5))
            # Alignment settings
            self.enable_alignment_lines.set(settings.get('enable_alignment_lines', True))
            self.align_left_tol.set(settings.get('align_left_tol', 10))
            self.align_right_tol.set(settings.get('align_right_tol', 10))
            self.align_top_tol.set(settings.get('align_top_tol', 10))
            self.align_bottom_tol.set(settings.get('align_bottom_tol', 10))
            self.align_center_x_tol.set(settings.get('align_center_x_tol', 10))
            self.align_center_y_tol.set(settings.get('align_center_y_tol', 10))

        except Exception as e:
            messagebox.showerror("Error", f"Error applying settings: {str(e)}")

    def save_settings(self):
        """
        Opens a file dialog to save the current application settings to a JSON file.
        """
        file_path = filedialog.asksaveasfilename(
            title="Save Settings",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )

        if file_path:
            try:
                settings = self.get_settings()
                with open(file_path, 'w') as f:
                    json.dump(settings, f, indent=4)
                messagebox.showinfo("Success", "Settings saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Error saving settings: {str(e)}")

    def load_settings(self):
        """
        Opens a file dialog to load application settings from a JSON file.
        Applies the loaded settings and triggers image reprocessing if an image is loaded.
        """
        file_path = filedialog.askopenfilename(
            title="Load Settings",
            filetypes=[("JSON files", "*.json")]
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    settings = json.load(f)
                self.set_settings(settings)
                messagebox.showinfo("Success", "Settings loaded successfully!")
                # Trigger reprocessing if image is loaded
                if self.original_image is not None:
                    threading.Thread(target=self.process_image, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Error", f"Error loading settings: {str(e)}")

    def update_display(self):
        """
        Updates the image displayed on the canvas.
        Converts the processed OpenCV image to a PhotoImage and scales it for display.
        Configures canvas scroll region to match the original image size.
        """
        if self.processed_image is None:
            return

        # Convert BGR (OpenCV) to RGB (PIL) format
        rgb_image = cv2.cvtColor(self.processed_image, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_image = Image.fromarray(rgb_image)

        # Resize image for initial display if it's too large, maintaining aspect ratio.
        # The canvas scrollbars will allow viewing the full original-sized image.
        max_display_width = 800
        max_display_height = 600
        img_w, img_h = pil_image.size

        if img_w > max_display_width or img_h > max_display_height:
            ratio_w = max_display_width / img_w
            ratio_h = max_display_height / img_h
            ratio = min(ratio_w, ratio_h) # Use the smaller ratio to fit both dimensions
            new_size = (int(img_w * ratio), int(img_h * ratio))
            pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)

        # Convert PIL Image to Tkinter PhotoImage
        self.photo = ImageTk.PhotoImage(pil_image)

        # Update canvas content
        self.canvas.delete("all") # Clear previous drawings
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        # Set the scroll region of the canvas to the dimensions of the ORIGINAL image.
        # This ensures that even if the displayed image is scaled down, the scrollbars
        # will allow the user to scroll through the full original resolution area.
        if self.original_image is not None:
            self.canvas.config(scrollregion=(0, 0, self.original_image.shape[1], self.original_image.shape[0]))
        else:
            # Fallback if original_image is somehow not set (shouldn't happen after load)
            self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def on_parameter_change(self, *args):
        """
        Callback function triggered when any slider or checkbox parameter changes.
        Initiates image reprocessing in a separate thread.
        """
        # Reset score to N/A when parameters change, as the previous score is now invalid
        self.current_organization_score.set("N/A")
        if self.original_image is not None:
            # Use threading to prevent UI freezing during image processing
            threading.Thread(target=self.process_image, daemon=True).start()

def main():
    root = tk.Tk()
    app = ElementDetector(root)
    root.mainloop()

if __name__ == "__main__":
    main()
