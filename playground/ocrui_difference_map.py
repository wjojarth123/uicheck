from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk
import cv2
import numpy as np
from paddleocr import PaddleOCR

class OCRDifferenceMapGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OCR Difference Map Tool")
        self.root.geometry("1200x800")

        self.ocr = PaddleOCR()
        self.current_image = None
        self.difference_map = None
        self.contours_image = None
        self.ocr_results = None

        self.setup_ui()

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Control panel
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill="x", pady=(0, 10))

        # File selection
        ttk.Button(control_frame, text="Load Image", command=self.load_image).pack(side="left", padx=(0, 10))

        # Process button
        self.process_btn = ttk.Button(control_frame, text="Process Image", command=self.process_image, state="disabled")
        self.process_btn.pack(side="left", padx=(0, 10))

        # Export button
        self.export_btn = ttk.Button(control_frame, text="Export Results", command=self.export_results, state="disabled")
        self.export_btn.pack(side="left")

        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)

        # Left panel - Images
        left_frame = ttk.Frame(content_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Image display tabs
        self.notebook = ttk.Notebook(left_frame)
        self.notebook.pack(fill="both", expand=True)

        # Original image tab
        self.original_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.original_frame, text="Original")

        self.original_canvas = ttk.Label(self.original_frame)
        self.original_canvas.pack(fill="both", expand=True)

        # Difference map tab
        self.difference_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.difference_frame, text="Difference Map")

        self.difference_canvas = ttk.Label(self.difference_frame)
        self.difference_canvas.pack(fill="both", expand=True)

        # Contours tab
        self.contours_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.contours_frame, text="Contours")

        self.contours_canvas = ttk.Label(self.contours_frame)
        self.contours_canvas.pack(fill="both", expand=True)

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if not file_path:
            return

        self.current_image = cv2.imread(file_path)
        self.display_image(self.current_image, self.original_canvas)
        self.process_btn["state"] = "normal"

    def process_image(self):
        if self.current_image is None:
            messagebox.showerror("Error", "No image loaded.")
            return

        # Convert to grayscale
        gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)

        # Calculate gradient magnitude (difference map)
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        difference_map = cv2.magnitude(grad_x, grad_y)

        # Normalize difference map for visualization
        difference_map = cv2.normalize(difference_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # Apply dilation to the difference map
        kernel = np.ones((3, 3), np.uint8)
        dilated_difference_map = cv2.dilate(difference_map, kernel, iterations=1)
        self.difference_map = dilated_difference_map
        self.display_image(self.difference_map, self.difference_canvas, cmap="gray")

        # Apply OCR mask
        ocr_results = self.ocr.ocr(self.current_image, cls=True)
        ocr_mask = np.zeros_like(self.difference_map, dtype=np.uint8)
        for result in ocr_results[0]:
            box = np.array(result[0]).astype(np.int32)
            cv2.fillPoly(ocr_mask, [box], 255)

        # Mask the difference map
        masked_difference_map = cv2.bitwise_and(self.difference_map, self.difference_map, mask=cv2.bitwise_not(ocr_mask))

        # Detect contours on the masked difference map
        contours, _ = cv2.findContours(masked_difference_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours_image = np.zeros_like(self.difference_map)
        cv2.drawContours(contours_image, contours, -1, (255, 255, 255), thickness=1)
        self.contours_image = contours_image
        self.display_image(self.contours_image, self.contours_canvas, cmap="gray")

        self.export_btn["state"] = "normal"

    def export_results(self):
        if self.difference_map is None or self.contours_image is None:
            messagebox.showerror("Error", "No results to export.")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Files", "*.png")])
        if not save_path:
            return

        cv2.imwrite(save_path, self.contours_image)
        messagebox.showinfo("Success", "Contours exported successfully.")

    def display_image(self, image, canvas, cmap=None):
        if cmap == "gray":
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        image = Image.fromarray(image)
        image_tk = ImageTk.PhotoImage(image=image)
        canvas.configure(image=image_tk)
        canvas.image = image_tk

if __name__ == "__main__":
    import tkinter as tk

    root = tk.Tk()
    app = OCRDifferenceMapGUI(root)
    root.mainloop()
