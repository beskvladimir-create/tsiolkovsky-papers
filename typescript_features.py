#!/usr/bin/env python3
"""
Признаки, различающие машинопись и рукопись.

Регулярность межстрочного шага для этого не годится: аккуратный курсив даёт
такой же ровный шаг, что и печать. Разметка это показала прямо.

Различает другое.

1. ШАГ ЛИТЕР. Пишущая машинка моноширинная: каждый знак встаёт на сетку с
   постоянным шагом. Если взять колоночную проекцию чернил внутри строки и
   посчитать автокорреляцию, у машинописи будет резкий пик на шаге литеры.
   Связный курсив такой сетки не имеет, пик размазан.

2. ДЛИНА СВЯЗНЫХ ШТРИХОВ. В курсиве буквы соединены, и чернильные отрезки
   вдоль строки длинные. В машинописи знаки стоят раздельно, отрезки короткие
   и однородные, а промежутки между ними одинаковые.

3. РОВНОСТЬ ВЫСОТЫ. Печатные знаки сидят в фиксированной строке; у рукописи
   выносные элементы гуляют, и толщина полосы текста меняется от строки к
   строке сильнее.

Ни один признак сам по себе не решает, поэтому считаем все и смотрим вместе.
"""
import numpy as np
from PIL import Image

WIDTH = 1200  # шире, чем в classify_pages: шаг литеры мелкий, его легко потерять


def text_bands(mask, min_h=3):
    proj = mask.mean(axis=1)
    thr = proj.mean() + 0.15 * proj.std() if proj.std() > 0 else 1.0
    on = proj > max(thr, 0.01)
    st, en, prev = [], [], False
    for i, v in enumerate(on):
        if v and not prev:
            st.append(i)
        elif not v and prev:
            en.append(i)
        prev = v
    if prev:
        en.append(len(on))
    return [(s, e) for s, e in zip(st, en) if e - s >= min_h]


def pitch_score(col):
    """Сила периодичности колоночной проекции строки.

    Возвращает (сила пика, шаг в пикселях). Автокорреляция считается на
    центрированном сигнале, ищется максимум в диапазоне шага 4..40 px.
    """
    x = col - col.mean()
    if x.std() < 1e-6 or len(x) < 60:
        return 0.0, 0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    if ac[0] <= 0:
        return 0.0, 0
    ac = ac / ac[0]
    lo, hi = 4, min(40, len(ac) - 1)
    if hi <= lo:
        return 0.0, 0
    seg = ac[lo:hi]
    k = int(np.argmax(seg))
    return float(seg[k]), lo + k


def run_stats(row_mask):
    """Длины чернильных отрезков и промежутков вдоль строки."""
    d = np.diff(row_mask.astype(np.int8))
    starts = np.flatnonzero(d == 1) + 1
    ends = np.flatnonzero(d == -1) + 1
    if row_mask[0]:
        starts = np.r_[0, starts]
    if row_mask[-1]:
        ends = np.r_[ends, len(row_mask)]
    n = min(len(starts), len(ends))
    if n == 0:
        return None
    ink = (ends[:n] - starts[:n]).astype(float)
    gaps = (starts[1:n] - ends[:n - 1]).astype(float) if n > 1 else np.array([])
    return ink, gaps


def features(path):
    try:
        im = Image.open(path).convert("L")
    except Exception:
        return None
    w, h = im.size
    if w != WIDTH:
        im = im.resize((WIDTH, max(1, int(h * WIDTH / w))), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32)
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    if hi - lo < 1e-3:
        return None
    n = np.clip((a - lo) / (hi - lo), 0, 1)
    mask = n < 0.55

    bands = text_bands(mask)
    if len(bands) < 4:
        return None

    pitches, peaks, ink_cv, gap_cv, heights = [], [], [], [], []
    for s, e in bands:
        strip = mask[s:e]
        if strip.shape[0] < 3:
            continue
        col = strip.mean(axis=0)
        pk, pt = pitch_score(col)
        peaks.append(pk)
        pitches.append(pt)
        rs = run_stats(col > col.mean() * 0.6)
        if rs:
            ink, gaps = rs
            if len(ink) >= 4 and ink.mean() > 0:
                ink_cv.append(float(ink.std() / ink.mean()))
            if len(gaps) >= 4 and gaps.mean() > 0:
                gap_cv.append(float(gaps.std() / gaps.mean()))
        heights.append(e - s)

    if not peaks:
        return None
    heights = np.array(heights, dtype=float)
    pit = np.array(pitches, dtype=float)
    pit_valid = pit[pit > 0]

    return {
        # сила периодичности: у машинописи высокая и одинаковая по строкам
        "pitch_peak": round(float(np.median(peaks)), 3),
        # согласие строк о шаге литеры: у машинописи шаг один и тот же
        "pitch_agree": round(float(1.0 - (pit_valid.std() / pit_valid.mean()))
                             if len(pit_valid) >= 3 and pit_valid.mean() > 0 else 0.0, 3),
        # разброс длин чернильных отрезков: у курсива больше (связные штрихи)
        "ink_cv": round(float(np.median(ink_cv)) if ink_cv else 0.0, 3),
        # разброс промежутков между знаками: у машинописи мал
        "gap_cv": round(float(np.median(gap_cv)) if gap_cv else 0.0, 3),
        # ровность высоты полос текста
        "height_cv": round(float(heights.std() / heights.mean())
                           if heights.mean() > 0 else 0.0, 3),
        "bands": len(bands),
    }


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, features(p))
