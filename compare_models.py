#!/usr/bin/env python3
"""
Is the stronger model worth its quota on handwriting?

378 sheets were read twice by different models: once when a faulty classifier
sent them to the wrong one, and again after it was corrected. The earlier
readings were kept in data/transcripts_pass1 precisely so that before and after
could be compared rather than taken on trust.

There is no ground truth for these sheets, but there does not need to be. Where
a sheet has a typed counterpart elsewhere in its file, agreement with that
counterpart estimates the accuracy of reading it, and that estimate has been
validated against printed editions: unbiased to within a percentage point, rank
correlation 0.92 where the edition is a faithful witness (validate_calibration.py).
So the same measure can be turned on the models themselves and asked which of
them reads a hand better.

Where no counterpart exists, a weaker but still useful signal is available: how
much doubt each reading carries, and how much text it produced at all. A model
out of its depth marks more words uncertain and drops more of the page.

    python3 compare_models.py
"""
import csv
import difflib
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets, clean, fold

ROOT = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(ROOT, "data", "transcripts_pass1")
NEW = os.path.join(ROOT, "data", "transcripts_raw")
MIN_WORDS = 40
MIN_RATIO = 0.25
MIN_UNCERTAIN = 0.02


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def uncertainty(raw):
    w = len(raw.split())
    return None if w < 30 else (raw.count("[?]")
                                + len(re.findall(r"\[неразборчиво", raw))) / w


def model_of(path, queue):
    return queue.get(path)


def main():
    # which model read which sheet, from the queue that recorded the re-read
    was = {}
    for name in ("queue_pass1.json", "queue.json"):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        import json
        for it in json.load(open(p, encoding="utf-8"))["items"]:
            was.setdefault(it["path"], {})[name] = it["model"]

    cls = {}
    with open(os.path.join(ROOT, "page_classes.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cls[r["path"].replace("\\", "/")] = r["class"]

    # typed sheets per file, to score a handwritten reading against
    typed = {}
    for p in glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md")):
        delo = os.path.basename(p)[:-3]
        opis = os.path.basename(os.path.dirname(p))
        for k, v in read_sheets(p).items():
            if cls.get(f"data/{opis}/{delo}/{k}.jpg") != "typed":
                continue
            t = toks(v)
            if len(t) >= MIN_WORDS:
                typed.setdefault((opis, delo), []).append(t)

    rows = []
    for op in sorted(glob.glob(os.path.join(OLD, "*", "*", "*.txt"))):
        rel = os.path.relpath(op, OLD)
        np = os.path.join(NEW, rel)
        if not os.path.exists(np):
            continue
        opis, delo, fn = rel.split(os.sep)
        scan = f"data/{opis}/{delo}/{fn[:-4]}.jpg"
        a = open(op, encoding="utf-8").read()
        b = open(np, encoding="utf-8").read()
        ua, ub = uncertainty(a), uncertainty(b)
        if ua is None or ub is None:
            continue
        # Genuine handwriting only, judged by the better of the two readings.
        # Taking either reading would let through a typed sheet that merely
        # defeated the weaker model, and those are the sheets whose agreement
        # with a typed copy comes out at 100%.
        if ub < MIN_UNCERTAIN or cls.get(scan) != "hand":
            continue
        ta, tb = toks(a), toks(b)
        if len(ta) < MIN_WORDS or len(tb) < MIN_WORDS:
            continue
        ref = typed.get((opis, delo), [])
        sa = sb = None
        if ref:
            sa = max(difflib.SequenceMatcher(None, ta, r, autojunk=False).ratio()
                     for r in ref)
            sb = max(difflib.SequenceMatcher(None, tb, r, autojunk=False).ratio()
                     for r in ref)
            if max(sa, sb) < MIN_RATIO or max(sa, sb) > 0.98:
                # above 0.98 the "pair" is one page scanned twice, not a
                # manuscript and its typed copy
                sa = sb = None
        m = was.get(scan, {})
        rows.append(dict(scan=scan,
                         model_old=m.get("queue_pass1.json", "?"),
                         model_new=m.get("queue.json", "?"),
                         words_old=len(ta), words_new=len(tb),
                         unc_old=round(ua, 4), unc_new=round(ub, 4),
                         agree_old=None if sa is None else round(sa, 3),
                         agree_new=None if sb is None else round(sb, 3)))

    if not rows:
        print("нечего сравнивать")
        return
    med = lambda x: sorted(x)[len(x) // 2]
    print(f"  листов прочитано дважды, из них рукописных: {len(rows)}")
    pairs = [(r["model_old"], r["model_new"]) for r in rows]
    import collections
    for k, v in collections.Counter(pairs).most_common():
        print(f"    {k[0]} -> {k[1]}: {v}")

    print(f"\n  пометок неуверенности на слово:")
    print(f"    прежнее чтение {med([r['unc_old'] for r in rows]):.3f}"
          f"    новое {med([r['unc_new'] for r in rows]):.3f}")
    print(f"  слов извлечено с листа:")
    print(f"    прежнее {med([r['words_old'] for r in rows])}"
          f"    новое {med([r['words_new'] for r in rows])}")

    g = [r for r in rows if r["agree_old"] is not None]
    if g:
        print(f"\n  согласие с машинописной копией того же текста ({len(g)} листов):")
        print(f"    прежнее чтение {med([r['agree_old'] for r in g])*100:.0f}%"
              f"    новое {med([r['agree_new'] for r in g])*100:.0f}%")
        better = sum(1 for r in g if r["agree_new"] > r["agree_old"])
        print(f"    новое лучше на {better} листах из {len(g)} "
              f"({better/len(g)*100:.0f}%)")
        d = med([r["agree_new"] - r["agree_old"] for r in g])
        print(f"    медиана прибавки: {d*100:+.0f} процентных пункта")
    else:
        print("\n  машинописной пары для этих листов нет: "
              "сравнение только по косвенным признакам")

    with open("model_comparison.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n  таблица: model_comparison.csv")


if __name__ == "__main__":
    main()
