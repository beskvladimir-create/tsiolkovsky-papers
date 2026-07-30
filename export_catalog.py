#!/usr/bin/env python3
"""
Export the fond 555 catalogue to JSON and build the priority list.

catalog.csv is written row by row by the downloader and holds the portal's
fields as they arrive. Here they are unpacked: the run-together "Название"
field is split into title, material type, reproduction method and dates, a
link to the source page is added, and the result is emitted as JSON.

The priority list is the rocketry core of the fond, selected by keywords in
the title so that it rebuilds itself as the catalogue grows rather than being
maintained by hand.
"""
import csv
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(ROOT, "catalog.csv")
BASE = "https://www.ras.ru/ktsiolkovskyarchive"

# The rocketry core of the fond. Patterns are Russian because the
# catalogue titles are.
PRIORITY_RE = re.compile(
    r"реактивн|ракет|космическ|звездоплав|мировых\s+пространств|"
    r"небесных\s+пространств|вне\s+земли|эфирн|межпланетн|"
    r"заатмосферн|тяготени|скорост",
    re.I,
)


def split_name(raw):
    """Split the portal's run-together title field into its parts."""
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
    # The title is everything before the first service field.
    cut = re.split(r"Вид материала:|Способ воспроизведения:|Крайние даты:", s, maxsplit=1)[0]
    out["title"] = cut.strip(" .;")
    return out


def load():
    """Read catalog.csv.

    Schema: opis and delo are the real archival inventory and file number;
    portal_id is the page id on the archive's site, from which the source
    link is built.
    """
    rows = []
    with open(CATALOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r.get("portal_id", "")
            if not pid.isdigit():
                continue
            parts = split_name(r.get("name", ""))
            rows.append({
                "opis": r.get("opis", ""),
                "opis_code": r.get("opis_code", ""),
                "delo": r.get("delo", "").lstrip("0") or "0",
                "portal_id": int(pid),
                **parts,
                "pages_downloaded": int(r.get("pages") or 0),
                "pages_expected": int(r.get("expected") or 0),
                "status": r.get("status", ""),
                # The inventory number in the address is decorative and any
                # value works; 1 is used consistently.
                "source_url": f"{BASE}/1_actview.aspx?id={pid}",
            })
    rows.sort(key=lambda r: (r["opis_code"], r["delo"].zfill(5)))
    return rows


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
        w = csv.DictWriter(f, fieldnames=["opis", "delo", "pages_expected",
                                          "status", "title", "source_url"])
        w.writeheader()
        for r in prio:
            w.writerow({k: r[k] for k in w.fieldnames})

    import collections
    by = collections.Counter(r["opis"] for r in rows)
    print(f"catalog.json: {len(rows)} files, "
          f"{sum(r['pages_downloaded'] for r in rows)} of "
          f"{sum(r['pages_expected'] for r in rows)} scans retrieved")
    for k in sorted(by):
        print(f"  {k:<10} {by[k]:>4} files")
    print(f"priority.csv: {len(prio)} files, "
          f"{sum(r['pages_expected'] for r in prio)} sheets")
    print("\npriority list, top 15:")
    for r in prio[:15]:
        print(f"  {r['opis']} d.{r['delo']:>5} {r['pages_expected']:>4} sh.  {r['title'][:60]}")


if __name__ == "__main__":
    main()
