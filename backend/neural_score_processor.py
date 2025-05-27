from fastai.vision.all import *
from PIL import Image
import pathlib # Added import
import traceback # Import traceback

# Load the pre-trained model (replace 'path/to/your/resnet50_model.pkl' with the actual path)
# Ensure your model is exported correctly using learn.export()
def initialize_neural_model():
    global learn  # Declare 'learn' as a global variable to access it in the function
    try:
        # Add temporary patch for PosixPath issue on Windows
        temp = pathlib.PosixPath
        pathlib.PosixPath = pathlib.WindowsPath
        learn = load_learner('image_rating_model.pkl') # Assuming model.pkl is in the same directory or provide full path
    except FileNotFoundError:
        print("Error: Model file 'model.pkl' not found. Please ensure the model path is correct.")
        learn = None
    except Exception as e:
        print(f"Error loading the model: {e}")
        learn = None
    finally:
        # Revert the patch
        if 'temp' in locals(): # Ensure temp was defined
            pathlib.PosixPath = temp

def get_neural_score(screenshot_path):
    global learn  # Ensure 'learn' is accessible globally
    """
    Calculates the neural score for a given screenshot using a FastAI ResNet50 model.
    The model should be an image regression model that takes an image and returns a score.
    """
    if learn is None:
            return 3

    try:
        # Open the image
        img = Image.open(screenshot_path)
        
        # Convert image to RGB mode to ensure compatibility
        img = img.convert("RGB")
        
        # Get prediction (score)
        # The output of learn.predict(img) depends on how the model was trained.
        # If it's a regression model, pred might be a tensor with one value.
        # We assume the first element of the prediction is the score.
        pred, _, _ = learn.predict(img)
        
        # Assuming the score is the first element of the prediction tensor
        # and needs to be converted to a float.
        # Adjust this based on your model's output format.
        score = float(pred[0]) 
        
        print(f"Neural score calculated for {screenshot_path}: {score:.2f}")
        return score
    except FileNotFoundError:
        print(f"Error: Screenshot file not found at {screenshot_path}. Returning score 0.")
        return 0
    except Exception as e:
        print(f"Error processing image {screenshot_path} with the neural model: {e}")
        print("--- Traceback ---")
        traceback.print_exc()
        print("--- End Traceback ---")
        return 0

# Example usage (optional, for testing)
# if __name__ == '__main__':
#     # Create a dummy screenshot for testing if you don't have one
#     # from PIL import Image
#     # dummy_img = Image.new('RGB', (60, 30), color = 'red')
#     # dummy_img.save("dummy_screenshot.png")
#     # score = get_neural_score("dummy_screenshot.png")
#     # print(f"Test neural score: {score}")
#
#     # Test with an actual image if available
#     # Make sure 'model.pt' and an image (e.g., 'screenshot.png') are in the correct path
#     # score = get_neural_score("screenshot.png") # Replace with a valid image path
#     # print(f"Test neural score for screenshot.png: {score}")
