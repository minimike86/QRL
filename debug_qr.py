#!/usr/bin/env python3
"""Debug script to check QR image properties."""

import numpy as np
from PIL import Image

# Load first QR image
img_path = "qr_output/qr_0000.png"
img = Image.open(img_path)

print(f"Image: {img_path}")
print(f"Mode: {img.mode}")
print(f"Size: {img.size}")
print(f"Format: {img.format}")

# Convert to numpy array
img_array = np.array(img)
print(f"Array shape: {img_array.shape}")
print(f"Array dtype: {img_array.dtype}")
print(f"Array min/max: {img_array.min()}/{img_array.max()}")

# Show some pixel values
print(f"Sample pixels: {img_array[0:5, 0:5]}")