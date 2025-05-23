import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from paddleocr import PaddleOCR

# Initialize the PaddleOCR with English language by default
# You can change it to a different language if needed
ocr = PaddleOCR(use_textline_orientation=True, lang='en')  # Changed use_angle_cls to use_textline_orientation

class OCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OCR Image Viewer")

        self.canvas = tk.Canvas(root, width=800, height=600)
        self.canvas.pack()

        self.btn = tk.Button(root, text="Load Image", command=self.load_image)
        self.btn.pack()

        self.text_display = tk.Text(root, height=10, width=80)
        self.text_display.pack(pady=10)

        self.tk_img = None

    def load_image(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")]
        )
        if not filepath:
            return

        image = cv2.imread(filepath)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)        # Run OCR with PaddleOCR
        result = ocr.predict(image) # Changed from ocr.ocr and removed cls=True
        
        # Create a copy of the original image for drawing boxes
        image_with_boxes = image_rgb.copy()
        
        # Clear previous text
        self.text_display.delete('1.0', tk.END)
        
        ocr_processed_successfully = False
        
        # Determine lines_data and handle structural issues with 'result'
        lines_data = None
        valid_result_structure_for_processing = False

        if result is None:
            self.text_display.insert(tk.END, "OCR Error: No result from predict() (result is None).\\n")
        elif not isinstance(result, list) or not result: # not a list or empty list
            self.text_display.insert(tk.END, f"OCR Error: Unexpected result format. Expected a non-empty list from predict(). Got type: {type(result)}.\\n")
        else:
            # result is a non-empty list. result[0] should contain the output for the first image.
            first_image_output = result[0]

            # Check if first_image_output is an object with a .data attribute (e.g., paddlex.OCRResult)
            if hasattr(first_image_output, 'data'):
                if isinstance(first_image_output.data, list):
                    lines_data = first_image_output.data
                    valid_result_structure_for_processing = True
                    # self.text_display.insert(tk.END, "Info: Used .data attribute (list) from OCRResult object.\\n")
                elif first_image_output.data is None: # Handle if .data is None (e.g., no text detected)
                    lines_data = [] # Treat as no lines detected
                    valid_result_structure_for_processing = True
                    # self.text_display.insert(tk.END, "Info: Used .data attribute (None) from OCRResult, treating as no lines.\\n")
                else:
                    # .data exists but is not a list and not None. This is unexpected.
                    self.text_display.insert(tk.END, f"OCR Error: result[0].data is of type '{type(first_image_output.data).__name__}'. Expected a list or None.\\n")
            elif isinstance(first_image_output, list): # Fallback: first_image_output is directly the list of lines
                lines_data = first_image_output
                valid_result_structure_for_processing = True
                # self.text_display.insert(tk.END, "Info: Used result[0] as list of lines directly.\\n") # Optional debug
            else:
                self.text_display.insert(tk.END, f"OCR Error: result[0] is of type '{type(first_image_output).__name__}'. Expected it to be a list of lines, or an object with a '.data' attribute that is a list of lines.\\n")
                # For debugging, attempt to list attributes of this unexpected object type
                if not isinstance(first_image_output, (dict, str, int, float, bool, type(None))):
                    try:
                        self.text_display.insert(tk.END, f"Attributes of result[0]: {dir(first_image_output)}\\n")
                    except Exception as e:
                        self.text_display.insert(tk.END, f"Could not list attributes of result[0]: {e}\\n")
        
        if valid_result_structure_for_processing:
            if lines_data: # If lines_data is a non-empty list
                for line_info in lines_data:
                    if not line_info or len(line_info) < 2:
                        # Ensure line_info has at least box and text_part
                        continue

                    box_coords = line_info[0] # These are the points for the polygon
                    text_part = line_info[1]  # This can be (text, score) or just text string

                    # Validate box_coords structure before attempting conversion
                    if not isinstance(box_coords, list) or not box_coords or not all(
                        isinstance(point, (list, tuple)) and len(point) == 2 and
                        all(isinstance(coord, (int, float)) for coord in point)
                        for point in box_coords
                    ):
                        # Optionally, log this error or print a warning
                        # print(f"Skipping malformed box_coords: {box_coords}")
                        continue # Skip this line_info if box_coords is not a list of coordinate pairs

                    text_content = ""
                    if isinstance(text_part, tuple) and len(text_part) >= 1:
                        text_content = text_part[0] # Get text from (text, score)
                    elif isinstance(text_part, str):
                        text_content = text_part # text_part is already the text string
                    else:
                        text_content = "[err_fmt]" # Placeholder for unrecognized format

                    # Convert box_coords to required format for drawing
                    poly_points = np.array(box_coords).astype(np.int32).reshape(-1, 2)
                    
                    # Draw the bounding box
                    cv2.polylines(image_with_boxes, [poly_points], True, (0, 255, 0), 2)
                    # Add text above the box
                    if poly_points.size > 0: # Ensure poly_points is not empty
                        cv2.putText(image_with_boxes, text_content, (int(poly_points[0][0]), int(poly_points[0][1] - 10)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    # Add to text display
                    self.text_display.insert(tk.END, text_content + " ")
                    ocr_processed_successfully = True # Set flag if at least one box is drawn

                if not ocr_processed_successfully and lines_data: # Loop ran over non-empty lines_data, but no lines were successfully processed
                    self.text_display.insert(tk.END, "Text detected, but all lines failed internal validation for drawing.\\n")
            else: # lines_data is an empty list (valid structure, but no text found)
                self.text_display.insert(tk.END, "No text detected by OCR (empty list of lines).\\n")
        # If valid_result_structure_for_processing is False, an error message about the structure was already printed.
                    
        image_pil = Image.fromarray(image_with_boxes) # Use a different variable name

        # Resize to fit canvas
        image_pil.thumbnail((800, 600))
        self.tk_img = ImageTk.PhotoImage(image_pil)
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img)

# Run the app
root = tk.Tk()
app = OCRApp(root)
root.mainloop()
