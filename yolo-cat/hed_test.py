import cv2
img = cv2.imread("../OmniParser/pls_backup.png")
(H, W) = img.shape[:2]
blob = cv2.dnn.blobFromImage(img, scalefactor=1.0, size=(W, H),
    swapRB=False, crop=False)
net = cv2.dnn.readNetFromCaffe("deploy.prototxt", "hed_pretrained_bsds.caffemodel")
net.setInput(blob)
hed = net.forward()
hed = cv2.resize(hed[0, 0], (W, H))
hed = (255 * hed).astype("uint8")
# Save the images instead of displaying them
cv2.imwrite("input_image.png", img)
cv2.imwrite("hed_output.png", hed)
print("Images saved as 'input_image.png' and 'hed_output.png'")