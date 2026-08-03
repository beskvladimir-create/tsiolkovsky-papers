#!/usr/bin/env python3
"""
Reclassifying every sheet with the validated feature.

classify_pages.py split the fond by the regularity of line spacing. Labelling
sheets by hand showed the feature is no good: neat cursive is as evenly spaced
as print, while typescript with paragraph indents looks irregular. The error
was not a small one, as it understated the share of typescript in the fond
nearly threefold.

What is used here is ink_cv from typescript_features: the spread of ink-run
lengths along a line. The threshold of 0.81 was checked against
labelled_pages.csv, 19 sheets out of 19, and independently against the
agreement of two readings of one text (calibrate_reading.py), where agreement
falls steadily as ink_cv rises.

Writes page_classes.csv: path, class, ink_cv.
"""
import csv
import os

from typescript_features import features

ROOT = os.path.dirname(os.path.abspath(__file__))
THR = 0.81  # below this, typescript; at or above it, handwriting


def main():
    paths = []
    for r, _, fs in os.walk(os.path.join(ROOT, "data")):
        if "transcripts" in r:
            continue
        for f in fs:
            if f.endswith(".jpg"):
                paths.append(os.path.join(r, f))
    paths.sort()
    out = os.path.join(ROOT, "page_classes.csv")
    n = {"hand": 0, "typed": 0, "note": 0}
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "class", "ink_cv"])
        for i, p in enumerate(paths, 1):
            f = features(p)
            if f is None:
                # too few bands of text to measure: a note, a cover or a blank
                cls, cv = "note", ""
            else:
                cls = "typed" if f["ink_cv"] < THR else "hand"
                cv = f["ink_cv"]
            n[cls] += 1
            w.writerow([os.path.relpath(p, ROOT), cls, cv])
            if i % 2000 == 0:
                print(f"  {i}/{len(paths)}", flush=True)
    tot = sum(n.values())
    print(f"\n  done: {tot:,} scans -> {out}")
    for k, v in n.items():
        print(f"    {k:<6} {v:>6}  {v/tot*100:>5.1f}%")


if __name__ == "__main__":
    main()
