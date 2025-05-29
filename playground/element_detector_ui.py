import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
import json
import cv2
import numpy as np
from element_detector_processor import ImageProcessor

# Helper class for a scrollable frame
class VerticalScrolledFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that can be used to contain other widgets."""
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


class ElementDetectorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Edge Detection with Text Line Merging and Alignment Lines")
        self.root.geometry("1600x900") # Increased width for new panel

        # Initialize image processor
        self.processor = ImageProcessor()

        # Initialize variables
        self.original_image = None
        self.processed_image = None
        self.display_image = None
        self.photo = None
        self.boxes = [] # Store detected boxes for alignment drawing and scoring

        # Organization Score variables
        self.organization_score_label = None # To display the score
        self.current_organization_score = tk.StringVar(value="N/A")

        self.setup_ui()

    def setup_ui(self):
        # Main frame to hold all other frames
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Left Control Panel ---
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

        # --- Tab 1: Basic Parameters ---
        basic_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(basic_frame_tab, text="Basic Params")
        basic_frame = basic_frame_tab.interior # Get the interior frame to place widgets

        self.blur_value = tk.IntVar(value=self.processor.blur_value)
        ttk.Label(basic_frame, text="Blur Kernel Size:").pack(pady=(5,0))
        blur_scale = ttk.Scale(basic_frame, from_=1, to=21, orient=tk.HORIZONTAL,
                               variable=self.blur_value, command=self.on_parameter_change)
        blur_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.blur_value).pack()

        self.min_area = tk.IntVar(value=self.processor.min_area)
        ttk.Label(basic_frame, text="Min Area:").pack(pady=(5,0))
        min_area_scale = ttk.Scale(basic_frame, from_=10, to=5000, orient=tk.HORIZONTAL,
                                   variable=self.min_area, command=self.on_parameter_change)
        min_area_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.min_area).pack()

        self.max_area = tk.IntVar(value=self.processor.max_area)
        ttk.Label(basic_frame, text="Max Area:").pack(pady=(5,0))
        max_area_scale = ttk.Scale(basic_frame, from_=1000, to=100000, orient=tk.HORIZONTAL,
                                   variable=self.max_area, command=self.on_parameter_change)
        max_area_scale.pack(fill=tk.X)
        ttk.Label(basic_frame, textvariable=self.max_area).pack()

        # --- Tab 2: Edge Detection Parameters ---
        edge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(edge_frame_tab, text="Edge Detection")
        edge_frame = edge_frame_tab.interior

        self.canny_low = tk.IntVar(value=self.processor.canny_low)
        ttk.Label(edge_frame, text="Canny Low Threshold:").pack(pady=(5,0))
        canny_low_scale = ttk.Scale(edge_frame, from_=10, to=200, orient=tk.HORIZONTAL,
                                     variable=self.canny_low, command=self.on_parameter_change)
        canny_low_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.canny_low).pack()

        self.canny_high = tk.IntVar(value=self.processor.canny_high)
        ttk.Label(edge_frame, text="Canny High Threshold:").pack(pady=(5,0))
        canny_high_scale = ttk.Scale(edge_frame, from_=50, to=400, orient=tk.HORIZONTAL,
                                      variable=self.canny_high, command=self.on_parameter_change)
        canny_high_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.canny_high).pack()

        self.edge_dilation = tk.IntVar(value=self.processor.edge_dilation)
        ttk.Label(edge_frame, text="Edge Dilation:").pack(pady=(5,0))
        edge_dil_scale = ttk.Scale(edge_frame, from_=0, to=10, orient=tk.HORIZONTAL,
                                    variable=self.edge_dilation, command=self.on_parameter_change)
        edge_dil_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.edge_dilation).pack()

        self.edge_erosion = tk.IntVar(value=self.processor.edge_erosion)
        ttk.Label(edge_frame, text="Edge Erosion:").pack(pady=(5,0))
        edge_ero_scale = ttk.Scale(edge_frame, from_=0, to=10, orient=tk.HORIZONTAL,
                                    variable=self.edge_erosion, command=self.on_parameter_change)
        edge_ero_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.edge_erosion).pack()

        self.kernel_size = tk.IntVar(value=self.processor.kernel_size)
        ttk.Label(edge_frame, text="Morphology Kernel Size:").pack(pady=(5,0))
        kernel_scale = ttk.Scale(edge_frame, from_=1, to=15, orient=tk.HORIZONTAL,
                                 variable=self.kernel_size, command=self.on_parameter_change)
        kernel_scale.pack(fill=tk.X)
        ttk.Label(edge_frame, textvariable=self.kernel_size).pack()

        # --- Tab 3: Text Line Merging Parameters ---
        merge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(merge_frame_tab, text="Text Merging")
        merge_frame = merge_frame_tab.interior

        self.enable_merge = tk.BooleanVar(value=self.processor.enable_merge)
        ttk.Checkbutton(merge_frame, text="Enable Merging", variable=self.enable_merge,
                        command=self.on_parameter_change).pack(pady=(5,0))

        self.height_tolerance = tk.DoubleVar(value=self.processor.height_tolerance)
        ttk.Label(merge_frame, text="Height Tolerance (0-1):").pack(pady=(5,0))
        height_tol_scale = ttk.Scale(merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                     variable=self.height_tolerance, command=self.on_parameter_change)
        height_tol_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.height_tolerance).pack()

        self.vertical_tolerance = tk.DoubleVar(value=self.processor.vertical_tolerance)
        ttk.Label(merge_frame, text="Vertical Alignment Tolerance (0-1):").pack(pady=(5,0))
        vert_tol_scale = ttk.Scale(merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                   variable=self.vertical_tolerance, command=self.on_parameter_change)
        vert_tol_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.vertical_tolerance).pack()

        self.horizontal_gap_ratio = tk.DoubleVar(value=self.processor.horizontal_gap_ratio)
        ttk.Label(merge_frame, text="Horizontal Gap Ratio (relative to height):").pack(pady=(5,0))
        gap_scale = ttk.Scale(merge_frame, from_=0.1, to=5.0, orient=tk.HORIZONTAL,
                              variable=self.horizontal_gap_ratio, command=self.on_parameter_change)
        gap_scale.pack(fill=tk.X)
        ttk.Label(merge_frame, textvariable=self.horizontal_gap_ratio).pack()

        # --- Tab 4: Paragraph Merging Parameters (Vertical) ---
        vertical_merge_frame_tab = VerticalScrolledFrame(self.notebook)
        self.notebook.add(vertical_merge_frame_tab, text="Paragraph Merging")
        vertical_merge_frame = vertical_merge_frame_tab.interior

        self.enable_vertical_merge = tk.BooleanVar(value=self.processor.enable_vertical_merge)
        ttk.Checkbutton(vertical_merge_frame, text="Enable Vertical Merging", variable=self.enable_vertical_merge,
                        command=self.on_parameter_change).pack(pady=(5,0))

        self.left_align_tolerance = tk.DoubleVar(value=self.processor.left_align_tolerance)
        ttk.Label(vertical_merge_frame, text="Left Alignment Tolerance (relative to width):").pack(pady=(5,0))
        left_align_scale = ttk.Scale(vertical_merge_frame, from_=0.01, to=0.5, orient=tk.HORIZONTAL,
                                     variable=self.left_align_tolerance, command=self.on_parameter_change)
        left_align_scale.pack(fill=tk.X)
        ttk.Label(vertical_merge_frame, textvariable=self.left_align_tolerance).pack()

        self.paragraph_height_tolerance = tk.DoubleVar(value=self.processor.paragraph_height_tolerance)
        ttk.Label(vertical_merge_frame, text="Paragraph Height Tolerance (0-1):").pack(pady=(5,0))
        para_height_scale = ttk.Scale(vertical_merge_frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL,
                                      variable=self.paragraph_height_tolerance, command=self.on_parameter_change)
        para_height_scale.pack(fill=tk.X)
        ttk.Label(vertical_merge_frame, textvariable=self.paragraph_height_tolerance).pack()

        self.vertical_gap_ratio = tk.DoubleVar(value=self.processor.vertical_gap_ratio)
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
• Vertical Gap Ratio: Max vertical gap as multiple of box height"""

        explanation_label = ttk.Label(info_frame, text=explanation_text, wraplength=280, justify=tk.LEFT)
        explanation_label.pack()

        self.info_label = ttk.Label(info_frame, text="No image loaded", wraplength=200, font=('TkDefaultFont', 9, 'bold'))
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
        control_panel_right = ttk.Frame(main_frame, width=350) # Fixed width
        control_panel_right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        control_panel_right.pack_propagate(False)

        # Alignment settings are in a scrollable frame
        alignment_settings_frame_tab = VerticalScrolledFrame(control_panel_right)
        alignment_settings_frame_tab.pack(fill=tk.BOTH, expand=True)
        alignment_settings_frame = alignment_settings_frame_tab.interior

        ttk.Label(alignment_settings_frame, text="Alignment Line Settings").pack(pady=(5,0))
        self.enable_alignment_lines = tk.BooleanVar(value=self.processor.enable_alignment_lines)
        ttk.Checkbutton(alignment_settings_frame, text="Enable Alignment Lines", variable=self.enable_alignment_lines,
                        command=self.on_parameter_change).pack(pady=(5,0))

        self.align_left_tol = tk.IntVar(value=self.processor.align_left_tol)
        ttk.Label(alignment_settings_frame, text="Left Alignment Tolerance (px):").pack(pady=(5,0))
        align_left_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                     variable=self.align_left_tol, command=self.on_parameter_change)
        align_left_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_left_tol).pack()

        self.align_right_tol = tk.IntVar(value=self.processor.align_right_tol)
        ttk.Label(alignment_settings_frame, text="Right Alignment Tolerance (px):").pack(pady=(5,0))
        align_right_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                      variable=self.align_right_tol, command=self.on_parameter_change)
        align_right_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_right_tol).pack()

        self.align_top_tol = tk.IntVar(value=self.processor.align_top_tol)
        ttk.Label(alignment_settings_frame, text="Top Alignment Tolerance (px):").pack(pady=(5,0))
        align_top_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                    variable=self.align_top_tol, command=self.on_parameter_change)
        align_top_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_top_tol).pack()

        self.align_bottom_tol = tk.IntVar(value=self.processor.align_bottom_tol)
        ttk.Label(alignment_settings_frame, text="Bottom Alignment Tolerance (px):").pack(pady=(5,0))
        align_bottom_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                       variable=self.align_bottom_tol, command=self.on_parameter_change)
        align_bottom_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_bottom_tol).pack()

        self.align_center_x_tol = tk.IntVar(value=self.processor.align_center_x_tol)
        ttk.Label(alignment_settings_frame, text="Center X Alignment Tolerance (px):").pack(pady=(5,0))
        align_center_x_scale = ttk.Scale(alignment_settings_frame, from_=0, to=50, orient=tk.HORIZONTAL,
                                        variable=self.align_center_x_tol, command=self.on_parameter_change)
        align_center_x_scale.pack(fill=tk.X)
        ttk.Label(alignment_settings_frame, textvariable=self.align_center_x_tol).pack()

        self.align_center_y_tol = tk.IntVar(value=self.processor.align_center_y_tol)
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
        self.organization_score_label = ttk.Label(score_frame, textvariable=self.current_organization_score, 
                                               font=('TkDefaultFont', 12, 'bold'))
        self.organization_score_label.pack(side=tk.LEFT, expand=True)

    def load_image(self):
        """Opens a file dialog to select an image and loads it."""
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
        """Processes the image using the ImageProcessor and updates the display."""
        if self.original_image is None:
            return

        # Update processor parameters from UI variables
        self.update_processor_parameters()

        # Process the image
        self.processed_image, self.boxes = self.processor.process_image(self.original_image)

        # Update the display on the main thread
        self.root.after(0, self.update_display)
        self.root.after(0, lambda: self.info_label.config(text=f"Detected {len(self.boxes)} elements"))

    def update_processor_parameters(self):
        """Updates all processor parameters from the UI variables."""
        self.processor.blur_value = self.blur_value.get()
        self.processor.min_area = self.min_area.get()
        self.processor.max_area = self.max_area.get()
        self.processor.canny_low = self.canny_low.get()
        self.processor.canny_high = self.canny_high.get()
        self.processor.edge_dilation = self.edge_dilation.get()
        self.processor.edge_erosion = self.edge_erosion.get()
        self.processor.kernel_size = self.kernel_size.get()
        self.processor.enable_merge = self.enable_merge.get()
        self.processor.height_tolerance = self.height_tolerance.get()
        self.processor.vertical_tolerance = self.vertical_tolerance.get()
        self.processor.horizontal_gap_ratio = self.horizontal_gap_ratio.get()
        self.processor.enable_vertical_merge = self.enable_vertical_merge.get()
        self.processor.left_align_tolerance = self.left_align_tolerance.get()
        self.processor.paragraph_height_tolerance = self.paragraph_height_tolerance.get()
        self.processor.vertical_gap_ratio = self.vertical_gap_ratio.get()
        self.processor.enable_alignment_lines = self.enable_alignment_lines.get()
        self.processor.align_left_tol = self.align_left_tol.get()
        self.processor.align_right_tol = self.align_right_tol.get()
        self.processor.align_top_tol = self.align_top_tol.get()
        self.processor.align_bottom_tol = self.align_bottom_tol.get()
        self.processor.align_center_x_tol = self.align_center_x_tol.get()
        self.processor.align_center_y_tol = self.align_center_y_tol.get()

    def calculate_organization_score(self):
        """Calculates and displays the organization score."""
        if not self.boxes:
            self.current_organization_score.set("N/A (No elements)")
            return

        score = self.processor.calculate_organization_score(self.boxes)
        self.current_organization_score.set(f"{score:.2f}")
        messagebox.showinfo("Organization Score", f"The calculated organization score is: {score:.2f}")

    def update_display(self):
        """Updates the image displayed on the canvas."""
        if self.processed_image is None:
            return

        # Convert BGR (OpenCV) to RGB (PIL) format
        rgb_image = cv2.cvtColor(self.processed_image, cv2.COLOR_BGR2RGB)

        # Convert to PIL Image
        pil_image = Image.fromarray(rgb_image)

        # Resize image for initial display if it's too large, maintaining aspect ratio
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

        # Set the scroll region of the canvas to the dimensions of the ORIGINAL image
        if self.original_image is not None:
            self.canvas.config(scrollregion=(0, 0, self.original_image.shape[1], self.original_image.shape[0]))
        else:
            # Fallback if original_image is somehow not set
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

    def get_settings(self):
        """Retrieves all current parameter values and returns them as a dictionary."""
        return {
            'blur_value': self.blur_value.get(),
            'min_area': self.min_area.get(),
            'max_area': self.max_area.get(),
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
            'enable_alignment_lines': self.enable_alignment_lines.get(),
            'align_left_tol': self.align_left_tol.get(),
            'align_right_tol': self.align_right_tol.get(),
            'align_top_tol': self.align_top_tol.get(),
            'align_bottom_tol': self.align_bottom_tol.get(),
            'align_center_x_tol': self.align_center_x_tol.get(),
            'align_center_y_tol': self.align_center_y_tol.get()
        }

    def set_settings(self, settings):
        """Applies settings from a provided dictionary to the application's parameters."""
        try:
            self.blur_value.set(settings.get('blur_value', 5))
            self.min_area.set(settings.get('min_area', 500))
            self.max_area.set(settings.get('max_area', 50000))
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
        """Opens a file dialog to save the current application settings to a JSON file."""
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
        """Opens a file dialog to load application settings from a JSON file."""
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

def main():
    root = tk.Tk()
    app = ElementDetectorUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()