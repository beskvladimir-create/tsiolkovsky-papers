#!/usr/bin/env python3
"""
Export the fond 555 catalogue to JSON and build the priority list.

catalog.csv is written row by row by the downloader and holds the portal's
fields as they arrive. Here they are unpacked: the run-together "Название"
field is split into title, material type, reproduction method and language, a
link to the source page is added, the dating is joined in from
delo_dates.csv, and the result is emitted as JSON.

The dating does not come from the title field and cannot: the downloader's
parser stopped at "Крайние даты" and never captured it, so the dates key was
empty for all 2,019 files. It is collected separately by fetch_dates.py and
joined here on the portal id.

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
    out = {"title": s, "material": "", "reproduction": "", "language": ""}
    # Every field name must appear in every other field's lookahead, or the
    # one that is not listed runs on into its neighbour. Leaving "Языки:" out
    # appended the language to the reproduction method of all 2,019 files.
    stop = r"Вид материала:|Способ воспроизведения:|Крайние даты:|Языки:"
    for key, name in (("material", "Вид материала"),
                      ("reproduction", "Способ воспроизведения"),
                      ("language", "Языки")):
        # (.*?) and not (.+?): nine files have an empty reproduction method,
        # and a pattern demanding at least one character swallowed the field
        # that followed it.
        m = re.search(rf"{name}:\s*(.*?)(?={stop}|$)", s, re.I)
        if m:
            out[key] = m.group(1).strip(" .;")
    # The title is everything before the first service field.
    out["title"] = re.split(stop, s, maxsplit=1)[0].strip(" .;")
    return out


def load_dates():
    """Dating by portal id, collected from the archive's cards by fetch_dates.py."""
    path = os.path.join(ROOT, "delo_dates.csv")
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["portal_id"]] = {
                "dates": r["dates_raw"],
                "year_from": int(r["year_from"]) if r["year_from"] else None,
                "year_to": int(r["year_to"]) if r["year_to"] else None,
                "date_conjectural": r["conjectural"] == "1",
            }
    return out


def load():
    """Read catalog.csv.

    Schema: opis and delo are the real archival inventory and file number;
    portal_id is the page id on the archive's site, from which the source
    link is built.
    """
    dates = load_dates()
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
                **dates.get(pid, {"dates": "", "year_from": None,
                                  "year_to": None, "date_conjectural": None}),
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
            "author": "Vladimir Beskorovainyi",
            "license": "CC0-1.0",
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
    dated = sum(1 for r in rows if r["year_from"])
    print(f"catalog.json: {len(rows)} files, {dated} dated, "
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
