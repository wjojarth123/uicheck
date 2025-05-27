import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk
import os
import csv
import time
import random
from collections import deque

class ImageRater:
    def __init__(self, master):
        self.master = master
        self.master.title("Image Rater")
        self.image_folder = ""
        self.image_files = []
        self.current_index = 0
        self.ratings = {}

        self.last_25_scores = deque(maxlen=25)
        self.last_25_times = deque(maxlen=25)
        self.start_time = None

        self.load_existing_ratings()

        self.image_folder = filedialog.askdirectory(title="Select Image Folder")
        if not self.image_folder:
            exit()

        self.image_files = [f for f in os.listdir(self.image_folder)
                            if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

        random.shuffle(self.image_files)

        self.label = tk.Label(self.master)
        self.label.pack()

        self.info_label = tk.Label(self.master, text="")
        self.info_label.pack()

        self.stats_label = tk.Label(self.master, text="")
        self.stats_label.pack()

        self.master.bind("<Key>", self.key_press)
        self.show_image()

    def load_existing_ratings(self):
        self.csv_path = filedialog.askopenfilename(title="Load existing ratings CSV (cancel to skip)",
                                                   filetypes=[("CSV Files", "*.csv")])
        if self.csv_path and os.path.exists(self.csv_path):
            with open(self.csv_path, newline='') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    filename, score = row
                    self.ratings[filename] = float(score)
        else:
            self.csv_path = "ratings.csv"

    def show_image(self):
        if self.current_index >= len(self.image_files):
            self.label.config(text="All images rated.")
            self.save_ratings()
            return

        image_path = os.path.join(self.image_folder, self.image_files[self.current_index])
        try:
            image = Image.open(image_path)
        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
            self.current_index += 1
            self.show_image()
            return

        image.thumbnail((800, 800))
        self.tkimage = ImageTk.PhotoImage(image)
        self.label.config(image=self.tkimage)

        self.info_label.config(
            text=f"Image {self.current_index + 1}/{len(self.image_files)}: {self.image_files[self.current_index]}")
        self.update_stats_label()
        self.start_time = time.time()

    def update_stats_label(self):
        if self.last_25_scores:
            avg_score = sum(self.last_25_scores) / len(self.last_25_scores)
            avg_time = sum(self.last_25_times) / len(self.last_25_times)
            self.stats_label.config(
                text=f"Last 25 avg score: {avg_score:.2f} | Avg time: {avg_time:.2f}s")
        else:
            self.stats_label.config(text="Rate images (1–10), - = discard")

    def key_press(self, event):
        if not self.image_files:
            return

        filename = self.image_files[self.current_index]
        full_path = os.path.join(self.image_folder, filename)
        elapsed = time.time() - self.start_time

        if event.char in "123456789":
            score = float(event.char)
        elif event.char == "0":
            score = 10.0
        elif event.char == "-":
            try:
                os.remove(full_path)
                print(f"Deleted {filename}")
            except Exception as e:
                print(f"Error deleting {filename}: {e}")
            self.current_index += 1
            self.show_image()
            return
        elif event.char == "q":
            self.save_ratings()
            self.master.quit()
            return
        else:
            return

        if filename in self.ratings:
            self.ratings[filename] = (self.ratings[filename] + score) / 2.0
        else:
            self.ratings[filename] = score

        self.last_25_scores.append(score)
        self.last_25_times.append(elapsed)

        self.current_index += 1
        self.show_image()

    def save_ratings(self):
        with open(self.csv_path, "w", newline='') as f:
            writer = csv.writer(f)
            for filename, score in self.ratings.items():
                writer.writerow([filename, f"{score:.2f}"])
        print(f"Ratings saved to {self.csv_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageRater(root)
    root.mainloop()
