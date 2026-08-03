#!/usr/bin/env python3
"""
Refitting the page classifier against labels that come from the reading.

The classifier in reclassify.py decides from the image alone, on the variation
in ink-run lengths, with a threshold fitted to 19 pages labelled by hand. It
passed that test and still fails at scale, in both directions: carbon copies
and faded typescript read as handwriting to it, and manuscripts written in a
clean hand read as typescript. Sampling shows this plainly. A page it called
handwriting opens "ТРУДЫ О КОСМИЧЕСКОЙ РАКЕТЕ /1903-1927 г./" with typewriter
slashes and a printed page number; a page it called typescript carries
pre-reform orthography, struck-out words and an insertion in the margin.

Nineteen labels could not have caught this. What can is the transcription
itself. The share of uncertainty marks the model leaves on a page is a signal
of an entirely different kind: it comes from reading the page rather than from
measuring its ink, and over the transcribed corpus it separates cleanly, at 0.5
marks per hundred words on typescript against 3.9 on handwriting. That gives
4,287 labelled sheets instead of 19.

The label is not ground truth either, so the rule fitted here is deliberately
simple and is reported with its errors rather than presented as settled. It is
fitted on one half of the sheets and scored on the other, so the accuracy
quoted is not the accuracy it was tuned to.

    python3 refit_classifier.py --features    measure the images (slow, once)
    python3 refit_classifier.py               fit and score
"""
import argparse
import csv
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets
from typescript_features import features

ROOT = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(ROOT, "refit_features.csv")
COLS = ["pitch_peak", "pitch_agree", "ink_cv", "gap_cv", "height_cv", "bands"]
MIN_UNCERTAIN = 0.02


def labels():
    """Sheet -> reads-as-handwriting, from the transcription's own doubt."""
    out = {}
    for p in glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md")):
        opis = os.path.basename(os.path.dirname(p)).replace("opis_", "")
        delo = os.path.basename(p)[:-3]
        for k, v in read_sheets(p).items():
            w = len(v.split())
            if w < 30:
                continue
            u = (v.count("[?]") + len(re.findall(r"\[неразборчиво", v))) / w
            out[f"data/opis_{opis}/{delo}/{k}.jpg"] = 1 if u >= MIN_UNCERTAIN else 0
    return out


def measure(lab):
    done = set()
    if os.path.exists(FEAT):
        with open(FEAT, encoding="utf-8") as f:
            done = {r["path"] for r in csv.DictReader(f)}
    todo = [p for p in lab if p not in done and os.path.exists(os.path.join(ROOT, p))]
    print(f"  {len(lab)} labelled sheets, {len(done)} measured, {len(todo)} to go",
          flush=True)
    new = not os.path.exists(FEAT)
    with open(FEAT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "hand"] + COLS)
        if new:
            w.writeheader()
        for i, p in enumerate(todo, 1):
            fe = features(os.path.join(ROOT, p))
            if fe is None:
                continue
            w.writerow(dict(path=p, hand=lab[p], **{c: fe[c] for c in COLS}))
            if i % 250 == 0:
                f.flush()
                print(f"  {i}/{len(todo)}", flush=True)


def fit_threshold(rows, col):
    """The single cut on one feature that gets the most sheets right."""
    vals = sorted({r[col] for r in rows})
    best = (0, None, None)
    for i in range(len(vals) - 1):
        t = (vals[i] + vals[i + 1]) / 2
        for sense in (1, -1):
            ok = sum(1 for r in rows
                     if (r[col] > t if sense > 0 else r[col] <= t) == bool(r["hand"]))
            if ok > best[0]:
                best = (ok, t, sense)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", action="store_true",
                    help="measure the images; slow, and only needs doing once")
    args = ap.parse_args()

    lab = labels()
    if args.features:
        measure(lab)
        return
    if not os.path.exists(FEAT):
        raise SystemExit("no features yet: run with --features first")

    rows = []
    with open(FEAT, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = {"path": r["path"], "hand": int(r["hand"])}
            for c in COLS:
                d[c] = float(r[c])
            rows.append(d)
    # Split by hash of the path, so the halves stay the same between runs and
    # sheets of one file do not all land on the same side.
    train = [r for r in rows if hash(r["path"]) % 2 == 0]
    test = [r for r in rows if hash(r["path"]) % 2 == 1]
    share = sum(r["hand"] for r in rows) / len(rows)
    print(f"  sheets {len(rows)}, reading as handwriting {share*100:.0f}%")
    print(f"  fitted on {len(train)}, scored on {len(test)}\n")

    print(f"  {'feature':<13}{'cut':>9}{'sense':>7}{'on fit':>9}{'on held out':>13}")
    scored = []
    for c in COLS:
        ok, t, sense = fit_threshold(train, c)
        hit = sum(1 for r in test
                  if (r[c] > t if sense > 0 else r[c] <= t) == bool(r["hand"]))
        scored.append((hit / len(test), c, t, sense))
        print(f"  {c:<13}{t:>9.3f}{'>' if sense > 0 else '<=':>7}"
              f"{ok/len(train)*100:>8.0f}%{hit/len(test)*100:>12.0f}%")

    scored.sort(reverse=True)
    acc, c, t, sense = scored[0]
    base = max(share, 1 - share)
    print(f"\n  best single feature: {c} {'>' if sense > 0 else '<='} {t:.3f}, "
          f"{acc*100:.0f}% on held-out sheets")
    print(f"  always guessing the commoner class would give {base*100:.0f}%")
    old = sum(1 for r in test if (r["ink_cv"] >= 0.81) == bool(r["hand"]))
    print(f"  the published rule, ink_cv >= 0.81, gets {old/len(test)*100:.0f}%")


if __name__ == "__main__":
    main()
