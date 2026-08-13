#!/usr/bin/env python3
"""
Проверка того, что реально записал пакетный прогон.

Замер на выборке из двенадцати листов говорил, чего ждать. Этот скрипт
смотрит, что вышло на самом деле, и меряет тем же способом, что
calibrate_reading.py: внутри дела ищет для рукописного листа машинописный
двойник по содержанию и считает согласие двух чтений одного текста. Числа
сопоставимы со старым корпусом (reading_calibration.csv), потому что мерка,
код и материал те же.

Отдельно ищет брак, которого замер на двенадцати листах увидеть не мог:
пустые ответы, отговорки вместо текста, обрывы на полуслове.

    python3 check_batch_quality.py
"""
import collections
import csv
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_variants import clean, fold

ROOT = os.path.dirname(os.path.abspath(__file__))
MIN_WORDS = 40
MIN_RATIO = 0.25
MIN_UNCERTAIN = 0.02

# Ответ, начинающийся так, спецификация считает неверным: модель вместо
# листа пересказывает, что она видит.
EXCUSE = re.compile(r"^\s*(вот текст|на этом листе|этот лист|я не могу|извин|к сожал)", re.I)


def toks(t):
    return [w for w in (fold(x).strip() for x in clean(t).split()) if w]


def uncertainty(raw):
    w = len(raw.split())
    return None if w < 30 else (raw.count("[?]") + len(re.findall(r"\[неразборчиво", raw))) / w


def main():
    st = json.load(open(os.path.join(ROOT, "batch_state.json"), encoding="utf-8"))
    q = json.load(open(os.path.join(ROOT, "queue.json"), encoding="utf-8"))
    keys = [int(k) for j in st["jobs"] for k in j["keys"]]

    sheets, missing = [], 0
    for i in keys:
        it = q["items"][i]
        p = os.path.join(ROOT, "data", "transcripts_raw", it["opis"], it["delo"],
                         it["page"].replace(".jpg", ".txt"))
        if not os.path.exists(p):
            missing += 1
            continue
        sheets.append((it, open(p, encoding="utf-8").read()))
    print(f"листов записано: {len(sheets)}, не найдено на диске: {missing}\n")

    # брак
    empty = [it for it, t in sheets if not t.strip()]
    declared = [it for it, t in sheets if t.strip() == "[пустой лист]"]
    excuses = [it for it, t in sheets if EXCUSE.match(t)]
    # Лист, кончающийся не знаком препинания. Само по себе это не брак:
    # фраза переходит на следующий лист, и у старого корпуса, читанного
    # подпиской, доля такая же (35% против 38%). Признаком обрыва ответа
    # служит finishReason=MAX_TOKENS, его ловит batch_run.py при разборе.
    cut = [it for it, t in sheets
           if len(t.split()) > 60 and t.rstrip() and t.rstrip()[-1] not in ".!?]»\"'-–—:;,"]
    long_ = sum(1 for _, t in sheets if len(t.split()) > 60)
    print(f"  пустой файл           {len(empty)}")
    print(f"  ответ «пустой лист»   {len(declared)}")
    print(f"  отговорка вместо      {len(excuses)}")
    print(f"  без знака в конце     {len(cut)} из {long_} "
          f"({len(cut)/max(long_,1)*100:.0f}%, у старого корпуса 35%)")
    if excuses[:3]:
        for it in excuses[:3]:
            print(f"    напр. {it['opis']}/{it['delo']}/{it['page']}")

    # объём и сомнения по типу листа
    print()
    by = collections.defaultdict(list)
    for it, t in sheets:
        by[it["class"]].append((len(t.split()), uncertainty(t)))
    for cls, v in sorted(by.items()):
        ws = sorted(x[0] for x in v)
        us = sorted(x[1] for x in v if x[1] is not None)
        print(f"  {cls:<6} листов {len(v):>5}  слов медиана {ws[len(ws)//2]:>4}  "
              f"пометок сомнения на 100 слов {us[len(us)//2]*100:>4.1f}")

    # согласие рукописи с машинописью того же текста, внутри дела
    per_delo = collections.defaultdict(lambda: {"hand": [], "typed": []})
    for it, t in sheets:
        w = toks(t)
        if len(w) < MIN_WORDS:
            continue
        if it["class"] == "hand":
            u = uncertainty(t)
            if u is None or u < MIN_UNCERTAIN:
                continue        # читается как машинопись, что бы ни говорил классификатор
            per_delo[(it["opis"], it["delo"])]["hand"].append((it["page"], w))
        elif it["class"] == "typed":
            per_delo[(it["opis"], it["delo"])]["typed"].append((it["page"], w))

    pairs = []
    for (op, delo), d in per_delo.items():
        for hk, ht in d["hand"]:
            best, bt, bk = 0.0, None, None
            for tk, tt in d["typed"]:
                m = difflib.SequenceMatcher(None, ht, tt, autojunk=False)
                if m.quick_ratio() <= best:
                    continue
                r = m.ratio()
                if r > best:
                    best, bt, bk = r, tt, tk
            if best >= MIN_RATIO:
                m = difflib.SequenceMatcher(None, ht, bt, autojunk=False)
                blocks = [b.size for b in m.get_matching_blocks() if b.size]
                pairs.append((delo, hk, bk, best, max(blocks) if blocks else 0))

    print()
    if not pairs:
        print("  пар рука/машинопись среди прочитанного не нашлось:")
        print("  сравнить новое чтение с эталоном на этих листах нельзя")
        return
    rs = sorted(p[3] for p in pairs)
    ls = sorted(p[4] for p in pairs)
    med = lambda x: x[len(x) // 2]
    print(f"  пар рука/машинопись одного текста: {len(pairs)} "
          f"из {len(set(p[0] for p in pairs))} дел")
    print(f"  согласие двух чтений: медиана {med(rs)*100:.0f}%  "
          f"лучшее {max(rs)*100:.0f}%  худшее {min(rs)*100:.0f}%")
    print(f"  длина совпадающего куска, слов: медиана {med(ls)}")

    old = [float(r["ratio"]) for r in
           csv.DictReader(open(os.path.join(ROOT, "reading_calibration.csv"),
                               encoding="utf-8"))]
    old.sort()
    print(f"\n  для сравнения, старый корпус (подписка, 294 пары): "
          f"медиана {med(old)*100:.0f}%")


if __name__ == "__main__":
    main()
