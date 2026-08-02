#!/usr/bin/env python3
"""
Пересчёт классов листов проверенным признаком.

classify_pages.py делил по ровности межстрочного шага. Разметка показала, что
признак негоден: аккуратный курсив так же ровен, как печать, а машинопись с
абзацными отступами выглядит неровной. Ошибка была не мелкой — доля печати в
фонде оказалась занижена почти втрое.

Здесь используется ink_cv из typescript_features: разброс длин чернильных
отрезков вдоль строки. Порог 0.81 проверен на labelled_pages.csv, 19 из 19.

Пишет page_classes.csv: путь, класс, ink_cv.
"""
import csv, os, sys
from typescript_features import features

ROOT = os.path.dirname(os.path.abspath(__file__))
THR = 0.81

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
                cls, cv = "note", ""
            else:
                cls = "typed" if f["ink_cv"] < THR else "hand"
                cv = f["ink_cv"]
            n[cls] += 1
            w.writerow([os.path.relpath(p, ROOT), cls, cv])
            if i % 2000 == 0:
                print(f"  {i}/{len(paths)}", flush=True)
    tot = sum(n.values())
    print(f"\n  готово: {tot:,} сканов -> {out}")
    for k, v in n.items():
        print(f"    {k:<6} {v:>6}  {v/tot*100:>5.1f}%")

if __name__ == "__main__":
    main()
