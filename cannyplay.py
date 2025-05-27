import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import numpy as np

def load_image():
    global img, img_display, canvas, photo
    file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.png;*.jpeg")])
    if file_path:
        img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
        update_image()

def update_image():
    global img, img_display, canvas, photo
    if img is not None:
        low = low_slider.get()
        high = high_slider.get()
        edges = cv2.Canny(img, low, high)
        img_display = ImageTk.PhotoImage(image=Image.fromarray(edges))
        canvas.config(width=img_display.width(), height=img_display.height())
        canvas.create_image(0, 0, anchor=tk.NW, image=img_display)

def on_slider_change(event):
    update_image()

# Initialize Tkinter window
root = tk.Tk()
root.title("Canny Edge Detection")

# Load image button
load_button = ttk.Button(root, text="Load Image", command=load_image)
load_button.pack()

# Canvas to display image
canvas = tk.Canvas(root, width=500, height=500)
canvas.pack()

# Sliders for Canny thresholds
low_slider = tk.Scale(root, from_=0, to=1000, orient=tk.HORIZONTAL, label="Low Threshold", command=on_slider_change)
low_slider.set(50)
low_slider.pack(fill=tk.X)

high_slider = tk.Scale(root, from_=0, to=1000, orient=tk.HORIZONTAL, label="High Threshold", command=on_slider_change)
high_slider.set(150)
high_slider.pack(fill=tk.X)

# Global variables
img = None
img_display = None

# Run the Tkinter event loop
root.mainloop()