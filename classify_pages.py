#!/usr/bin/env python3
"""
Быстрая классификация сканов без нейросети: PIL + numpy, миллисекунды на лист.

Идея: печать и рукопись различаются регулярностью строк. У печатного текста
базовые линии идут с почти постоянным шагом и одинаковой толщиной штриха,
у рукописи шаг и плотность гуляют. Пустые листы отсекаются по доле чернил.

Считает по каждому листу:
  ink      доля тёмных пикселей после нормализации контраста
  lines    число текстовых строк (по горизонтальной проекции)
  regular  регулярность шага строк, 1 = идеально ровный (печать)
  contrast разброс яркости, низкий = выцветший лист

Выход: CSV, дальше решаем порог по глазам на выборке.
"""
import csv
import os
import sys
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
WIDTH = 900  # до этой ширины ужимаем перед анализом, деталей хватает


def metrics(path):
    try:
        im = Image.open(path).convert("L")
    except Exception:
        return None
    w, h = im.size
    if w > WIDTH:
        im = im.resize((WIDTH, int(h * WIDTH / w)), Image.BILINEAR)
    a = np.asarray(im, dtype=np.float32)

    # нормализация контраста по перцентилям: гасит разницу в освещении сканов
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    contrast = float(hi - lo)
    if hi - lo < 1e-3:
        return dict(ink=0.0, lines=0, regular=0.0, contrast=contrast)
    n = np.clip((a - lo) / (hi - lo), 0, 1)

    ink_mask = n < 0.55
    ink = float(ink_mask.mean())

    # горизонтальная проекция: сколько чернил в каждой строке пикселей
    proj = ink_mask.mean(axis=1)
    thr = proj.mean() + 0.15 * proj.std() if proj.std() > 0 else 1.0
    on = proj > max(thr, 0.01)

    # границы полос текста
    starts, ends = [], []
    prev = False
    for i, v in enumerate(on):
        if v and not prev:
            starts.append(i)
        elif not v and prev:
            ends.append(i)
        prev = v
    if prev:
        ends.append(len(on))
    bands = [(s, e) for s, e in zip(starts, ends) if e - s >= 3]

    lines = len(bands)
    if lines >= 4:
        centers = np.array([(s + e) / 2 for s, e in bands])
        gaps = np.diff(centers)
        # коэффициент вариации шага: у печати мал, у рукописи велик
        cv = float(gaps.std() / gaps.mean()) if gaps.mean() > 0 else 1.0
        regular = float(max(0.0, 1.0 - cv))
    else:
        regular = 0.0

    return dict(ink=round(ink, 4), lines=lines,
                regular=round(regular, 3), contrast=round(contrast, 1))


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    files = []
    for opis in sorted(os.listdir(DATA)):
        d = os.path.join(DATA, opis)
        if not os.path.isdir(d) or not opis.startswith("opis_"):
            continue
        for delo in sorted(os.listdir(d)):
            dd = os.path.join(d, delo)
            if not os.path.isdir(dd):
                continue
            for page in sorted(os.listdir(dd)):
                if page.endswith(".jpg"):
                    files.append((opis, delo, page, os.path.join(dd, page)))

    if limit and len(files) > limit:
        rng = np.random.default_rng(42)  # фиксированное зерно: выборка воспроизводима
        idx = rng.choice(len(files), limit, replace=False)
        files = [files[i] for i in sorted(idx)]

    out = os.path.join(ROOT, "page_metrics.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["opis", "delo", "page", "ink", "lines",
                                          "regular", "contrast"])
        w.writeheader()
        for i, (opis, delo, page, path) in enumerate(files, 1):
            m = metrics(path)
            if m is None:
                continue
            w.writerow(dict(opis=opis, delo=delo, page=page, **m))
            if i % 500 == 0:
                print(f"  {i}/{len(files)}", flush=True)
    print(f"готово: {len(files)} листов -> {out}")


if __name__ == "__main__":
    main()
