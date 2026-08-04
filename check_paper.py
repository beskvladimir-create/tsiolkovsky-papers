#!/usr/bin/env python3
"""
Check every figure in the paper against the data it claims to describe.

The corpus grows with each night's run, so every number in the paper is a
snapshot of a moving thing. Editing them by hand is how the abstract came to
say 36% where section 6 said 37%: the pair count had been updated and the
percentage had not. One number wrong in one place is worse than a number
missing, because a reader who checks it stops trusting the rest.

So the figures are not maintained by hand any more. This recomputes each of
them from the files on disk and compares it with what the paper says, and it is
meant to be run before the paper is touched or sent anywhere.

It reports a disagreement rather than fixing it. A changed number can mean the
corpus grew, which calls for an edit, or that something broke, which calls for
an investigation, and a script cannot tell the two apart.

    python3 check_paper.py
"""
import csv
import glob
import os
import re
import statistics as st
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(ROOT, "paper", "paper.md")


def load(path):
    p = os.path.join(ROOT, path)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def corpus():
    files = sheets = marks = struck = 0
    for p in glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md")):
        t = open(p, encoding="utf-8").read()
        files += 1
        sheets += len(re.findall(r"^## Лист ", t, re.M))
        marks += t.count("[?]") + len(re.findall(r"\[неразборчиво", t))
        struck += len(re.findall(r"~~.+?~~", t))
    return files, sheets, marks, struck


def main():
    text = re.sub(r"\s+", " ", open(PAPER, encoding="utf-8").read())

    cat = load("catalog.csv")
    dates = [r for r in load("delo_dates.csv") if r["year_from"]]
    cls = Counter(r["class"] for r in load("page_classes.csv"))
    cal = load("reading_calibration.csv")
    val = load("calibration_validation.csv")
    ab = load("ab_models.csv")
    files, sheets, marks, struck = corpus()

    checks = [
        ("files in the fond", f"{len(cat):,} files"),
        ("scans", f"{sum(int(r['pages'] or 0) for r in cat):,} scans"),
        ("dated", f"{len(dates):,} of those files"),
        ("conjectural", f"{sum(1 for r in dates if r['conjectural'] == '1')} of the dated"),
        ("handwritten", f"{cls['hand']:,}"),
        ("typewritten", f"{cls['typed']:,}"),
        ("notes", f"{cls['note']:,}"),
        ("corpus", f"{files} files and {sheets:,} scans"),
        ("uncertainty marks", f"{marks:,} uncertainty marks"),
        ("deletions", f"{struck:,} passages struck out"),
    ]
    if cal:
        agree = st.median(float(r["ratio"]) for r in cal)
        run = st.median(int(r["longest_run"]) for r in cal)
        short = sum(1 for r in cal if int(r["longest_run"]) < 10) / len(cal)
        checks += [
            ("calibration pairs", f"{len(cal)} such pairs"),
            ("calibration files", f"{len(cal)} pairs from {len({r['delo'] for r in cal})} files"),
            ("median agreement", f"median {agree*100:.0f}%"),
            ("median longest run", f"median of {run:.0f} words"),
            ("short runs", f"on {short*100:.0f}% of pairs"),
        ]
    if val:
        checks += [("validation pairs", f"Over {len(val)} such pairs")]
    if ab:
        win = sum(1 for r in ab
                  if float(r["agree_strong"]) > float(r["agree_cheap"]))
        checks += [("model test", f"wins on {win} and loses on {len(ab)-win}")]

    # Presence is not enough. A stale figure elsewhere in the text contradicts
    # the right one without ever making it absent, which is exactly how the
    # abstract came to disagree with section 6. So each quantity that has a
    # recognisable phrasing is also required to be stated the same way
    # everywhere it appears.
    contradictions = []
    if cal:
        want = f"{st.median(float(r['ratio']) for r in cal)*100:.0f}"
        found = set(re.findall(r"median (\d+)% of words", text))
        odd = found - {want}
        if odd:
            contradictions.append(
                f"«median N% of words»: сказано {sorted(odd)}, а по данным {want}")
    # "all 2,019 files and 51,008 scans" is the fond, not the corpus; the
    # corpus is always introduced by "currently" or "holds".
    for pat, want in ((r"(?:currently|holds) (\d[\d,]*) (?:archival )?files and [\d,]+ scans",
                       f"{files:,}"),
                      (r"(?:currently|holds) [\d,]+ (?:archival )?files and ([\d,]*) scans",
                       f"{sheets:,}")):
        found = set(re.findall(pat, text))
        odd = found - {want}
        if odd:
            contradictions.append(f"«{pat}»: сказано {sorted(odd)}, а по данным {want}")

    bad = 0
    for label, claim in checks:
        ok = claim.lower() in text.lower()
        bad += 0 if ok else 1
        print(f"  {'OK ' if ok else 'НЕТ'}  {label:<20} «{claim}»")

    print()
    for c in contradictions:
        print(f"  ПРОТИВОРЕЧИЕ  {c}")
    bad += len(contradictions)
    if bad:
        print(f"  расходится: {bad}. Числа в статье устарели или что-то сломалось;")
        print(f"  разобраться нужно вручную, скрипт этого не различает.")
    else:
        print(f"  все {len(checks)} величин совпадают с данными")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
