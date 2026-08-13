#!/usr/bin/env python3
"""
Свёртка зацикленных строк в расшифровках.

На 59 листах из 51 008 модель зациклилась и повторила одну и ту же строку
разметки сотни раз подряд: на листе 010 дела 47 четвёртой описи —
«[вставка: [неразборчиво]]» 282 раза, на листе 551 дела 144 первой описи —
635 раз. Повторяется всегда пометка, а не текст, так что содержание не
выдумано; но каждый повтор считается как пометка неуверенности, и в
опубликованном числе 310 166 таких набралось 5 766, то есть 1,9%.

Свёрнутый повтор заменяется одной строкой и пометкой о том, сколько строк
свёрнуто. Молча выбрасывать нельзя: лист, где модель сорвалась, должен об этом
говорить, иначе через месяц никто не отличит артефакт от чтения.

Порог в три повтора подряд: две одинаковые строки на листе бывают по делу
(две пустые пометки на полях), три сотни — никогда.

    python3 fix_loops.py --dry     # посмотреть, ничего не меняя
    python3 fix_loops.py
"""
import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "transcripts_raw")
MIN_RUN = 3


def fold(lines):
    """Возвращает (новые строки, сколько строк свёрнуто)."""
    out, i, dropped = [], 0, 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1] == lines[i] and lines[i].strip():
            j += 1
        run = j - i + 1
        out.append(lines[i])
        if run >= MIN_RUN:
            out.append(f"[повтор свёрнут: та же строка ещё {run - 1} раз]")
            dropped += run - 1
        else:
            out.extend(lines[i + 1:j + 1])
        i = j + 1
    return out, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(RAW, "**", "*.txt"), recursive=True))
    touched = total = marks = 0
    for path in files:
        lines = open(path, encoding="utf-8").read().split("\n")
        new, dropped = fold(lines)
        if not dropped:
            continue
        touched += 1
        total += dropped
        marks += sum(l.count("[?]") + len(re.findall(r"\[неразборчиво", l))
                     for l in lines) - sum(
                     l.count("[?]") + len(re.findall(r"\[неразборчиво", l))
                     for l in new)
        rel = path.split("transcripts_raw/")[-1]
        print(f"  {rel:<36} свёрнуто {dropped}")
        if not args.dry:
            open(path, "w", encoding="utf-8").write("\n".join(new))

    print(f"\nлистов затронуто: {touched} из {len(files)}")
    print(f"строк свёрнуто: {total:,}")
    print(f"пометок неуверенности убыло: {marks:,}")
    if args.dry:
        print("\n(ничего не записано, это --dry)")
    else:
        print("\nдальше: python3 assemble.py — пересобрать дела")


if __name__ == "__main__":
    main()
