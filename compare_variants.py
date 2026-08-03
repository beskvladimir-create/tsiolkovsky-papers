#!/usr/bin/env python3
"""
Collating two redactions of one text, with a check on resolving power.

The fond holds "Космический корабль" in two variants, files 46 and 47, and that
is a rare chance: one conception written down twice. The difference between the
redactions would show what the author added, dropped and rephrased, where the
printed editions give only what survived.

But two texts can only be compared if they are read more accurately than they
differ, and on the manuscripts of this fond that condition fails. Two readings
of one and the same text agree on 38-55% of words, and the longest verbatim
matching run does not exceed about fifteen words (calibrate_reading.py, 400
manuscript/typescript pairs from 31 files). Aligning long texts depends on long
verbatim anchors, and with anchors this short the alignment falls apart: on the
first run it matched 4 words of one redaction against 1,877 of the other and
declared the result a rewritten passage.

So this script first reads the noise floor out of reading_calibration.csv and
compares it against the similarity actually observed. If the similarity does
not clear the floor, no differences are printed at all, because on this
material they cannot be told apart from misreadings. A list of "differences"
without that check would be an invention.

    python3 calibrate_reading.py          # the floor first
    python3 compare_variants.py A.md B.md --out report.md
"""
import argparse
import csv
import difflib
import os
import re
from collections import Counter


def read_sheets(path):
    s = open(path, encoding="utf-8").read()
    parts = re.split(r"^## Лист (\S+)\s*$", s, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


# Editorial marks the transcription convention puts in square brackets.
STRIP = re.compile(r"\[(?:другой почерк|на полях|штамп|вставка|рисунок|формула)[^\]]*\]")


def clean(t, drop_struck=True):
    """Remove editorial markup. Struck-through text goes by default: it belongs
    to revision within one redaction, not to the difference between them."""
    if drop_struck:
        t = re.sub(r"~~.*?~~", " ", t)
    t = STRIP.sub(" ", t)
    t = re.sub(r"\[неразборчиво[^\]]*\]", " ", t)
    t = t.replace("[?]", "")
    return re.sub(r"\s+", " ", t).strip()


def fold(t):
    """Fold orthography, so that pre-reform and modernised spellings of one
    word do not count as two different words."""
    t = re.sub(r"ъ(?=\s|$)", "", t.lower())
    for a, b in (("ѣ", "е"), ("і", "и"), ("ѳ", "ф"), ("ѵ", "и"), ("ё", "е")):
        t = t.replace(a, b)
    return re.sub(r"[^\w\s]", " ", t)


def token_stream(sheets, skip_cover=2):
    """The whole redaction as one stream of words, each tied to its sheet.

    Sheet boundaries mean nothing for the content: a sentence runs freely onto
    the next sheet. The first sheets are skipped as the archival cover, which
    is present in both redactions and has nothing to do with the text.
    """
    keys = sorted(sheets)[skip_cover:]
    toks, where = [], []
    for k in keys:
        for w in clean(sheets[k]).split():
            f = fold(w).strip()
            if f:
                toks.append(f)
                where.append(k)
    return toks, where


def runs(a_tok, b_tok, min_len=25):
    """Align the two word streams end to end.

    difflib finds the common stretches and what lies between them by itself;
    chopping the texts up beforehand is unnecessary, and it was exactly that
    chopping which spoiled the earlier approach, since one and the same passage
    fell into different chunks and never got paired.

    Only insertions and deletions of min_len words or more are returned: short
    discrepancies are variant readings and recognition errors, not differences
    between redactions.
    """
    sm = difflib.SequenceMatcher(None, a_tok, b_tok, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        la, lb = i2 - i1, j2 - j1
        if tag == "delete" and la >= min_len:
            out.append(("only_a", i1, i2, j1, j1))
        elif tag == "insert" and lb >= min_len:
            out.append(("only_b", i1, i1, j1, j2))
        elif tag == "replace" and max(la, lb) >= min_len:
            out.append(("replace", i1, i2, j1, j2))
    return sm, out


def noise_floor(delo_a, delo_b, path="reading_calibration.csv"):
    """The noise floor: how well two readings of one text agree.

    Pairs from the same files are used when there are any, otherwise the whole
    corpus. This is an upper bound on what the method could legitimately put
    down to a difference between redactions.
    """
    if not os.path.exists(path):
        return None, 0
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        return None, 0
    own = [r for r in rows if r["delo"] in (delo_a, delo_b)]
    use = own or rows
    rs = sorted(float(r["ratio"]) for r in use)
    return rs[len(rs) // 2], len(use)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-len", type=int, default=25,
                    help="how many words in a row count as a difference")
    args = ap.parse_args()

    ta, wa = token_stream(read_sheets(args.a))
    tb, wb = token_stream(read_sheets(args.b))
    sm, diffs = runs(ta, tb, args.min_len)

    common = sum(bl.size for bl in sm.get_matching_blocks())
    print(f"  {os.path.basename(args.a)}: {len(ta):,} words")
    print(f"  {os.path.basename(args.b)}: {len(tb):,} words")
    print(f"  text in common: {common:,} words "
          f"({common/len(ta)*100:.0f}% of the first, "
          f"{common/len(tb)*100:.0f}% of the second)")

    floor, n_pairs = noise_floor(os.path.basename(args.a)[:-3],
                                 os.path.basename(args.b)[:-3])
    observed = common / max(len(ta), len(tb))
    if floor is not None:
        print(f"  reading noise floor: {floor*100:.0f}% "
              f"(from {n_pairs} pairs known to be the same text)")
        if observed <= floor:
            print(f"  observed similarity {observed*100:.0f}% does not clear "
                  f"the floor: differences between the redactions cannot be "
                  f"told apart from reading errors.")
            print("  no differences reported.")
            return

    c = Counter(t for t, *_ in diffs)
    print(f"  substantial differences (from {args.min_len} words): {len(diffs)}")
    for k in ("only_a", "only_b", "replace"):
        if c[k]:
            lbl = {"only_a": "only in the first", "only_b": "only in the second",
                   "replace": "rewritten"}[k]
            print(f"    {lbl}: {c[k]}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("# Collation of two redactions\n\n")
            f.write(f"- First: `{args.a}`, {len(ta):,} words\n")
            f.write(f"- Second: `{args.b}`, {len(tb):,} words\n")
            f.write(f"- Text in common: {common:,} words\n\n")
            f.write("End-to-end word alignment. Orthography folded, "
                    "struck-through text and editorial marks removed, archival "
                    "covers skipped. Differences of "
                    f"{args.min_len} words or more are shown: shorter "
                    "discrepancies are variant readings and recognition "
                    "errors, not differences between redactions.\n\n")
            for tag, i1, i2, j1, j2 in sorted(
                    diffs, key=lambda d: -(max(d[2] - d[1], d[4] - d[3]))):
                lbl = {"only_a": "Only in the first redaction",
                       "only_b": "Only in the second redaction",
                       "replace": "Rewritten"}[tag]
                f.write(f"## {lbl}\n\n")
                if i2 > i1:
                    f.write(f"*first, sheet {wa[i1]}, {i2-i1} words*\n\n")
                    f.write("> " + " ".join(ta[i1:i2])[:1500] + "\n\n")
                if j2 > j1:
                    f.write(f"*second, sheet {wb[j1]}, {j2-j1} words*\n\n")
                    f.write("> " + " ".join(tb[j1:j2])[:1500] + "\n\n")
        print(f"  report: {args.out}")


if __name__ == "__main__":
    main()
