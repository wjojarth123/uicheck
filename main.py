import tkinter as tk
from ocrui import OCREdgeDetectionGUI

if __name__ == "__main__":
    root = tk.Tk()
    app = OCREdgeDetectionGUI(root)
    root.mainloop()
