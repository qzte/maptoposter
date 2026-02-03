import numpy as np
from PIL import Image
import math
import glob
import os
from scipy.ndimage import gaussian_filter

# ---- CONFIG ----
BASE_PATH = r"posters\Marseille"
IMAGE_GLOB = os.path.join(BASE_PATH, "*.png")
GLOW_FOLDER = "glow"
OUTPUT_SUFFIX = "_glow"
SCALE_MULTIPLIER = 2.5   # scale the multiplier on sigma if changing poster lindewidth
# ----------------

paths = sorted(glob.glob(IMAGE_GLOB))

def add_glow(image_rgba, sigma=8, strength=0.6):
    img = image_rgba.astype(np.float32)
    rgb = img[..., :3]
    alpha = img[..., 3:]

    blurred = gaussian_filter(rgb, sigma=(sigma, sigma, 0))
    glow = rgb + blurred * strength
    glow = np.clip(glow, 0, 255)

    out = np.concatenate([glow, alpha], axis=2)
    return out.astype(np.uint8)

for path in paths:
    img = np.array(Image.open(path).convert("RGBA"))

    # create output folder
    base_dir = os.path.dirname(path)
    filename = os.path.basename(path)
    name, ext = os.path.splitext(filename)

    out_dir = os.path.join(base_dir, GLOW_FOLDER)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{name}{OUTPUT_SUFFIX}{ext}")

    # apply glow
    out = add_glow(img, sigma=10*SCALE_MULTIPLIER, strength=0.7)
    Image.fromarray(out).save(out_path)

print("Done")