"""Pitch detector for the sports veto: share of grass-green pixels in the picture.

Football pitches are yellow-green (hue 75-135 degrees, saturated, not dark). Green-screen
promos, teal product ads and a teleshopping spot with a green olive net (all 2026-11-04) sit
outside that range or fill too little of the picture for long. The top rows (scoreboard,
channel logo, badge) and the bottom band (tickers, captions) are left out.
"""
import numpy as np

SMALL = (80, 45)
ROWS = (6, 40)
HUE = (75, 135)  # degrees
SAT, VAL = 0.45, 0.30


def pitch(im):
    """im: PIL image of the frame (any mode). Returns the grass-green share, 0-1."""
    a = np.asarray(im.convert("RGB").resize(SMALL).convert("HSV"), float)[ROWS[0]:ROWS[1]]
    h, s, v = a[..., 0] * (360 / 255), a[..., 1] / 255, a[..., 2] / 255
    return float(((h >= HUE[0]) & (h <= HUE[1]) & (s >= SAT) & (v >= VAL)).mean())
