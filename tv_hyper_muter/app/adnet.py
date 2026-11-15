"""MobileNetV3-Large feature extractor in plain numpy (no torch / onnxruntime).

Weights: torchvision IMAGENET1K_V2, batch-norm folded into the convolutions (export_weights.py).
Input: PIL image -> 160x288 RGB; output: 960 pooled features, the same vector as torchvision's
model with the classifier removed.
"""
import numpy as np
from PIL import Image

H, W = 160, 288
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
STRIDE2 = {2, 4, 7, 13}          # blocks that halve the picture
HSWISH_FROM = 7                  # blocks 1-6 use ReLU, 7-15 hard-swish


def hswish(x):
    return x * np.clip(x + 3.0, 0.0, 6.0) * (1.0 / 6.0)


def relu(x):
    return np.maximum(x, 0.0)


def dwconv(x, w, b, stride):
    """Depthwise k x k convolution. x: (h, w, c), w: (k, k, c)."""
    k = w.shape[0]
    p = (k - 1) // 2
    xp = np.pad(x, ((p, p), (p, p), (0, 0)))
    h, wd = x.shape[0], x.shape[1]
    oh, ow = (h + 2 * p - k) // stride + 1, (wd + 2 * p - k) // stride + 1
    out = np.zeros((oh, ow, x.shape[2]), np.float32)
    for i in range(k):
        for j in range(k):
            out += xp[i:i + stride * oh:stride, j:j + stride * ow:stride] * w[i, j]
    return out + b


class Net:
    def __init__(self, path):
        z = np.load(path)
        self.p = {k: z[k].astype(np.float32) for k in z.files}

    def features(self, im):
        p = self.p
        im = im.convert("RGB")
        if im.size != (W, H):
            im = im.resize((W, H), Image.BILINEAR)
        x = (np.asarray(im, np.float32) / 255.0 - MEAN) / STD
        # stem: 3x3 stride 2, 3 -> 16
        xp = np.pad(x, ((1, 1), (1, 1), (0, 0)))
        oh, ow = H // 2, W // 2
        cols = np.concatenate([xp[i:i + 2 * oh:2, j:j + 2 * ow:2] for i in range(3) for j in range(3)], axis=2)
        x = hswish(cols @ p["stem.w"] + p["stem.b"])
        for n in range(1, 16):
            act = hswish if n >= HSWISH_FROM else relu
            y = x
            if f"b{n}.exp.w" in p:
                y = act(y @ p[f"b{n}.exp.w"] + p[f"b{n}.exp.b"])
            y = act(dwconv(y, p[f"b{n}.dw.w"], p[f"b{n}.dw.b"], 2 if n in STRIDE2 else 1))
            if f"b{n}.se1.w" in p:
                s = y.mean((0, 1))
                s = relu(s @ p[f"b{n}.se1.w"] + p[f"b{n}.se1.b"])
                s = np.clip((s @ p[f"b{n}.se2.w"] + p[f"b{n}.se2.b"]) / 6.0 + 0.5, 0.0, 1.0)
                y = y * s
            y = y @ p[f"b{n}.pr.w"] + p[f"b{n}.pr.b"]
            x = x + y if y.shape == x.shape and n not in STRIDE2 else y
        x = hswish(x @ p["head.w"] + p["head.b"])
        return x.mean((0, 1))
