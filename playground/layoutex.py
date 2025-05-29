import cv2
from doclayout_yolo import YOLOv10

# Load the pre-trained model
model = YOLOv10("path/to/provided/model")

# Perform prediction
det_res = model.predict(
    "OmniParser/pls.png",   # Image to predict
    conf=0.2,          # Confidence threshold
    device="cpu"    # Device to use (e.g., 'cuda:0' or 'cpu')
)

# Annotate and save the result
annotated_frame = det_res[0].plot(pil=True, line_width=5, font_size=20)
cv2.imwrite("doclay_annotated.png", annotated_frame)