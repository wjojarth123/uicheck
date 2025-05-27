import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np
import os
import threading
from paddleocr import PaddleOCR

class OCREdgeDetectionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OCR Edge Detection Tool")
        self.root.geometry("1200x800")
          # Configuration
        self.OCR_CONFIDENCE_THRESHOLD = 0.85
        self.ocr = None
        self.current_image = None
        self.original_cv_image = None
        self.edges_image = None        
        self.cleaned_edges_image = None
        self.major_edges_image = None            
        self.minor_edges_image = None  # For showing removed small edges
        self.edge_overlay_image = None  # For overlay visualization
        self.straight_edges_image = None  # For straight lines using Hough transform
        self.contours_image = None  # For contour detection on major edges
        self.cleaned_contours_image = None  # For contour detection on cleaned edges
        self.merged_view_image = None  # For merged view of minor element boxes + rectangular major contours
        self.ocr_results = None
        
        self.setup_ui()
        self.initialize_ocr()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Control panel
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # File selection
        ttk.Button(control_frame, text="Load Image", 
                  command=self.load_image).pack(side=tk.LEFT, padx=(0, 10))
        
        # Confidence threshold
        ttk.Label(control_frame, text="Confidence Threshold:").pack(side=tk.LEFT, padx=(0, 5))
        self.threshold_var = tk.DoubleVar(value=self.OCR_CONFIDENCE_THRESHOLD)
        threshold_scale = ttk.Scale(control_frame, from_=0.1, to=1.0, 
                                   variable=self.threshold_var, length=200)
        threshold_scale.pack(side=tk.LEFT, padx=(0, 10))
        
        self.threshold_label = ttk.Label(control_frame, text=f"{self.OCR_CONFIDENCE_THRESHOLD:.2f}")
        self.threshold_label.pack(side=tk.LEFT, padx=(0, 10))
        threshold_scale.configure(command=self.update_threshold_label)
        
        # Process button
        self.process_btn = ttk.Button(control_frame, text="Process OCR", 
                                     command=self.process_image, state=tk.DISABLED)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Export buttons
        self.export_btn = ttk.Button(control_frame, text="Export Results", 
                                    command=self.export_results, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT)
        
        # Morphology controls
        morph_frame = ttk.LabelFrame(control_frame, text="Edge Morphology")
        morph_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        # Erosion control
        ttk.Label(morph_frame, text="Erosion:").grid(row=0, column=0, padx=5)
        self.erosion_var = tk.IntVar(value=0)
        erosion_scale = ttk.Scale(morph_frame, from_=0, to=10, 
                                 variable=self.erosion_var, length=100)
        erosion_scale.grid(row=0, column=1, padx=5)
        self.erosion_label = ttk.Label(morph_frame, text="0")
        self.erosion_label.grid(row=0, column=2, padx=(0, 5))
        erosion_scale.configure(command=lambda v: self.update_morph_label(v, self.erosion_label, "erosion"))        # Dilation control
        ttk.Label(morph_frame, text="Dilation:").grid(row=1, column=0, padx=5)
        self.dilation_var = tk.IntVar(value=5)
        dilation_scale = ttk.Scale(morph_frame, from_=0, to=10, 
                                  variable=self.dilation_var, length=100)
        dilation_scale.grid(row=1, column=1, padx=5)
        self.dilation_label = ttk.Label(morph_frame, text="5")
        self.dilation_label.grid(row=1, column=2, padx=(0, 5))
        dilation_scale.configure(command=lambda v: self.update_morph_label(v, self.dilation_label, "dilation"))
          # Proximity threshold control
        ttk.Label(morph_frame, text="Proximity:").grid(row=2, column=0, padx=5)
        self.proximity_var = tk.IntVar(value=8)
        proximity_scale = ttk.Scale(morph_frame, from_=0, to=50, 
                                   variable=self.proximity_var, length=100)
        proximity_scale.grid(row=2, column=1, padx=5)
        self.proximity_label = ttk.Label(morph_frame, text="8")
        self.proximity_label.grid(row=2, column=2, padx=(0, 5))
        proximity_scale.configure(command=lambda v: self.update_morph_label(v, self.proximity_label, "proximity"))
        
        # Apply morphology button
        self.apply_morph_btn = ttk.Button(morph_frame, text="Apply", 
                                        command=self.apply_morphology, state=tk.DISABLED)
        self.apply_morph_btn.grid(row=0, column=3, rowspan=3, padx=5, pady=2)
        
        # Progress bar
        self.progress = ttk.Progressbar(control_frame, mode='indeterminate')
        self.progress.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Images
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Image display tabs
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Original image tab
        self.original_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.original_frame, text="Original")
        
        self.original_canvas = tk.Canvas(self.original_frame, bg='white')
        self.original_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Edges tab
        self.edges_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.edges_frame, text="Original Edges")
        
        self.edges_canvas = tk.Canvas(self.edges_frame, bg='white')
        self.edges_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Cleaned edges tab
        self.cleaned_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.cleaned_frame, text="Cleaned Edges")
        
        self.cleaned_canvas = tk.Canvas(self.cleaned_frame, bg='white')
        self.cleaned_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Major edges tab (edges without small components)
        self.major_edges_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.major_edges_frame, text="Major Edges")
        
        self.major_edges_canvas = tk.Canvas(self.major_edges_frame, bg='white')
        self.major_edges_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Minor edges tab (only small components)
        self.minor_edges_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.minor_edges_frame, text="Minor Edges")
        
        self.minor_edges_canvas = tk.Canvas(self.minor_edges_frame, bg='white')
        self.minor_edges_canvas.pack(fill=tk.BOTH, expand=True)        # Overlay tab (showing both major and minor edges)
        self.overlay_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.overlay_frame, text="Edges Overlay")
          # Straight Major Edges tab (using Hough Line Transform)
        self.straight_edges_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.straight_edges_frame, text="Straight Major Edges")
        
        self.straight_edges_canvas = tk.Canvas(self.straight_edges_frame, bg='white')
        self.straight_edges_canvas.pack(fill=tk.BOTH, expand=True)        # Major Edges Contour Detection tab
        self.contours_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.contours_frame, text="Major Edge Contours")
        
        # Create a container for the canvas and controls
        contour_container = ttk.Frame(self.contours_frame)
        contour_container.pack(fill=tk.BOTH, expand=True)
        
        # Cleaned Edges Contour Detection tab
        self.cleaned_contours_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.cleaned_contours_frame, text="Cleaned Edge Contours")
        
        # Create a container for the canvas and controls
        cleaned_contour_container = ttk.Frame(self.cleaned_contours_frame)
        cleaned_contour_container.pack(fill=tk.BOTH, expand=True)
        
        # Add contour controls
        contour_controls_frame = ttk.Frame(contour_container)
        contour_controls_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        # Min area control
        ttk.Label(contour_controls_frame, text="Min Area:").pack(side=tk.LEFT, padx=(0, 5))
        self.min_contour_area_var = tk.IntVar(value=500)
        min_area_scale = ttk.Scale(contour_controls_frame, from_=100, to=5000, 
                                  variable=self.min_contour_area_var, length=100)
        min_area_scale.pack(side=tk.LEFT, padx=5)
        self.min_contour_label = ttk.Label(contour_controls_frame, text="500")
        self.min_contour_label.pack(side=tk.LEFT, padx=(0, 15))
        min_area_scale.configure(command=lambda v: self.update_contour_label(v, self.min_contour_label, "min_area"))
        
        # Max area control
        ttk.Label(contour_controls_frame, text="Max Area:").pack(side=tk.LEFT, padx=(0, 5))
        self.max_contour_area_var = tk.IntVar(value=50000)
        max_area_scale = ttk.Scale(contour_controls_frame, from_=5000, to=500000, 
                                  variable=self.max_contour_area_var, length=100)
        max_area_scale.pack(side=tk.LEFT, padx=5)
        self.max_contour_label = ttk.Label(contour_controls_frame, text="50000")
        self.max_contour_label.pack(side=tk.LEFT, padx=(0, 15))
        max_area_scale.configure(command=lambda v: self.update_contour_label(v, self.max_contour_label, "max_area"))
        
        # Apply contour detection button
        self.apply_contours_btn = ttk.Button(contour_controls_frame, text="Detect Contours", 
                                           command=self.apply_contour_detection, state=tk.DISABLED)
        self.apply_contours_btn.pack(side=tk.LEFT, padx=10)
          # Canvas for displaying contours
        self.contours_canvas = tk.Canvas(contour_container, bg='white')
        self.contours_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Add contour controls for cleaned edges
        cleaned_contour_controls_frame = ttk.Frame(cleaned_contour_container)
        cleaned_contour_controls_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        # Min area control for cleaned edges
        ttk.Label(cleaned_contour_controls_frame, text="Min Area:").pack(side=tk.LEFT, padx=(0, 5))
        self.cleaned_min_contour_area_var = tk.IntVar(value=200)
        cleaned_min_area_scale = ttk.Scale(cleaned_contour_controls_frame, from_=50, to=2000, 
                                  variable=self.cleaned_min_contour_area_var, length=100)
        cleaned_min_area_scale.pack(side=tk.LEFT, padx=5)
        self.cleaned_min_contour_label = ttk.Label(cleaned_contour_controls_frame, text="200")
        self.cleaned_min_contour_label.pack(side=tk.LEFT, padx=(0, 15))
        cleaned_min_area_scale.configure(command=lambda v: self.update_contour_label(v, self.cleaned_min_contour_label, "cleaned_min_area"))
        
        # Max area control for cleaned edges
        ttk.Label(cleaned_contour_controls_frame, text="Max Area:").pack(side=tk.LEFT, padx=(0, 5))
        self.cleaned_max_contour_area_var = tk.IntVar(value=30000)
        cleaned_max_area_scale = ttk.Scale(cleaned_contour_controls_frame, from_=2000, to=300000, 
                                  variable=self.cleaned_max_contour_area_var, length=100)
        cleaned_max_area_scale.pack(side=tk.LEFT, padx=5)
        self.cleaned_max_contour_label = ttk.Label(cleaned_contour_controls_frame, text="30000")
        self.cleaned_max_contour_label.pack(side=tk.LEFT, padx=(0, 15))
        cleaned_max_area_scale.configure(command=lambda v: self.update_contour_label(v, self.cleaned_max_contour_label, "cleaned_max_area"))
        
        # Apply contour detection button for cleaned edges
        self.apply_cleaned_contours_btn = ttk.Button(cleaned_contour_controls_frame, text="Detect Contours", 
                                           command=self.apply_cleaned_contour_detection, state=tk.DISABLED)
        self.apply_cleaned_contours_btn.pack(side=tk.LEFT, padx=10)
        
        # Canvas for displaying cleaned edge contours
        self.cleaned_contours_canvas = tk.Canvas(cleaned_contour_container, bg='white')
        self.cleaned_contours_canvas.pack(fill=tk.BOTH, expand=True)
        
        overlay_container = ttk.Frame(self.overlay_frame)
        overlay_container.pack(fill=tk.BOTH, expand=True)
        
        # Add a legend for the overlay colors
        legend_frame = ttk.Frame(overlay_container)
        legend_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        ttk.Label(legend_frame, text="Edge Type Legend:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        # White for major edges
        white_label_frame = ttk.Frame(legend_frame, width=15, height=15, style='WhiteFrame.TFrame')
        white_label_frame.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Style().configure('WhiteFrame.TFrame', background='white')
        ttk.Label(legend_frame, text="Major Edges").pack(side=tk.LEFT, padx=(0, 15))
        
        # Yellow for connected minor edges
        yellow_label_frame = ttk.Frame(legend_frame, width=15, height=15, style='YellowFrame.TFrame')
        yellow_label_frame.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Style().configure('YellowFrame.TFrame', background='cyan')
        ttk.Label(legend_frame, text="Connected Minor Edges").pack(side=tk.LEFT, padx=(0, 15))
        
        # Red for isolated minor edges
        red_label_frame = ttk.Frame(legend_frame, width=15, height=15, style='RedFrame.TFrame')
        red_label_frame.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Style().configure('RedFrame.TFrame', background='red')
        ttk.Label(legend_frame, text="Isolated Minor Edges").pack(side=tk.LEFT)
        
        self.overlay_canvas = tk.Canvas(overlay_container, bg='white')
        self.overlay_canvas.pack(fill=tk.BOTH, expand=True)
          # Bounding boxes tab
        self.bbox_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.bbox_frame, text="With Bounding Boxes")
        
        self.bbox_canvas = tk.Canvas(self.bbox_frame, bg='white')
        self.bbox_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Merged View tab (minor boxes + rectangular major contours)
        self.merged_view_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.merged_view_frame, text="Merged View")
        
        # Create a container for the canvas and controls
        merged_view_container = ttk.Frame(self.merged_view_frame)
        merged_view_container.pack(fill=tk.BOTH, expand=True)
        
        # Add controls for the merged view
        merged_view_controls_frame = ttk.Frame(merged_view_container)
        merged_view_controls_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        # Apply merged view generation button
        self.apply_merged_view_btn = ttk.Button(merged_view_controls_frame, text="Generate Merged View", 
                                           command=self.generate_merged_view, state=tk.DISABLED)
        self.apply_merged_view_btn.pack(side=tk.LEFT, padx=10)
        
        # Canvas for displaying merged view
        self.merged_view_canvas = tk.Canvas(merged_view_container, bg='white')
        self.merged_view_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Right panel - Results
        right_frame = ttk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.configure(width=300)
        
        # Results text area
        ttk.Label(right_frame, text="OCR Results", font=('Arial', 12, 'bold')).pack(pady=(0, 5))
        
        self.results_text = scrolledtext.ScrolledText(right_frame, width=40, height=30)
        self.results_text.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def initialize_ocr(self):
        """Initialize PaddleOCR in a separate thread"""
        def init_ocr():
            try:
                self.status_var.set("Initializing OCR...")
                self.progress.start()
                self.ocr = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False
                )
                self.status_var.set("OCR initialized successfully")
                self.progress.stop()
            except Exception as e:
                self.status_var.set(f"OCR initialization failed: {str(e)}")
                self.progress.stop()
                messagebox.showerror("Error", f"Failed to initialize OCR: {str(e)}")
        
        threading.Thread(target=init_ocr, daemon=True).start()
    
    def update_threshold_label(self, value):
        self.threshold_label.config(text=f"{float(value):.2f}")
        self.OCR_CONFIDENCE_THRESHOLD = float(value)
    
    def load_image(self):
        """Load an image file"""
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            try:
                # Load image with OpenCV
                self.original_cv_image = cv2.imread(file_path)
                if self.original_cv_image is None:
                    raise ValueError("Could not load image")
                
                # Convert for PIL display
                rgb_image = cv2.cvtColor(self.original_cv_image, cv2.COLOR_BGR2RGB)
                self.current_image = Image.fromarray(rgb_image)
                
                # Display original image
                self.display_image(self.current_image, self.original_canvas)
                  # Enable process button
                self.process_btn.config(state=tk.NORMAL)
                
                # Disable morphology button until processing is done
                self.apply_morph_btn.config(state=tk.DISABLED)
                
                self.status_var.set(f"Image loaded: {os.path.basename(file_path)} "
                                  f"({self.original_cv_image.shape[1]}x{self.original_cv_image.shape[0]})")                # Clear previous results
                self.results_text.delete(1.0, tk.END)                    
                self.clear_canvases([self.edges_canvas, self.cleaned_canvas, self.major_edges_canvas, 
                                    self.minor_edges_canvas, self.overlay_canvas, self.bbox_canvas,
                                    self.straight_edges_canvas, self.contours_canvas, self.cleaned_contours_canvas,
                                    self.merged_view_canvas])
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image: {str(e)}")
    
    def display_image(self, pil_image, canvas):
        """Display PIL image on canvas with scaling"""
        canvas.delete("all")
        
        # Get canvas size
        canvas.update()
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet
            canvas.after(100, lambda: self.display_image(pil_image, canvas))
            return
        
        # Calculate scaling to fit canvas
        img_width, img_height = pil_image.size
        scale_x = canvas_width / img_width
        scale_y = canvas_height / img_height
        scale = min(scale_x, scale_y, 1.0)  # Don't upscale
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        # Resize image
        resized_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to PhotoImage and display
        photo = ImageTk.PhotoImage(resized_image)
        canvas.create_image(canvas_width//2, canvas_height//2, image=photo)
        canvas.image = photo  # Keep a reference
    
    def clear_canvases(self, canvases):
        """Clear specified canvases"""
        for canvas in canvases:
            canvas.delete("all")
    
    def process_image(self):
        """Process the image with OCR and edge detection"""
        if self.original_cv_image is None or self.ocr is None:
            messagebox.showwarning("Warning", "Please load an image and wait for OCR initialization")
            return
        
        def process():
            try:
                self.status_var.set("Processing image...")
                self.progress.start()
                self.process_btn.config(state=tk.DISABLED)
                
                # Convert to grayscale for edge detection
                gray = cv2.cvtColor(self.original_cv_image, cv2.COLOR_BGR2GRAY)
                
                # Perform Canny edge detection
                edges = cv2.Canny(gray, 20, 100)
                self.edges_image = edges.copy()                # Run OCR
                # Convert BGR to RGB for PaddleOCR
                rgb_for_ocr = cv2.cvtColor(self.original_cv_image, cv2.COLOR_BGR2RGB)
                result = self.ocr.predict(rgb_for_ocr)
                
                # Create mask to remove text areas
                mask = np.zeros_like(edges)
                
                # Process OCR results
                results_text = "--- OCR Results ---\n\n"
                text_boxes_found = 0
                bounding_boxes = []
                
                if result and result[0]:
                    for poly, text, score in zip(result[0]['rec_polys'], result[0]['rec_texts'], result[0]['rec_scores']):
                          if score > self.OCR_CONFIDENCE_THRESHOLD:
                            text_boxes_found += 1
                            results_text += f"Text: '{text}'\n"
                            results_text += f"Score: {score:.3f}\n"
                            results_text += f"Bounding box: {poly}\n\n"
                            
                            # Convert poly to numpy array
                            poly_np = np.array(poly)
                            x_coords = poly_np[:, 0]
                            y_coords = poly_np[:, 1]
                            
                            x_min = int(np.min(x_coords))
                            y_min = int(np.min(y_coords))
                            x_max = int(np.max(x_coords))
                            y_max = int(np.max(y_coords))
                            
                            # Store for visualization
                            bounding_boxes.append((x_min, y_min, x_max, y_max, text, score))
                            
                            # Expand bounding box by 4px margin
                            margin = 4
                            x_min_margin = max(0, x_min - margin)
                            y_min_margin = max(0, y_min - margin)
                            x_max_margin = min(self.original_cv_image.shape[1], x_max + margin)
                            y_max_margin = min(self.original_cv_image.shape[0], y_max + margin)
                            
                            # Fill mask
                            cv2.rectangle(mask, (x_min_margin, y_min_margin), 
                                        (x_max_margin, y_max_margin), 255, -1)
                
                results_text += f"Total high-confidence text boxes found: {text_boxes_found}\n"
                  # Apply mask to edges
                inverted_mask = cv2.bitwise_not(mask)
                edges_without_text = cv2.bitwise_and(edges, inverted_mask)
                self.cleaned_edges_image = edges_without_text.copy()
                
                # Run contour detection on cleaned edges
                self.cleaned_contours_image = self.detect_contours(
                    self.cleaned_edges_image,
                    min_contour_area=self.cleaned_min_contour_area_var.get(), 
                    max_contour_area=self.cleaned_max_contour_area_var.get()
                )
                
                # Create image with only major edges (remove small isolated components)
                proximity_value = self.proximity_var.get() if hasattr(self, 'proximity_var') else 20
                self.major_edges_image = self.remove_small_edges(edges_without_text, min_size=100, proximity_threshold=proximity_value)
                  # Create minor edges visualization (edges that were removed)
                self.minor_edges_image = cv2.subtract(edges_without_text, self.major_edges_image)
                
                # Create overlay image showing edge types with different colors
                self.edge_overlay_image = np.zeros((edges.shape[0], edges.shape[1], 3), dtype=np.uint8)
                
                # Set major edges to white
                self.edge_overlay_image[self.major_edges_image > 0] = [255, 255, 255]
                
                # Identify isolated vs. connected minor edges
                connected_minor_edges, isolated_minor_edges = self.classify_minor_edges(
                    self.minor_edges_image, self.major_edges_image, proximity_value
                )
                
                # Set isolated minor edges to red
                self.edge_overlay_image[isolated_minor_edges > 0] = [0, 0, 255]
                
                # Set connected minor edges to yellow (these are close to major edges)
                self.edge_overlay_image[connected_minor_edges > 0] = [0, 255, 255]
                  # Generate straight edges using Hough Line Transform on major edges
                self.straight_edges_image = self.apply_hough_transform(
                    self.major_edges_image, 
                    threshold=50, 
                    min_line_length=50, 
                    max_line_gap=5
                )
                  # Detect contours on the major edges
                self.contours_image = self.detect_contours(
                    self.major_edges_image,
                    min_contour_area=500, 
                    max_contour_area=100000
                )
                
                # Update UI in main thread
                self.root.after(0, lambda: self.update_results(results_text, bounding_boxes))
                
            except Exception as e:
                error_msg = str(e)  # Capture the error message first
                self.root.after(0, lambda: self.handle_processing_error(error_msg))
        
        threading.Thread(target=process, daemon=True).start()
    
    def update_results(self, results_text, bounding_boxes):
        """Update UI with processing results"""
        try:
            # Update results text
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, results_text)
              # Display edge images
            if self.edges_image is not None:
                edges_pil = Image.fromarray(self.edges_image)
                self.display_image(edges_pil, self.edges_canvas)
            
            if self.cleaned_edges_image is not None:
                cleaned_pil = Image.fromarray(self.cleaned_edges_image)
                self.display_image(cleaned_pil, self.cleaned_canvas)
            if self.major_edges_image is not None:
                major_edges_pil = Image.fromarray(self.major_edges_image)
                self.display_image(major_edges_pil, self.major_edges_canvas)
            
            if self.minor_edges_image is not None:
                minor_edges_pil = Image.fromarray(self.minor_edges_image)
                self.display_image(minor_edges_pil, self.minor_edges_canvas)
            
            if self.edge_overlay_image is not None:
                overlay_pil = Image.fromarray(self.edge_overlay_image)
                self.display_image(overlay_pil, self.overlay_canvas)
            
            # Create and display image with bounding boxes
            if bounding_boxes and self.current_image:
                bbox_image = self.current_image.copy()
                draw = ImageDraw.Draw(bbox_image)
                
                for x_min, y_min, x_max, y_max, text, score in bounding_boxes:
                    # Draw rectangle
                    draw.rectangle([x_min, y_min, x_max, y_max], outline='red', width=2)
                    
                    # Draw text label
                    label = f"{text[:20]}... ({score:.2f})" if len(text) > 20 else f"{text} ({score:.2f})"
                    draw.text((x_min, y_min - 20), label, fill='red')
                
                self.display_image(bbox_image, self.bbox_canvas)            # Enable export, morphology and contour buttons            self.export_btn.config(state=tk.NORMAL)            self.process_btn.config(state=tk.NORMAL)
            self.apply_morph_btn.config(state=tk.NORMAL)
            self.apply_contours_btn.config(state=tk.NORMAL)
            self.apply_cleaned_contours_btn.config(state=tk.NORMAL)
            self.apply_merged_view_btn.config(state=tk.NORMAL)
            self.progress.stop()
            self.status_var.set("Processing completed successfully")
            
        except Exception as e:
            self.handle_processing_error(str(e))
    
    def handle_processing_error(self, error_msg):
        """Handle processing errors"""
        self.progress.stop()
        self.process_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Processing failed: {error_msg}")
        messagebox.showerror("Error", f"Processing failed: {error_msg}")
    
    def export_results(self):
        """Export the processed images"""
        if self.cleaned_edges_image is None:
            messagebox.showwarning("Warning", "No processed images to export")
            return
        
        try:
            # Ask for directory
            directory = filedialog.askdirectory(title="Select Export Directory")
            if not directory:
                return
              # Export cleaned edges
            cleaned_path = os.path.join(directory, "edges_without_text_boxes.png")
            cv2.imwrite(cleaned_path, self.cleaned_edges_image)
              # Export major edges
            if self.major_edges_image is not None:
                major_edges_path = os.path.join(directory, "major_edges.png")
                cv2.imwrite(major_edges_path, self.major_edges_image)
            
            # Export minor edges
            if self.minor_edges_image is not None:
                minor_edges_path = os.path.join(directory, "minor_edges.png")
                cv2.imwrite(minor_edges_path, self.minor_edges_image)
              # Export edge overlay
            if self.edge_overlay_image is not None:
                overlay_path = os.path.join(directory, "edges_overlay.png")
                cv2.imwrite(overlay_path, self.edge_overlay_image)
              # Export straight major edges
            if self.straight_edges_image is not None:
                straight_edges_path = os.path.join(directory, "straight_major_edges.png")
                cv2.imwrite(straight_edges_path, self.straight_edges_image)            # Export major edge contour detection
            if self.contours_image is not None:
                contours_path = os.path.join(directory, "major_edge_contours.png")
                cv2.imwrite(contours_path, self.contours_image)
                  # Export cleaned edge contour detection
            if self.cleaned_contours_image is not None:
                cleaned_contours_path = os.path.join(directory, "cleaned_edge_contours.png")
                cv2.imwrite(cleaned_contours_path, self.cleaned_contours_image)
            
            # Export merged view
            if self.merged_view_image is not None:
                merged_view_path = os.path.join(directory, "merged_view.png")
                cv2.imwrite(merged_view_path, cv2.cvtColor(self.merged_view_image, cv2.COLOR_RGB2BGR))
            
            # Export original edges
            if self.edges_image is not None:
                original_edges_path = os.path.join(directory, "original_edges.png")
                cv2.imwrite(original_edges_path, self.edges_image)
            
            # Export OCR results as text
            results_path = os.path.join(directory, "ocr_results.txt")
            with open(results_path, 'w', encoding='utf-8') as f:
                f.write(self.results_text.get(1.0, tk.END))
            
            self.status_var.set(f"Results exported to {directory}")
            messagebox.showinfo("Success", f"Results exported successfully to:\n{directory}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
    def update_morph_label(self, value, label, type_name):
        """Update the label for morphology control values"""
        int_value = int(float(value))
        label.config(text=str(int_value))
        if type_name == "erosion":
            self.erosion_var.set(int_value)
        elif type_name == "dilation":
            self.dilation_var.set(int_value)
        elif type_name == "proximity":
            self.proximity_var.set(int_value)      
    def update_contour_label(self, value, label, type_name):
        """Update the label for contour control values"""
        int_value = int(float(value))
        label.config(text=str(int_value))
        if type_name == "min_area":
            self.min_contour_area_var.set(int_value)
        elif type_name == "max_area":
            self.max_contour_area_var.set(int_value)
        elif type_name == "cleaned_min_area":
            self.cleaned_min_contour_area_var.set(int_value)
        elif type_name == "cleaned_max_area":
            self.cleaned_max_contour_area_var.set(int_value)
    
    def apply_morphology(self):
        """Apply erosion and dilation to the cleaned edges image without re-running OCR"""
        if self.cleaned_edges_image is None:
            messagebox.showwarning("Warning", "No processed image to apply morphology")
            return
        
        try:
            # Get current morphology values
            erosion_value = self.erosion_var.get()
            dilation_value = self.dilation_var.get()
            proximity_value = self.proximity_var.get()
              # Start from the cleaned edges (without text)
            current_image = self.cleaned_edges_image.copy()
            
            # Apply erosion if needed
            if erosion_value > 0:
                kernel = np.ones((erosion_value, erosion_value), np.uint8)
                current_image = cv2.erode(current_image, kernel, iterations=1)
            
            # Apply dilation if needed
            if dilation_value > 0:
                kernel = np.ones((dilation_value, dilation_value), np.uint8)
                current_image = cv2.dilate(current_image, kernel, iterations=1)
                
            # Also update the cleaned contours based on the morphologically processed image
            self.cleaned_contours_image = self.detect_contours(
                current_image,
                min_contour_area=self.cleaned_min_contour_area_var.get(),
                max_contour_area=self.cleaned_max_contour_area_var.get()
            )
            
            # Apply small edge removal for the major edges tab, considering proximity
            self.major_edges_image = self.remove_small_edges(current_image, min_size=100, proximity_threshold=proximity_value)
            
            # Create minor edges visualization
            self.minor_edges_image = cv2.subtract(current_image, self.major_edges_image)
            
            # Create overlay image showing edge types with different colors
            self.edge_overlay_image = np.zeros((current_image.shape[0], current_image.shape[1], 3), dtype=np.uint8)
            
            # Set major edges to white
            self.edge_overlay_image[self.major_edges_image > 0] = [255, 255, 255]
            
            # Identify isolated vs. connected minor edges
            connected_minor_edges, isolated_minor_edges = self.classify_minor_edges(
                self.minor_edges_image, self.major_edges_image, proximity_value
            )
            
            # Set isolated minor edges to red
            self.edge_overlay_image[isolated_minor_edges > 0] = [0, 0, 255]
            
            # Set connected minor edges to yellow (these are close to major edges)
            self.edge_overlay_image[connected_minor_edges > 0] = [0, 255, 255]            # Generate straight edges using Hough Line Transform on major edges
            self.straight_edges_image = self.apply_hough_transform(
                self.major_edges_image, 
                threshold=50, 
                min_line_length=50, 
                max_line_gap=5
            )
            
            # Detect contours on the major edges
            self.contours_image = self.detect_contours(
                self.major_edges_image,
                min_contour_area=self.min_contour_area_var.get(), 
                max_contour_area=self.max_contour_area_var.get()
            )
            
            # Update displays
            self.update_edge_displays()
            self.status_var.set(f"Applied erosion={erosion_value}, dilation={dilation_value}, proximity={proximity_value}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply morphology: {str(e)}")
    def apply_contour_detection(self):
        """Apply contour detection on the major edges image"""
        if self.major_edges_image is None:
            messagebox.showwarning("Warning", "No processed image for contour detection")
            return
        
        try:
            # Get current contour parameter values
            min_area = self.min_contour_area_var.get()
            max_area = self.max_contour_area_var.get()
            
            # Detect contours
            self.contours_image = self.detect_contours(
                self.major_edges_image,
                min_contour_area=min_area,
                max_contour_area=max_area
            )
            
            # Update display
            contours_pil = Image.fromarray(self.contours_image)
            self.display_image(contours_pil, self.contours_canvas)
            
            self.status_var.set(f"Applied contour detection with min_area={min_area}, max_area={max_area}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply contour detection: {str(e)}")
    def apply_cleaned_contour_detection(self):
        """Apply contour detection on the cleaned edges image"""
        if self.cleaned_edges_image is None:
            messagebox.showwarning("Warning", "No processed image for contour detection")
            return
        
        try:
            # Get current contour parameter values
            min_area = self.cleaned_min_contour_area_var.get()
            max_area = self.cleaned_max_contour_area_var.get()
            
            # Detect contours
            self.cleaned_contours_image = self.detect_contours(
                self.cleaned_edges_image,
                min_contour_area=min_area,
                max_contour_area=max_area
            )
            
            # Update display
            cleaned_contours_pil = Image.fromarray(self.cleaned_contours_image)
            self.display_image(cleaned_contours_pil, self.cleaned_contours_canvas)
            
            self.status_var.set(f"Applied contour detection on cleaned edges with min_area={min_area}, max_area={max_area}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply contour detection: {str(e)}")
    def update_edge_displays(self):
        """Update all edge displays after morphology changes"""
        try:
            # Show major edges
            if self.major_edges_image is not None:
                major_edges_pil = Image.fromarray(self.major_edges_image)
                self.display_image(major_edges_pil, self.major_edges_canvas)
            
            # Show minor edges
            if self.minor_edges_image is not None:
                minor_edges_pil = Image.fromarray(self.minor_edges_image)
                self.display_image(minor_edges_pil, self.minor_edges_canvas)
            
            # Show overlay image
            if self.edge_overlay_image is not None:
                overlay_pil = Image.fromarray(self.edge_overlay_image)
                self.display_image(overlay_pil, self.overlay_canvas)            # Show straight edges
            if self.straight_edges_image is not None:
                straight_edges_pil = Image.fromarray(self.straight_edges_image)
                self.display_image(straight_edges_pil, self.straight_edges_canvas)
              # Show detected contours for major edges
            if self.contours_image is not None:
                contours_pil = Image.fromarray(self.contours_image)
                self.display_image(contours_pil, self.contours_canvas)
                
            # Show detected contours for cleaned edges
            if self.cleaned_contours_image is not None:
                cleaned_contours_pil = Image.fromarray(self.cleaned_contours_image)
                self.display_image(cleaned_contours_pil, self.cleaned_contours_canvas)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update displays: {str(e)}")
    def remove_small_edges(self, edge_image, min_size=100, proximity_threshold=20):
        """Remove edge components that can fit within a bounding box of min_size x min_size pixels
        and are considered isolated (not part of larger structures)"""
        # Find connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(edge_image, connectivity=8)
        
        # Create output images
        major_edges = np.zeros_like(edge_image)
        
        # If proximity_threshold is 0, use the original behavior - just filter by size
        if proximity_threshold == 0:
            # Original behavior - just filter by size
            for i in range(1, num_labels):
                width = stats[i, cv2.CC_STAT_WIDTH]
                height = stats[i, cv2.CC_STAT_HEIGHT]
                
                # Check if component is larger than min_size in either dimension
                if width > min_size or height > min_size:
                    # Keep this component as a major edge
                    component_mask = (labels == i).astype(np.uint8) * 255
                    major_edges = cv2.bitwise_or(major_edges, component_mask)
            
            return major_edges
        
        # Otherwise, use the pixel-based proximity filtering
        
        # First pass: Identify large components only
        for i in range(1, num_labels):
            width = stats[i, cv2.CC_STAT_WIDTH]
            height = stats[i, cv2.CC_STAT_HEIGHT]
            
            # Check if component is larger than min_size in either dimension
            if width > min_size or height > min_size:
                # Keep this component as a major edge
                component_mask = (labels == i).astype(np.uint8) * 255
                major_edges = cv2.bitwise_or(major_edges, component_mask)
        
        # Create a dilated version of major edges to check for proximity
        if proximity_threshold > 0:
            kernel = np.ones((proximity_threshold, proximity_threshold), np.uint8)
            dilated_major_edges = cv2.dilate(major_edges, kernel, iterations=1)
        else:
            dilated_major_edges = major_edges.copy()
        
        # Second pass: Check small components for proximity to major edges
        for i in range(1, num_labels):
            width = stats[i, cv2.CC_STAT_WIDTH]
            height = stats[i, cv2.CC_STAT_HEIGHT]
            
            # Skip components that are already marked as major
            if width > min_size or height > min_size:
                continue
                
            # Get mask for this small component
            component_mask = (labels == i).astype(np.uint8) * 255
            
            # Check if the component overlaps with the dilated major edges
            # Note: We're checking actual pixel proximity, not bounding box proximity
            overlap = cv2.bitwise_and(component_mask, dilated_major_edges)
            
            # If this component is close enough to major edge pixels, include it
            if np.any(overlap):
                major_edges = cv2.bitwise_or(major_edges, component_mask)
        
        return major_edges    
    def classify_minor_edges(self, minor_edges_image, major_edges_image, proximity_threshold):
        """Classify minor edges as either connected to major edges or isolated"""
        # Find connected components in minor edges
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(minor_edges_image, connectivity=8)
        
        # Create output images
        connected_minor_edges = np.zeros_like(minor_edges_image)
        isolated_minor_edges = np.zeros_like(minor_edges_image)
        
        # If proximity_threshold is 0, all minor edges are considered isolated
        if proximity_threshold == 0:
            isolated_minor_edges = minor_edges_image.copy()
            return connected_minor_edges, isolated_minor_edges
        
        # Dilate major edges to create a proximity zone
        # This creates a region around each major edge pixel where minor edges would be considered "connected"
        kernel = np.ones((proximity_threshold, proximity_threshold), np.uint8)
        major_edges_dilated = cv2.dilate(major_edges_image, kernel, iterations=1)
        
        # For each minor edge component
        for i in range(1, num_labels):
            # Get component mask
            component_mask = (labels == i).astype(np.uint8) * 255
            
            # Check if any pixels of this component are close to major edge pixels
            # by checking overlap with the dilated major edges
            overlap = cv2.bitwise_and(component_mask, major_edges_dilated)
            
            if np.any(overlap):
                # This component has pixels close to major edge pixels
                connected_minor_edges = cv2.bitwise_or(connected_minor_edges, component_mask)
            else:
                # This component is isolated from major edges
                isolated_minor_edges = cv2.bitwise_or(isolated_minor_edges, component_mask)
        
        return connected_minor_edges, isolated_minor_edges
    def apply_hough_transform(self, edge_image, threshold=50, min_line_length=50, max_line_gap=5):
        """Apply Hough Line Transform to detect straight lines in the edge image.
        
        Args:
            edge_image: Input edge image (single channel)
            threshold: Accumulator threshold parameter. Only lines with enough votes get returned
            min_line_length: Minimum line length. Line segments shorter than this are rejected
            max_line_gap: Maximum allowed gap between line segments to treat them as a single line
            
        Returns:
            Image with only straight edges detected by the Hough transform
        """
        # Create a blank image for drawing the lines
        straight_edges = np.zeros_like(edge_image)
        
        # Apply probabilistic Hough Line Transform
        lines = cv2.HoughLinesP(edge_image, 1, np.pi/180, threshold, None, min_line_length, max_line_gap)
        
        # Draw detected lines on the blank image
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(straight_edges, (x1, y1), (x2, y2), 255, 1)
        
        return straight_edges    
    def detect_contours(self, edge_image, min_contour_area=500, max_contour_area=100000):
        """Detect contours in an edge image.
        
        Args:
            edge_image: Input edge image (single channel)
            min_contour_area: Minimum area for a contour to be considered
            max_contour_area: Maximum area for a contour to be considered
            
        Returns:
            Image with detected contours drawn on it
        """
        # Create a copy of the original image for drawing
        contour_image = np.zeros((edge_image.shape[0], edge_image.shape[1], 3), dtype=np.uint8)
        
        # Find contours
        contours, hierarchy = cv2.findContours(edge_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Store filtered contours
        filtered_contours = []
        
        for i, contour in enumerate(contours):
            # Calculate contour area
            area = cv2.contourArea(contour)
            
            # Filter by area
            if min_contour_area < area < max_contour_area:
                filtered_contours.append(contour)
                
                # Generate a random color for this contour
                color = (
                    np.random.randint(100, 256),
                    np.random.randint(100, 256),
                    np.random.randint(100, 256)
                )
                
                # Draw the contour
                cv2.drawContours(contour_image, [contour], 0, color, 2)
                
                # Calculate and show contour center point
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    
                    # Draw center point
                    cv2.circle(contour_image, (cx, cy), 5, color, -1)
                    
                    # Get the bounding rectangle
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Show area and dimensions
                    info_text = f"A:{int(area)} {w}x{h}"
                    cv2.putText(
                        contour_image, 
                        info_text, 
                        (cx + 10, cy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, 
                        color, 
                        1
                    )
        
        self.status_var.set(f"Found {len(filtered_contours)} contours in the image")
        return contour_image
    def generate_merged_view(self):
        """Generate a merged view that combines bounding boxes around minor elements 
        with rectangle-simplified contours from major edges"""
        
        if self.minor_edges_image is None or self.major_edges_image is None:
            messagebox.showwarning("Warning", "No processed images for merged view")
            return
        
        try:
            # Create a new RGB image based on the original
            if self.current_image:
                self.merged_view_image = np.array(self.current_image)
            else:
                # Fallback to blank canvas with original dimensions
                h, w = self.major_edges_image.shape
                self.merged_view_image = np.ones((h, w, 3), dtype=np.uint8) * 255
            
            # 1. Find and draw bounding boxes around minor elements (both isolated and connected)
            minor_elements_combined = cv2.bitwise_or(
                self.minor_edges_image, 
                cv2.subtract(self.cleaned_edges_image, self.major_edges_image)
            )
            
            # Find contours for minor elements
            minor_contours, _ = cv2.findContours(minor_elements_combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Draw bounding boxes for minor elements in blue
            for minor_contour in minor_contours:
                area = cv2.contourArea(minor_contour)
                # Filter very small elements
                if area > 20:  # Minimum area threshold for minor elements
                    x, y, w, h = cv2.boundingRect(minor_contour)
                    cv2.rectangle(self.merged_view_image, (x, y), (x+w, y+h), (255, 0, 0), 1)
            
            # 2. Find and draw simplified rectangle contours from major edges
            major_contours, _ = cv2.findContours(self.major_edges_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Process major contours
            for major_contour in major_contours:
                area = cv2.contourArea(major_contour)
                
                # Filter by area - use same thresholds as contour detection
                if area > self.min_contour_area_var.get() and area < self.max_contour_area_var.get():
                    # Approximate contour to rectangle
                    perimeter = cv2.arcLength(major_contour, True)
                    epsilon = 0.02 * perimeter  # 2% approximation
                    approx = cv2.approxPolyDP(major_contour, epsilon, True)
                    
                    # Draw as green contour
                    cv2.drawContours(self.merged_view_image, [approx], 0, (0, 255, 0), 2)
                    
                    # Get the center of the contour for labeling
                    M = cv2.moments(approx)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        
                        # Show area as label
                        cv2.putText(
                            self.merged_view_image,
                            f"{int(area)}",
                            (cx, cy),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 100, 0),
                            1
                        )
            
            # Display the merged view
            merged_view_pil = Image.fromarray(self.merged_view_image)
            self.display_image(merged_view_pil, self.merged_view_canvas)
            
            self.status_var.set("Generated merged view with minor element boxes and major contour rectangles")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate merged view: {str(e)}")
def main():
    root = tk.Tk()
    app = OCREdgeDetectionGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()