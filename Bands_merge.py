import numpy as np
from PIL import Image
import math
import glob
import os

# ---- CONFIG ----
BASE_PATH = r"posters\Marseille"
IMAGE_GLOB = os.path.join(BASE_PATH, "*.png")
ANGLE_DEG = -10
FADE_RATIO = 0.5 # x% of band width is used for blending. Other value used 0.75
OUTPUT_PATH = os.path.join(BASE_PATH, "output_bands.png")
# ----------------

paths = sorted(glob.glob(IMAGE_GLOB))

# Filter out the output file
paths = [p for p in paths if os.path.abspath(p) != os.path.abspath(OUTPUT_PATH)]

images = [np.array(Image.open(p).convert("RGBA")) for p in paths]

if not images:
    raise ValueError("No images found")

h, w, _ = images[0].shape
n = len(images)

stack = np.stack(images, axis=0)
out = np.zeros((h, w, 4), dtype=np.uint8)

theta = math.radians(-ANGLE_DEG)
cos_t = math.cos(theta)
sin_t = math.sin(theta)

yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")

xr = (xx * cos_t - yy * sin_t)
xr_min, xr_max = xr.min(), xr.max()
band_width = (xr_max - xr_min) / n

idx = ((xr - xr_min) // band_width).astype(int)
idx = np.clip(idx, 0, n - 1)

fade_width = band_width * FADE_RATIO

for i in range(n):
    mask_i = (idx == i)
    out[mask_i] = stack[i][mask_i]

# Crossfade boundaries
for i in range(n - 1):
    boundary_start = xr_min + (i + 1) * band_width - fade_width
    boundary_end = xr_min + (i + 1) * band_width + fade_width

    mask = (xr >= boundary_start) & (xr <= boundary_end)

    t = (xr[mask] - boundary_start) / (boundary_end - boundary_start)
    t = np.clip(t, 0, 1)

    img_a = stack[i][mask].astype(float)
    img_b = stack[i + 1][mask].astype(float)

    blended = img_a * (1 - t[:, None]) + img_b * t[:, None]
    out[mask] = blended.astype(np.uint8)

Image.fromarray(out).save(OUTPUT_PATH)
print("Done")