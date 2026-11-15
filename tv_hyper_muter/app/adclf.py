"""Ad-or-programme check on the picture itself (shadow mode in 0.14.0: logged, never acted on).

A frozen MobileNetV3-Large (adnet.py, plain numpy) turns one frame every ~5 s into 960 features.
A small head trained on a labelled recording week (2026-11-09..15, 42k frames) looks at the mean
and spread of those features over the last 30 s, plus how much the picture changes, and gives
P(ad). `prob()` is the mean of P over the last 25 s: the number a mute decision would be checked
against. Trained on frames 5 s apart, so frames are taken at that pace whatever the grab interval.
"""
import os

import numpy as np
from PIL import Image

import adnet

HERE = os.path.dirname(os.path.abspath(__file__))
EVERY_S = 4.5      # take a frame when the last one is at least this old
WINDOW_S = 30      # features: last 30 s
SMOOTH_S = 25      # verdict: mean P over the last 25 s
GAP_S = 20         # a longer gap between frames starts a new window
FRESH_S = 12       # prob() is None when the newest P is older than this


class AdClassifier:
    def __init__(self, model_dir=None):
        d = model_dir or os.path.join(HERE, "model")
        self.net = adnet.Net(os.path.join(d, "adnet_weights.npz"))
        h = np.load(os.path.join(d, "adhead.npz"))
        self.mu, self.sd = h["mu"], h["sd"]
        self.w1, self.b1, self.w2, self.b2 = h["W1"], h["b1"], h["W2"], h["b2"]
        self.reset()

    def reset(self, channel=None):
        self.channel = channel
        self.frames = []   # (t, features, thumbnail, change vs the frame before)
        self.ps = []       # (t, P(ad) of the window ending at t)

    def head(self, f):
        z = np.maximum(((f - self.mu) / self.sd) @ self.w1 + self.b1, 0.0) @ self.w2 + self.b2
        return float(1.0 / (1.0 + np.exp(-z[0])))

    def add(self, t, channel, im):
        """Feed a 320x180 colour frame; returns True when it was used (one every ~5 s)."""
        if channel != self.channel or (self.frames and t - self.frames[-1][0] > GAP_S):
            self.reset(channel)
        if self.frames and t - self.frames[-1][0] < EVERY_S:
            return False
        thumb = np.asarray(im.convert("L").resize((32, 18), Image.BILINEAR), np.float32)
        change = float(np.abs(thumb - self.frames[-1][2]).mean()) if self.frames else 0.0
        self.frames = [f for f in self.frames + [(t, self.net.features(im), thumb, change)]
                       if t - f[0] <= WINDOW_S]
        x = np.stack([f[1] for f in self.frames])
        m = np.array([f[3] for f in self.frames[1:]] or [0.0], np.float32)
        feat = np.concatenate([x.mean(0), x.std(0),
                               [m.mean(), m.max(), m.min(), (m > 25).mean(), (m < 3).mean()]])
        self.ps = [p for p in self.ps + [(t, self.head(feat.astype(np.float32)))] if t - p[0] <= SMOOTH_S]
        return True

    def prob(self, t):
        if not self.ps or t - self.ps[-1][0] > FRESH_S:
            return None
        return sum(p for _, p in self.ps) / len(self.ps)
