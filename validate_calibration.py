#!/usr/bin/env python3
"""
Does agreement with a typed copy predict accuracy against a printed edition?

calibrate_reading.py measures how far two readings of one text diverge, using
files that the fond happens to hold twice, as an autograph and as a typed copy.
That measurement is only worth anything if the quantity it produces stands in
for the thing nobody can measure without ground truth: how accurately the
manuscript was read.

This puts that to the test. Three files carry an autograph, a typed copy of the
same text, and a published edition of it, so all three quantities can be had at
once for the same page:

    acc_hand   the autograph reading scored against the printed edition
    acc_typed  the typed reading scored against the same
    agree      the two readings scored against each other, which is what
               calibrate_reading.py has to work with elsewhere

If agree tracks acc_hand, the calibration measures what it claims to. If it
does not, the calibration is a curiosity and the paper says so.

Sheets are paired by content and then located inside the printed text, because
a sheet is an arbitrary cut of a page rather than a unit of the work: the
window of the edition that best matches the typed reading is taken as the
ground truth for that pair. The typed reading is used to find the window, not
the handwritten one, since it is the more reliable of the two and choosing the
window with the weaker reading would bias the result in our favour.

A sheet counts as handwritten only if its transcription is uncertain enough to
have come from a hand, the same filter calibrate_reading.py applies. Two of the
three files here needed it: their sheets carry the image signature of
handwriting while their transcriptions read as clean typescript, page numbers
and all, and pairing typed against typed would have produced 93% agreement and
a validation that validated nothing.

    python3 validate_calibration.py
"""
import csv
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets, clean, fold
from validate import wikisource_text

# file, its published counterpart on Russian Wikisource
CASES = [
    ("data/transcripts/opis_2/delo_0013.md", "Черты из моей жизни (Циолковский)"),
    ("data/transcripts/opis_1/delo_0395.md", "Гений среди людей (Циолковский)"),
    ("data/transcripts/opis_1/delo_0203.md",
     "Дирижабль, стратоплан и звездолёт как три ступени величайших достижений СССР (Циолковский)"),
]

MIN_WORDS = 40
MIN_RATIO = 0.25
MIN_UNCERTAIN = 0.02  # marks of doubt per word, below which a sheet reads as typed


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def uncertainty(raw):
    w = len(raw.split())
    if w < 30:
        return None
    n = raw.count("[?]") + len(re.findall(r"\[неразборчиво", raw))
    return n / w


def page_class():
    cls = {}
    with open("page_classes.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.search(r"(opis_[^/]+)/(delo_\d+[а-яa-z]?)/(\d+)\.jpg", r["path"])
            if m:
                cls[(m.group(2), m.group(3))] = r["class"]
    return cls


def best_window(needle, hay):
    """The stretch of the printed text that best matches a reading.

    Scanning every offset would be needlessly slow, so the search is coarse
    first and then refined around the best coarse position.
    """
    n = len(needle)
    if n < 20 or len(hay) < n:
        return None
    best, at = -1, 0
    step = max(1, n // 6)
    for i in range(0, len(hay) - n + 1, step):
        r = difflib.SequenceMatcher(None, needle, hay[i:i + n],
                                    autojunk=False).quick_ratio()
        if r > best:
            best, at = r, i
    lo = max(0, at - step)
    hi = min(len(hay) - n, at + step)
    best, at = -1, lo
    for i in range(lo, hi + 1, max(1, step // 8)):
        r = difflib.SequenceMatcher(None, needle, hay[i:i + n],
                                    autojunk=False).ratio()
        if r > best:
            best, at = r, i
    return hay[at:at + n]


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def main():
    cls = page_class()
    rows = []
    for path, title in CASES:
        if not os.path.exists(path):
            print(f"  {os.path.basename(path)}: не собрано, пропуск")
            continue
        delo = os.path.basename(path)[:-3]
        sheets = read_sheets(path)
        hand, typed = [], []
        for k, v in sheets.items():
            t = toks(v)
            if len(t) < MIN_WORDS:
                continue
            c = cls.get((delo, k))
            if c == "hand":
                u = uncertainty(v)
                if u is None or u < MIN_UNCERTAIN:
                    continue
                hand.append((k, t))
            elif c == "typed":
                typed.append((k, t))
        if not hand or not typed:
            print(f"  {delo}: нет пары автограф/машинопись "
                  f"({len(hand)} рукописных, {len(typed)} машинописных)")
            continue

        _, pub = wikisource_text(title)
        hay = toks(pub)
        print(f"  {delo}: {len(hand)} рукописных, {len(typed)} машинописных, "
              f"издание {len(hay):,} слов", flush=True)

        for hk, ht in hand:
            best, bt, bk = 0.0, None, None
            for tk, tt in typed:
                r = ratio(ht, tt)
                if r > best:
                    best, bt, bk = r, tt, tk
            if best < MIN_RATIO:
                continue
            window = best_window(bt, hay)
            if window is None:
                continue
            rows.append(dict(delo=delo, hand=hk, typed=bk,
                             words=len(ht),
                             agree=round(best, 3),
                             acc_hand=round(ratio(ht, window), 3),
                             acc_typed=round(ratio(bt, window), 3)))

    if not rows:
        print("\n  пар не набралось: дела ещё не расшифрованы")
        return

    with open("calibration_validation.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    med = lambda x: sorted(x)[len(x) // 2]
    ag = [r["agree"] for r in rows]
    ah = [r["acc_hand"] for r in rows]
    at = [r["acc_typed"] for r in rows]
    print(f"\n  пар: {len(rows)} из {len(set(r['delo'] for r in rows))} дел")
    print(f"  согласие двух прочтений      медиана {med(ag)*100:.0f}%")
    print(f"  точность автографа           медиана {med(ah)*100:.0f}%")
    print(f"  точность машинописи          медиана {med(at)*100:.0f}%")

    # Spearman: does the estimate rank pages the way the truth does?
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    ra, rb = rank(ag), rank(ah)
    n = len(rows)
    if n > 2:
        d2 = sum((ra[i] - rb[i]) ** 2 for i in range(n))
        rho = 1 - 6 * d2 / (n * (n * n - 1))
        print(f"  ранговая связь согласия и точности: rho = {rho:.2f}")
    bias = med([r["acc_hand"] - r["agree"] for r in rows])
    print(f"  систематическое смещение оценки: {bias*100:+.0f} процентных пунктов")
    print(f"\n  таблица: calibration_validation.csv")


if __name__ == "__main__":
    main()
