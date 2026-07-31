#!/usr/bin/env python3
"""
Сборка очереди транскрипции по приоритетным делам.

Каждый скан получает модель по своему типу, который уже посчитан
classify_pages.py:
  ровные строки + много строк  -> машинопись -> sonnet (замерено 98.2%,
                                  на уровне opus, но дешевле по квоте)
  мало строк                   -> помета или обложка -> sonnet, выход крошечный
  остальное                    -> рукопись -> opus (на почерке заметно точнее)

Состояние держим в queue.json: каждый скан либо pending, либо done, либо
failed. Прогон можно оборвать в любой момент, потеряется максимум одна пачка.

    python3 build_queue.py            собрать заново
    python3 build_queue.py --status   что осталось
"""
import argparse
import csv
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue.json")
BATCH = 4  # сканов на один вызов: при 1 накладные расходы съедают всё,
           # при 6+ растёт контекст внутри вызова


def page_class(m):
    lines, reg = int(m["lines"]), float(m["regular"])
    if lines <= 3:
        return "note"
    if reg > 0.80 and lines >= 10:
        return "typed"
    return "hand"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        if not os.path.exists(QUEUE):
            raise SystemExit("очереди нет, соберите без --status")
        q = json.load(open(QUEUE, encoding="utf-8"))
        items = q["items"]
        by = {}
        for it in items:
            by[it["status"]] = by.get(it["status"], 0) + 1
        done = by.get("done", 0)
        print(f"  сканов в очереди: {len(items)}")
        for k in ("done", "pending", "failed"):
            if by.get(k):
                print(f"    {k:<8} {by[k]}")
        print(f"  готово: {done/len(items)*100:.1f}%")
        left = [i for i in items if i["status"] == "pending"]
        if left:
            d = left[0]
            print(f"  следующее: {d['opis']}/{d['delo']} лист {d['page']} ({d['model']})")
        return

    metrics = {}
    with open(os.path.join(ROOT, "page_metrics.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            metrics[(r["opis"], r["delo"], r["page"])] = r

    # приоритет: порядок как в priority.csv, он уже отсортирован по объёму
    prio = list(csv.DictReader(open(os.path.join(ROOT, "priority.csv"), encoding="utf-8")))
    cat = {(r["opis"], r["delo"]): r
           for r in csv.DictReader(open(os.path.join(ROOT, "catalog.csv"), encoding="utf-8"))}

    items = []
    for p in prio:
        row = None
        for (o, d), r in cat.items():
            if r["opis"] == p["opis"] and r["delo"].lstrip("0") == p["delo"]:
                row = r
                break
        if not row:
            continue
        opis_dir = f"opis_{row['opis_code']}"
        delo_dir = f"delo_{row['delo']}"
        d = os.path.join(ROOT, "data", opis_dir, delo_dir)
        if not os.path.isdir(d):
            continue
        for page in sorted(x for x in os.listdir(d) if x.endswith(".jpg")):
            m = metrics.get((opis_dir, delo_dir, page))
            cls = page_class(m) if m else "hand"
            items.append({
                "opis": opis_dir, "delo": delo_dir, "page": page,
                "path": os.path.join("data", opis_dir, delo_dir, page),
                "class": cls,
                "model": "opus" if cls == "hand" else "sonnet",
                "status": "pending",
            })

    json.dump({"batch": BATCH, "items": items},
              open(QUEUE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by_cls, by_model = {}, {}
    for it in items:
        by_cls[it["class"]] = by_cls.get(it["class"], 0) + 1
        by_model[it["model"]] = by_model.get(it["model"], 0) + 1
    print(f"  очередь: {len(items)} сканов из {len(prio)} дел")
    print(f"  по типу : {by_cls}")
    print(f"  по модели: {by_model}")


if __name__ == "__main__":
    main()
