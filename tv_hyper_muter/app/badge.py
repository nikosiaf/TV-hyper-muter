"""Age-rating badge detector shared by the live muter and the offline tests.

The badge is a small circle (about 10 px across at 320x180) in a fixed corner per channel.
The score is the correlation between the image gradient and a synthetic ring, so the digit
inside (K, 8, 12, 16, 18) does not matter. Searching +-SHIFT px allows for small encoder shifts.
"""
from functools import lru_cache

import numpy as np

# channel -> (centre_y, centre_x, radius) at 320x180; filled in by calibrate.py
CENTRES = {}
THRESHOLD = 0.45
SHIFT = 2  # search +-SHIFT px around the learned centre (was 1; Alpha badge moved 1-2 px on Happy Day, 2026-11-03)


def grad(a):
    gy = np.zeros_like(a)
    gx = np.zeros_like(a)
    gy[1:-1] = (a[2:] - a[:-2]) / 2
    gx[:, 1:-1] = (a[:, 2:] - a[:, :-2]) / 2
    return np.hypot(gx, gy)


@lru_cache(maxsize=64)
def _ring(r, half):
    t = _ring_raw(r, half)
    t.setflags(write=False)
    return t, float(np.linalg.norm(t))


def ring(r, half=9):
    return _ring(float(r), half)[0]


def _ring_raw(r, half=9):
    yy, xx = np.mgrid[-half:half + 1, -half:half + 1]
    d = np.hypot(yy, xx)
    t = np.exp(-((d - r) ** 2) / (2 * 0.8 ** 2))
    return t - t.mean()


def score_at(g, cy, cx, r, half=9, shift=None):
    shift = SHIFT if shift is None else shift
    t, tn = _ring(float(r), half)
    best = -1.0
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            y, x = cy + dy, cx + dx
            if y - half < 0 or x - half < 0 or y + half + 1 > g.shape[0] or x + half + 1 > g.shape[1]:
                continue
            p = g[y - half:y + half + 1, x - half:x + half + 1]
            p = p - p.mean()
            s = float((p * t).sum() / (np.linalg.norm(p) * tn + 1e-6))
            best = max(best, s)
    return best


def score(gray, channel):
    # a channel may have several badge shapes, e.g. Open: full badge (9,307,4) at programme
    # start, smaller one (9,308,3) during talk shows (2026-11-03); best match wins
    c = CENTRES[channel]
    shapes = c if isinstance(c[0], (list, tuple)) else [c]
    return score_grad(grad(gray), channel)


def score_grad(g, channel):
    """score() on an already computed gradient image."""
    c = CENTRES[channel]
    shapes = c if isinstance(c[0], (list, tuple)) else [c]
    return max(score_at(g, cy, cx, r) for cy, cx, r in shapes)


def caption(gray, cy, cx):
    """Programme caption next to a top-left badge (Skai: 'Κατάλληλο για όλους' in two small lines).

    Text energy (mean horizontal brightness change) of the two caption lines minus the gap row
    between them. Skai's own promos carry the same badge but with one big day/time label across
    the gap row ('ΣΑΒΒΑΤΟ 14:30'), or the badge alone; both score <= 0, captions 17-40 (2026-11-04/05).
    """
    a = np.asarray(gray, float)
    x0, x1 = cx + 5, cx + 47
    if cy - 1 < 0 or cy + 2 >= a.shape[0] or x1 + 1 > a.shape[1]:
        return 0.0
    e = lambda y: float(np.abs(np.diff(a[y, x0:x1])).mean())
    return min(e(cy - 1), e(cy)) - e(cy + 2)
