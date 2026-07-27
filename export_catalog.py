#!/usr/bin/env python3
"""
Экспорт каталога фонда 555 в JSON и сборка приоритетного списка дел.

catalog.csv пишется скачивателем построчно и содержит сырые поля со страницы
РАН. Здесь мы его разбираем: вытаскиваем из слитного «Название» отдельные
поля (вид материала, способ воспроизведения, крайние даты), проставляем
ссылку на страницу дела и отдаём машиночитаемый JSON.

Приоритет: дела ракетно-космической тематики, ради которых проект и делается.
Отбор по ключевым словам в названии, чтобы список пересобирался сам при
появлении описей 2-5, а не правился руками.
"""
import csv
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(ROOT, "catalog.csv")
BASE = "https://www.ras.ru/ktsiolkovskyarchive"

# ракетно-космическое ядро фонда
PRIORITY_RE = re.compile(
    r"реактивн|ракет|космическ|звездоплав|мировых\s+пространств|"
    r"небесных\s+пространств|вне\s+земли|эфирн|межпланетн|"
    r"заатмосферн|тяготени|скорост",
    re.I,
)


def split_name(raw):
    """Из слитной строки достаёт заголовок и служебные поля."""
    s = re.sub(r"\s+", " ", raw or "").strip()
    out = {"title": s, "material": "", "reproduction": "", "dates": ""}
    for key, pat in (
        ("material", r"Вид материала:\s*(.+?)(?=Способ воспроизведения:|Крайние даты:|$)"),
        ("reproduction", r"Способ воспроизведения:\s*(.+?)(?=Вид материала:|Крайние даты:|$)"),
        ("dates", r"Крайние даты:\s*(.+?)(?=Вид материала:|Способ воспроизведения:|$)"),
    ):
        m = re.search(pat, s, re.I)
        if m:
            out[key] = m.group(1).strip(" .;")
    # заголовок = всё до первого служебного поля
    cut = re.split(r"Вид материала:|Способ воспроизведения:|Крайние даты:", s, maxsplit=1)[0]
    out["title"] = cut.strip(" .;")
    return out


def load():
    rows = []
    with open(CATALOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                opis, delo = int(r["opis_page"]), int(r["delo"])
            except (ValueError, KeyError):
                continue
            parts = split_name(r.get("name", ""))
            rows.append({
                "opis": r.get("opis", ""),
                "opis_page": opis,
                "delo": delo,
                **parts,
                "pages_downloaded": int(r.get("pages") or 0),
                "pages_expected": int(r.get("expected") or 0),
                "status": r.get("status", ""),
                "source_url": f"{BASE}/{opis}_actview.aspx?id={delo}",
            })
    # на всякий случай схлопываем дубли: оставляем строку с большим числом листов
    best = {}
    for r in rows:
        k = (r["opis_page"], r["delo"])
        if k not in best or r["pages_downloaded"] > best[k]["pages_downloaded"]:
            best[k] = r
    return [best[k] for k in sorted(best)]


def main():
    rows = load()

    with open(os.path.join(ROOT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump({
            "fond": "555",
            "archive": "Архив Российской академии наук (Archive of the Russian Academy of Sciences)",
            "person": "Циолковский Константин Эдуардович (Konstantin E. Tsiolkovsky)",
            "source": BASE,
            "files_listed": len(rows),
            "pages_downloaded": sum(r["pages_downloaded"] for r in rows),
            "pages_expected": sum(r["pages_expected"] for r in rows),
            "files": rows,
        }, f, ensure_ascii=False, indent=1)

    prio = [r for r in rows if PRIORITY_RE.search(r["title"])]
    prio.sort(key=lambda r: -r["pages_expected"])
    with open(os.path.join(ROOT, "priority.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["opis_page", "delo", "pages_expected",
                                          "status", "title", "source_url"])
        w.writeheader()
        for r in prio:
            w.writerow({k: r[k] for k in w.fieldnames})

    print(f"catalog.json: {len(rows)} дел, "
          f"{sum(r['pages_downloaded'] for r in rows)} из "
          f"{sum(r['pages_expected'] for r in rows)} листов скачано")
    print(f"priority.csv: {len(prio)} дел, "
          f"{sum(r['pages_expected'] for r in prio)} листов")
    print("\nприоритет, топ-15:")
    for r in prio[:15]:
        print(f"  д.{r['delo']:>4} {r['pages_expected']:>4} л.  {r['title'][:72]}")


if __name__ == "__main__":
    main()
