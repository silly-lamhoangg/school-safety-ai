import cv2
import ultralytics
import torch

print("OpenCV:", cv2.__version__)
print("Ultralytics:", ultralytics.__version__)
print("PyTorch:", torch.__version__)

if torch.cuda.is_available():
    print("GPU: Co the su dung CUDA")
else:
    print("GPU: Su dung CPU")

print("MOI TRUONG DA SAN SANG!")