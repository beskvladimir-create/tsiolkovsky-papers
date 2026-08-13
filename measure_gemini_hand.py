#!/usr/bin/env python3
"""
Чем читать оставшиеся листы: замер моделей Gemini на рукописи.

Эталона расшифровки у фонда нет, поэтому меряем тем же способом, что и
calibrate_reading.py: часть фонда хранит один текст дважды, рукой автора и
машинописной копией. Машинопись наш конвейер читает с точностью 98,1% знаков,
то есть она годится за эталон. Значит, рукописный лист можно дать модели и
сличить её чтение с машинописью того же текста.

Базовая линия считается на тех же листах и тем же кодом: это нынешнее чтение
рукописи конвейером против той же машинописи. Сравнение честное, потому что
меняется только модель, а текст, пара и мерка остаются те же.

Выборка идёт двумя слоями. Пары с высоким согласием это заведомо один и тот же
текст, но и заведомо лёгкий почерк; пары средние ближе к тому, что в фонде
преобладает. Числа печатаются по слоям отдельно, средним по ним смысла нет.

Токены берутся из usageMetadata, поэтому цена замерена, а не оценена.

    python3 measure_gemini_hand.py --models gemini-3.5-flash-lite,gemini-3.6-flash
"""
import argparse
import csv
import difflib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import read_sheets, clean, fold
from transcribe_gemini import load_key, transcribe

ROOT = os.path.dirname(os.path.abspath(__file__))
OPISI = ("opis_1", "opis_1а", "opis_2", "opis_3", "opis_4")
OUT = os.path.join(ROOT, "gemini_hand_measurement.csv")

# Слои выборки: (имя, нижняя граница согласия, верхняя, сколько дел)
STRATA = (("лёгкая", 0.80, 1.01, 6), ("типичная", 0.40, 0.66, 6))


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def agree(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def uncertainty(raw):
    w = len(raw.split())
    if not w:
        return 0.0
    n = raw.count("[?]") + len(re.findall(r"\[неразборчиво", raw))
    return n / w


def locate(delo, sheet):
    for op in OPISI:
        p = os.path.join(ROOT, "data", op, delo, f"{sheet}.jpg")
        if os.path.exists(p):
            return op, p
    return None, None


def sample():
    """Пары рука/машинопись: скан на месте, обе расшифровки на месте."""
    rows = list(csv.DictReader(open(os.path.join(ROOT, "reading_calibration.csv"),
                                    encoding="utf-8")))
    out, seen = [], set()
    for name, lo, hi, want in STRATA:
        n = 0
        for r in rows:
            if n >= want or r["delo"] in seen:
                continue
            ratio = float(r["ratio"])
            if not (lo <= ratio < hi):
                continue
            op, img = locate(r["delo"], r["hand"])
            if not img:
                continue
            md = os.path.join(ROOT, "data", "transcripts", op, r["delo"] + ".md")
            if not os.path.exists(md):
                continue
            sh = read_sheets(md)
            if r["hand"] not in sh or r["typed"] not in sh:
                continue
            seen.add(r["delo"])
            n += 1
            out.append(dict(stratum=name, delo=r["delo"], hand=r["hand"],
                            typed=r["typed"], img=img,
                            ref=toks(sh[r["typed"]]), base_raw=sh[r["hand"]]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemini-3.5-flash-lite,gemini-3.6-flash")
    ap.add_argument("--thinking", default="low",
                    help="уровень размышления для Gemini 3: minimal|low|medium|high")
    ap.add_argument("--jpeg", type=int, default=0,
                    help="пережать скан перед отправкой, качество 1-95")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    key = load_key()
    items = sample()
    print(f"листов в выборке: {len(items)} "
          f"({', '.join(sorted(set(i['stratum'] for i in items)))})\n")

    # прежние замеры не затираем: строки того же прогона заменяем, чужие
    # оставляем, иначе каждая новая модель стирает предыдущую таблицу
    rows = []
    if os.path.exists(OUT):
        rows = [r for r in csv.DictReader(open(OUT, encoding="utf-8"))
                if r["model"] != "конвейер (нынешний)"]
    for it in items:
        base = toks(it["base_raw"])
        rows.append(dict(stratum=it["stratum"], delo=it["delo"], sheet=it["hand"],
                         model="конвейер (нынешний)", agreement=round(agree(base, it["ref"]), 3),
                         words=len(base), words_ref=len(it["ref"]),
                         uncertain=round(uncertainty(it["base_raw"]), 4),
                         tok_in=0, tok_out=0, seconds=0.0))

    for name in args.models.split(","):
        model = name.strip()
        label = f"{model} ({args.thinking})" if model.startswith("gemini-3") else model
        if args.jpeg:
            label += f" q{args.jpeg}"
        rows = [r for r in rows if r["model"] != label]
        print(f"── {label}")
        for it in items:
            t0 = time.time()
            text, ti, to = transcribe(key, model, it["img"], thinking=args.thinking,
                                      quality=args.jpeg or None)
            dt = time.time() - t0
            if text is None:
                print(f"  {it['delo']}/{it['hand']}: ПРОВАЛ")
                continue
            a = agree(toks(text), it["ref"])
            rows.append(dict(stratum=it["stratum"], delo=it["delo"], sheet=it["hand"],
                             model=label, agreement=round(a, 3),
                             words=len(toks(text)), words_ref=len(it["ref"]),
                             uncertain=round(uncertainty(text), 4),
                             tok_in=ti, tok_out=to, seconds=round(dt, 1)))
            probe = os.path.join(ROOT, "data", "gemini_probe", label.replace(" ", "_"))
            os.makedirs(probe, exist_ok=True)
            with open(os.path.join(probe,
                                   f"{it['delo']}_{it['hand']}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(text)
            print(f"  {it['delo']}/{it['hand']} [{it['stratum']}]: "
                  f"согласие {a*100:.0f}%  ({ti}+{to} ток., {dt:.0f} с)")
            time.sleep(args.delay)
        print()

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    med = lambda x: sorted(x)[len(x) // 2] if x else 0
    num = lambda r, k: float(r[k])
    print("согласие с машинописью того же текста, медиана по слоям:\n")
    models = list(dict.fromkeys(r["model"] for r in rows))
    strata = list(dict.fromkeys(r["stratum"] for r in rows))
    print(f"  {'модель':<30}" + "".join(f"{s:>12}" for s in strata) +
          f"{'листов':>8}{'ток.вых/лист':>14}{'с/лист':>9}")
    for m in models:
        mine = [r for r in rows if r["model"] == m]
        line = f"  {m:<30}"
        for s in strata:
            v = [num(r, "agreement") for r in mine if r["stratum"] == s]
            line += f"{med(v)*100:>11.0f}%"
        outs = [num(r, "tok_out") for r in mine]
        secs = [num(r, "seconds") for r in mine]
        line += (f"{len(mine):>8}{sum(outs)/max(len(outs),1):>14.0f}"
                 f"{sum(secs)/max(len(secs),1):>9.1f}")
        print(line)
    print(f"\n  таблица: {os.path.basename(OUT)}")
    print(f"  расшифровки: data/gemini_probe/<модель>/")


if __name__ == "__main__":
    main()
