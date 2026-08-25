#!/usr/bin/env python3
"""
Сборка корпуса в формат, который Hugging Face грузит одной строкой.

На Zenodo корпус лежит так, как он живёт в проекте: markdown на дело, с
разметкой листов. Для архивиста это правильно, для машинного обучения — нет.
Исследователь, которому нужен корпус, ждёт `load_dataset(...)` и колонки, а не
папку markdown, которую надо разбирать самому. Большинство таких закрывает
вкладку.

Поэтому здесь тот же корпус разворачивается в JSONL: строка на лист, поля
готовы к обучению и оценке. Parquet был бы плотнее, но требует pyarrow, а
JSONL с gzip грузится тем же `load_dataset` и не тянет зависимостей.

Каноническим хранилищем остаётся Zenodo с DOI; это витрина.

    python3 build_hf_dataset.py
"""
import csv
import glob
import gzip
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "hf")
BASE = "https://www.ras.ru/ktsiolkovskyarchive"

SHEET = re.compile(r"^## Лист (\S+)\s*$", re.M)
MARK = re.compile(r"\[неразборчиво")


def page_classes():
    cls = {}
    p = os.path.join(ROOT, "page_classes.csv")
    for r in csv.DictReader(open(p, encoding="utf-8")):
        m = re.search(r"(opis_[^/]+)/(delo_[^/]+)/0*(\d+)\.jpg", r["path"])
        if m:
            cls[(m.group(1), m.group(2), m.group(3))] = r["class"]
    return cls


def catalogue():
    out = {}
    for r in csv.DictReader(open(os.path.join(ROOT, "catalog.csv"), encoding="utf-8")):
        name = re.sub(r"\s+", " ", r["name"]).strip()
        title = re.search(r'"([^"]+)"', name)
        out[(f"opis_{r['opis_code']}", f"delo_{r['delo']}")] = dict(
            title=title.group(1) if title else name,
            description=name, portal_id=r.get("portal_id", ""))
    return out


def dates():
    out = {}
    for r in csv.DictReader(open(os.path.join(ROOT, "delo_dates.csv"), encoding="utf-8")):
        out[(f"opis_{r['opis_code']}", f"delo_{r['delo']}")] = dict(
            year_from=int(r["year_from"]) if r["year_from"].isdigit() else None,
            year_to=int(r["year_to"]) if r["year_to"].isdigit() else None,
            conjectural=r["conjectural"] == "1")
    return out


def main():
    cls, cat, dts = page_classes(), catalogue(), dates()
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "corpus.jsonl.gz")
    n = skipped = 0
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for md in sorted(glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md"))):
            opis = os.path.basename(os.path.dirname(md))
            delo = os.path.basename(md)[:-3]
            raw = open(md, encoding="utf-8").read()
            parts = SHEET.split(raw)
            meta = cat.get((opis, delo), {})
            dd = dts.get((opis, delo), {})
            for i in range(1, len(parts) - 1, 2):
                sheet, text = parts[i], parts[i + 1].strip()
                if not text:
                    skipped += 1
                    continue
                key = (opis, delo, str(int(sheet)) if sheet.isdigit() else sheet)
                words = text.split()
                rec = {
                    "id": f"{opis}/{delo}/{sheet}",
                    "opis": opis.replace("opis_", ""),
                    "delo": delo.replace("delo_", ""),
                    "sheet": sheet,
                    "text": text,
                    "page_type": cls.get(key),
                    "words": len(words),
                    "chars": len(text),
                    # разметка неуверенности — то, ради чего корпус и годится
                    # для оценки чтения: места сомнения не спрятаны
                    "uncertain_marks": text.count("[?]") + len(MARK.findall(text)),
                    "struck_out": len(re.findall(r"~~.+?~~", text)),
                    "title": meta.get("title"),
                    "year_from": dd.get("year_from"),
                    "year_to": dd.get("year_to"),
                    "date_conjectural": dd.get("conjectural"),
                    "scan_url": (f"{BASE}/{opis.replace('opis_','')}_actview.aspx"
                                 f"?id={meta.get('portal_id','')}"),
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    size = os.path.getsize(path)
    print(f"  {os.path.relpath(path, ROOT)}")
    print(f"  строк (листов): {n:,}, пустых пропущено: {skipped}")
    print(f"  размер: {size/1e6:.1f} МБ в gzip")


if __name__ == "__main__":
    main()
