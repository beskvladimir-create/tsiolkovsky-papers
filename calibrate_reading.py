#!/usr/bin/env python3
"""
How much worse handwriting reads than typescript, measured on the same text.

Part of the fond holds each text twice: the author's manuscript and a typed
copy of it sit in the same file. That is a ready-made experiment. One source,
one pipeline, and the only thing that differs is how hard the page is to read,
so the whole gap between the two transcriptions belongs to the reading of the
handwriting.

Pairs are found by content, not by sheet number: for each handwritten sheet we
look for the typed sheet most similar to it and keep the pair if the similarity
clears a threshold. The threshold is deliberately low, because at poor reading
quality even identical text scores only moderately, while unrelated sheets
score distinctly lower.

What matters is not only the share of matching words but the length of the runs
that match. Aligning long texts depends on long verbatim anchors, and if the
longest run is short, redactions cannot be collated word by word at all. That
is the number this script exists to produce, and compare_variants.py reads it
back as a floor.

    python3 calibrate_reading.py
"""
import csv
import difflib
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets, clean, fold

MIN_WORDS = 40    # short sheets give unstable similarity
MIN_RATIO = 0.25  # below this a pair is treated as unrelated


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def page_class():
    cls = {}
    with open("page_classes.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.search(r"(delo_\d+)/.*?(\d+)\.jpg", r["path"])
            if m:
                cls[(m.group(1), m.group(2))] = r["class"]
    return cls


def main():
    cls = page_class()
    pairs = []
    for path in sorted(glob.glob("data/transcripts/opis_1/*.md")):
        delo = os.path.basename(path)[:-3]
        sh = read_sheets(path)
        hand, typed = [], []
        for k, v in sh.items():
            t = toks(v)
            if len(t) < MIN_WORDS:
                continue
            c = cls.get((delo, k))
            (hand if c == "hand" else typed if c == "typed" else []).append((k, t))
        if not hand or not typed:
            continue
        for hk, ht in hand:
            best, bt, bk = 0.0, None, None
            for tk, tt in typed:
                m = difflib.SequenceMatcher(None, ht, tt, autojunk=False)
                if m.quick_ratio() <= best:
                    continue
                r = m.ratio()
                if r > best:
                    best, bt, bk = r, tt, tk
            if best >= MIN_RATIO:
                m = difflib.SequenceMatcher(None, ht, bt, autojunk=False)
                blocks = [b.size for b in m.get_matching_blocks() if b.size]
                pairs.append(dict(delo=delo, hand=hk, typed=bk,
                                  words_hand=len(ht), words_typed=len(bt),
                                  ratio=round(best, 3),
                                  longest_run=max(blocks) if blocks else 0))

    if not pairs:
        print("no pairs found")
        return
    pairs.sort(key=lambda p: -p["ratio"])
    med = lambda x: sorted(x)[len(x) // 2]
    rs = [p["ratio"] for p in pairs]
    ls = [p["longest_run"] for p in pairs]
    print(f"  manuscript/typescript pairs of one text: {len(pairs)}")
    print(f"  from files: {len(set(p['delo'] for p in pairs))}")
    print(f"\n  agreement between two readings of the same text:")
    print(f"    median {med(rs)*100:.0f}%   best {max(rs)*100:.0f}%   "
          f"worst {min(rs)*100:.0f}%")
    print(f"  longest verbatim matching run, words:")
    print(f"    median {med(ls)}   best {max(ls)}   worst {min(ls)}")
    print(f"    pairs with no run longer than 10 words: "
          f"{sum(1 for x in ls if x < 10)/len(ls)*100:.0f}%")
    with open("reading_calibration.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pairs[0]))
        w.writeheader()
        w.writerows(pairs)
    print(f"\n  table: reading_calibration.csv")
    print(f"\n  examples:")
    for p in pairs[:8]:
        print(f"    {p['delo']} sheet {p['hand']} against {p['typed']}: "
              f"agreement {p['ratio']*100:.0f}%, longest run "
              f"{p['longest_run']} words")


if __name__ == "__main__":
    main()
