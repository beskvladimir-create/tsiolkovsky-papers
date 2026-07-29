#!/usr/bin/env python3
"""
Переразметка уже скачанного под настоящую структуру фонда.

До 29.07.2026 мы считали, что номер описи стоит в адресе страницы, а id это
номер дела. И то и другое неверно: id сквозной по фонду, а настоящие опись и
номер дела зашиты в пути к сканам. Поэтому 835 скачанных дел лежат в
data/opis_1/delo_{id} и подписаны в каталоге описью 1, хотя среди них есть
описи 1А и 2.

Сами файлы целы: ссылки брались из HTML, скачано верно. Перекачивать не надо,
надо переложить и переподписать.

Порядок важен. id 300 это дело 297, а папка delo_0297 уже занята под id 297,
то есть прямое переименованиеporождает коллизии. Поэтому сначала всё уезжает
в отстойник одним rename, потом раскладывается по местам.

Карта id -> (опись, дело) пишется в remap.json по мере построения, так что
прерванный прогон продолжается, а не начинается заново.

    python3 remap.py --dry-run     показать, что будет сделано
    python3 remap.py               выполнить
"""
import argparse
import csv
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsiolkovsky_downloader import (  # noqa: E402
    BASE, DATA, CATALOG, FIELDS, OPIS_NAME,
    fetch, parse_delo, norm_delo, polite_sleep, valid_jpeg, write_catalog,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
MAPFILE = os.path.join(ROOT, "remap.json")
STAGING = os.path.join(DATA, "_staging")


def load_map():
    if os.path.exists(MAPFILE):
        with open(MAPFILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_map(m):
    tmp = MAPFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, MAPFILE)


def build_map(portal_ids):
    """Для каждого id спрашивает у портала настоящие опись и номер дела."""
    m = load_map()
    todo = [p for p in portal_ids if str(p) not in m]
    print(f"карта: известно {len(m)}, спросить надо {len(todo)}")
    for i, pid in enumerate(todo, 1):
        html = fetch(f"{BASE}/ktsiolkovskyarchive/1_actview.aspx?id={pid}")
        polite_sleep()
        if not html:
            m[str(pid)] = None
        else:
            name, code, delo_no, links = parse_delo(html)
            m[str(pid)] = None if not (code and links) else {
                "opis_code": code, "delo": norm_delo(delo_no),
                "name": name, "expected": len(links),
            }
        if i % 25 == 0:
            save_map(m)
            print(f"  {i}/{len(todo)}", flush=True)
    save_map(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    old_rows = []
    if os.path.exists(CATALOG):
        with open(CATALOG, encoding="utf-8") as f:
            old_rows = list(csv.DictReader(f))
    # в старой схеме колонка delo хранила id портала
    portal_ids = sorted({int(r["delo"]) for r in old_rows if r.get("delo", "").isdigit()})
    print(f"дел в старом каталоге: {len(portal_ids)}")

    m = build_map(portal_ids)

    moves, missing = [], []
    for pid in portal_ids:
        info = m.get(str(pid))
        src = os.path.join(DATA, "opis_1", f"delo_{pid:04d}")
        if not os.path.isdir(src):
            continue
        if info is None:
            missing.append(pid)
            continue
        dst = os.path.join(DATA, f"opis_{info['opis_code']}", f"delo_{info['delo']}")
        moves.append((pid, src, dst, info))

    changed = [x for x in moves if os.path.normpath(x[1]) != os.path.normpath(x[2])]
    print(f"\nпапок к перекладке: {len(moves)}, из них реально меняют путь: {len(changed)}")
    by_opis = {}
    for _, _, _, info in moves:
        by_opis[info["opis_code"]] = by_opis.get(info["opis_code"], 0) + 1
    for code in sorted(by_opis):
        print(f"  {OPIS_NAME.get(code, code):<10} {by_opis[code]:>4} дел")
    if missing:
        print(f"  без данных на портале: {len(missing)} -> {missing[:8]}")

    print("\nпримеры перекладки:")
    for pid, src, dst, info in changed[:5]:
        print(f"  id {pid}: opis_1/delo_{pid:04d} -> "
              f"opis_{info['opis_code']}/delo_{info['delo']}")

    if args.dry_run:
        print("\n--dry-run: ничего не тронуто")
        return

    # 1. всё в отстойник одним движением, чтобы не поймать коллизии имён
    src_root = os.path.join(DATA, "opis_1")
    if os.path.isdir(src_root):
        if os.path.exists(STAGING):
            sys.exit("отстойник уже существует, разберитесь вручную: " + STAGING)
        os.rename(src_root, STAGING)
        print(f"\nopis_1 -> _staging")

    # 2. раскладываем по настоящим местам
    done = 0
    for pid, _, dst, info in moves:
        staged = os.path.join(STAGING, f"delo_{pid:04d}")
        if not os.path.isdir(staged):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            sys.exit(f"цель уже занята, это не должно случаться: {dst}")
        shutil.move(staged, dst)
        done += 1
    print(f"переложено папок: {done}")

    left = os.listdir(STAGING) if os.path.isdir(STAGING) else []
    if left:
        print(f"в отстойнике осталось {len(left)}: {left[:5]}")
    else:
        os.rmdir(STAGING)
        print("отстойник пуст, удалён")

    # 3. пересобираем каталог под новую схему, пересчитывая страницы по диску
    rows = []
    for pid, _, dst, info in moves:
        pages = sum(1 for x in os.listdir(dst)
                    if x.endswith(".jpg") and valid_jpeg(os.path.join(dst, x))) \
            if os.path.isdir(dst) else 0
        exp = info["expected"]
        rows.append({
            "opis": OPIS_NAME.get(info["opis_code"], info["opis_code"]),
            "opis_code": info["opis_code"], "delo": info["delo"],
            "portal_id": pid, "name": info["name"],
            "pages": pages, "expected": exp,
            "status": "empty" if not pages else ("ok" if pages >= exp else "partial"),
        })
    rows.sort(key=lambda r: (r["opis_code"], r["delo"]))
    write_catalog(rows)
    print(f"каталог пересобран: {len(rows)} дел, "
          f"{sum(r['pages'] for r in rows)} сканов")
    st = {}
    for r in rows:
        st[r["status"]] = st.get(r["status"], 0) + 1
    print(f"статусы: {st}")


if __name__ == "__main__":
    main()
