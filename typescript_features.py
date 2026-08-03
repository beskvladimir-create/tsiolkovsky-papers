#!/usr/bin/env python3
"""
The features that tell typescript from handwriting.

The regularity of line spacing will not do it: neat cursive gives a line pitch
as even as print. Labelling the sheets by hand showed that outright.

What does separate them is this.

1. CHARACTER PITCH. A typewriter is monospaced: every character lands on a grid
   at a fixed step. Take the column projection of the ink within a line and
   autocorrelate it, and typescript shows a sharp peak at the character pitch.
   Joined-up cursive has no such grid, and the peak is smeared out.

2. LENGTH OF CONNECTED STROKES. In cursive the letters are joined, so the ink
   runs along a line are long. In typescript the characters stand apart, the
   runs are short and uniform, and the gaps between them are all alike.

3. EVENNESS OF HEIGHT. Printed characters sit within a fixed line; in
   handwriting the ascenders and descenders wander, and the thickness of the
   band of text varies more from line to line.

No single feature settles it, so all of them are computed and read together.
The decision made from them lives in reclassify.py, and it is validated against
labelled_pages.csv.
"""
import numpy as np
from PIL import Image

WIDTH = 1200  # wider than in classify_pages: the character pitch is fine and
              # easily lost at lower resolution


def text_bands(mask, min_h=3):
    proj = mask.mean(axis=1)
    thr = proj.mean() + 0.15 * proj.std() if proj.std() > 0 else 1.0
    on = proj > max(thr, 0.01)
    st, en, prev = [], [], False
    for i, v in enumerate(on):
        if v and not prev:
            st.append(i)
        elif not v and prev:
            en.append(i)
        prev = v
    if prev:
        en.append(len(on))
    return [(s, e) for s, e in zip(st, en) if e - s >= min_h]


def pitch_score(col):
    """How strongly periodic the column projection of a line is.

    Returns (peak strength, pitch in pixels). The autocorrelation is taken on
    the centred signal, and the maximum is sought over pitches of 4 to 40 px.
    """
    x = col - col.mean()
    if x.std() < 1e-6 or len(x) < 60:
        return 0.0, 0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    if ac[0] <= 0:
        return 0.0, 0
    ac = ac / ac[0]
    lo, hi = 4, min(40, len(ac) - 1)
    if hi <= lo:
        return 0.0, 0
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    return float(seg[k]), lo + k


def run_stats(row_mask):
    """Lengths of the ink runs and of the gaps between them along a line."""
    d = np.diff(row_mask.astype(np.int8))
    starts = np.flatnonzero(d == 1) + 1
    ends = np.flatnonzero(d == -1) + 1
    if row_mask[0]:
        starts = np.r_[0, starts]
    if row_mask[-1]:
        ends = np.r_[ends, len(row_mask)]
    n = min(len(starts), len(ends))
    if n == 0:
        return None
    ink = (ends[:n] - starts[:n]).astype(float)
    gaps = (starts[1:n] - ends[:n - 1]).astype(float) if n > 1 else np.array([])
    return ink, gaps


def features(path):
    try:
        im = Image.open(path).convert("L")
    except Exception:
        return None
    w, h = im.size
    if w != WIDTH:
        im = im.resize((WIDTH, max(1, int(h * WIDTH / w))), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32)
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    if hi - lo < 1e-3:
        return None
    n = np.clip((a - lo) / (hi - lo), 0, 1)
    mask = n < 0.55

    bands = text_bands(mask)
    if len(bands) < 4:
        return None

    pitches, peaks, ink_cv, gap_cv, heights = [], [], [], [], []
    for s, e in bands:
        strip = mask[s:e]
        if strip.shape[0] < 3:
            continue
        col = strip.mean(axis=0)
        pk, pt = pitch_score(col)
        peaks.append(pk)
        pitches.append(pt)
        rs = run_stats(col > col.mean() * 0.6)
        if rs:
            ink, gaps = rs
            if len(ink) >= 4 and ink.mean() > 0:
                ink_cv.append(float(ink.std() / ink.mean()))
            if len(gaps) >= 4 and gaps.mean() > 0:
                gap_cv.append(float(gaps.std() / gaps.mean()))
        heights.append(e - s)

    if not peaks:
        return None
    heights = np.array(heights, dtype=float)
    pit = np.array(pitches, dtype=float)
    pit_valid = pit[pit > 0]

    return {
        # strength of the periodicity: high and consistent across typed lines
        "pitch_peak": round(float(np.median(peaks)), 3),
        # how far the lines agree on the pitch: one and the same for typescript
        "pitch_agree": round(float(1.0 - (pit_valid.std() / pit_valid.mean()))
                             if len(pit_valid) >= 3 and pit_valid.mean() > 0 else 0.0, 3),
        # spread of ink-run lengths: larger for cursive, whose strokes join up
        "ink_cv": round(float(np.median(ink_cv)) if ink_cv else 0.0, 3),
        # spread of the gaps between characters: small for typescript
        "gap_cv": round(float(np.median(gap_cv)) if gap_cv else 0.0, 3),
        # evenness of the height of the bands of text
        "height_cv": round(float(heights.std() / heights.mean())
                           if heights.mean() > 0 else 0.0, 3),
        "bands": len(bands),
    }


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, features(p))
