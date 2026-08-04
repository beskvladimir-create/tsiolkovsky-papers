#!/usr/bin/env python3
"""
Does the stronger model actually read this hand better?

Two thirds of the fond's sheets are routed to the expensive model because the
pipeline assumes it reads handwriting better. That assumption was never
measured. It was written into a comment, and the routing has followed it ever
since; what was measured, at 98.2% against 98.1%, was typescript, where the two
models are level.

Comparing the readings kept from an earlier pass suggested no difference at all
on handwriting, but on nine sheets, which settles nothing. This runs the test
properly: sheets that are unambiguously handwritten and have a typed copy of
the same text elsewhere in their file are read again by the cheaper model, and
both readings are scored against that copy. Scoring against a typed copy is the
measure validated in validate_calibration.py, unbiased to within a percentage
point against printed editions.

The expensive readings already exist, so the test costs one pass of the cheap
model over a sample, and nothing else. If the two come out level, the remaining
46,000 sheets of the fond can be read at a fraction of the quota.

The prompt, the batching and the specification are exactly those of the nightly
run, because a difference in any of them would be measured as a difference
between the models.

    python3 ab_models.py --sample 60     read the sample with the cheap model
    python3 ab_models.py --report        score both readings
"""
import argparse
import csv
import difflib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets, clean, fold

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "transcripts_ab")
RAW = os.path.join(ROOT, "data", "transcripts_raw")
SPEC = os.path.join(ROOT, "TRANSCRIPTION_SPEC.md")
CHEAP = "sonnet"
BATCH = 4


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def sample(n):
    """Handwritten sheets that have a typed copy, spread across files.

    Taken round robin rather than in order, so that one long file cannot
    supply the whole sample and turn the test into a test of one hand.
    """
    rows = list(csv.DictReader(open(os.path.join(ROOT, "reading_calibration.csv"),
                                    encoding="utf-8")))
    by = {}
    for r in rows:
        by.setdefault(r["delo"], []).append(r)
    for v in by.values():
        v.sort(key=lambda r: r["hand"])
    out, i = [], 0
    while len(out) < n and any(len(v) > i for v in by.values()):
        for d in sorted(by):
            if len(by[d]) > i and len(out) < n:
                out.append(by[d][i])
        i += 1
    return out


def opis_of(delo):
    for o in ("opis_1", "opis_1а", "opis_2", "opis_3", "opis_4"):
        if os.path.isdir(os.path.join(ROOT, "data", o, delo)):
            return o
    return None


def read_batch(paths):
    spec = open(SPEC, encoding="utf-8").read()
    listing = "\n".join(os.path.join(ROOT, p) for p in paths)
    prompt = f"""Ты транскрибируешь сканы рукописей К.Э. Циолковского из фонда 555 Архива РАН.

СПЕЦИФИКАЦИЯ (следуй буквально):
{spec}

Прочитай инструментом Read эти сканы по порядку:
{listing}

Твой финальный ответ это и есть результат. Верни ТОЛЬКО транскрипции,
разделённые строкой-маркером вида === ИМЯ_ФАЙЛА === перед каждым листом,
например === 003.jpg ===. Никакого вступления и никаких выводов."""
    p = subprocess.run(["claude", "-p", "--model", CHEAP, "--allowedTools", "Read"],
                       input=prompt, text=True, capture_output=True, timeout=1800)
    out = p.stdout
    if re.search(r"session limit|rate.?limit|usage limit|exceeded your", out, re.I):
        raise SystemExit("subscription limit reached, stopping cleanly")
    parts = re.split(r"^===\s*(\S+?\.jpg)\s*===\s*$", out, flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def do_sample(n):
    todo = []
    for r in sample(n):
        o = opis_of(r["delo"])
        if not o:
            continue
        dst = os.path.join(OUT, o, r["delo"], f"{r['hand']}.txt")
        if os.path.exists(dst):
            continue
        todo.append((f"data/{o}/{r['delo']}/{r['hand']}.jpg", dst))
    print(f"  to read with {CHEAP}: {len(todo)}", flush=True)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        got = read_batch([p for p, _ in chunk])
        for p, dst in chunk:
            name = os.path.basename(p)
            if name not in got:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(got[name])
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)


def report():
    cal = {(r["delo"], r["hand"]): r for r in csv.DictReader(
        open(os.path.join(ROOT, "reading_calibration.csv"), encoding="utf-8"))}
    typed = {}
    for p in sorted(os.listdir(os.path.join(ROOT, "data", "transcripts"))):
        d = os.path.join(ROOT, "data", "transcripts", p)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".md"):
                continue
            sh = read_sheets(os.path.join(d, f))
            typed[f[:-3]] = sh

    rows = []
    for o in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
        for delo in sorted(os.listdir(os.path.join(OUT, o))):
            for fn in sorted(os.listdir(os.path.join(OUT, o, delo))):
                sheet = fn[:-4]
                c = cal.get((delo, sheet))
                if not c:
                    continue
                cheap = open(os.path.join(OUT, o, delo, fn), encoding="utf-8").read()
                strong_p = os.path.join(RAW, o, delo, fn)
                if not os.path.exists(strong_p):
                    continue
                strong = open(strong_p, encoding="utf-8").read()
                sh = typed.get(delo, {})
                ref = sh.get(c["typed"])
                if not ref:
                    continue
                rt = toks(ref)
                a = difflib.SequenceMatcher(None, toks(cheap), rt, autojunk=False).ratio()
                b = difflib.SequenceMatcher(None, toks(strong), rt, autojunk=False).ratio()
                rows.append(dict(delo=delo, sheet=sheet,
                                 agree_cheap=round(a, 3), agree_strong=round(b, 3),
                                 words_cheap=len(toks(cheap)),
                                 words_strong=len(toks(strong))))
    if not rows:
        print("  нечего сравнивать: сначала --sample")
        return
    med = lambda x: sorted(x)[len(x) // 2]
    a = [r["agree_cheap"] for r in rows]
    b = [r["agree_strong"] for r in rows]
    win = sum(1 for r in rows if r["agree_strong"] > r["agree_cheap"])
    print(f"  листов: {len(rows)} из {len({r['delo'] for r in rows})} дел")
    print(f"  согласие с машинописной копией:")
    print(f"    {CHEAP:<8} {med(a)*100:.0f}%")
    print(f"    opus     {med(b)*100:.0f}%")
    print(f"  дорогая модель лучше на {win} листах из {len(rows)} "
          f"({win/len(rows)*100:.0f}%)")
    print(f"  медиана разницы: {med([r['agree_strong']-r['agree_cheap'] for r in rows])*100:+.1f} "
          f"процентного пункта")
    with open(os.path.join(ROOT, "ab_models.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  таблица: ab_models.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.sample:
        do_sample(args.sample)
    if args.report or not args.sample:
        report()


if __name__ == "__main__":
    main()
