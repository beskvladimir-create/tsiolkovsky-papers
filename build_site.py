#!/usr/bin/env python3
"""
Build the static site that makes the fond browsable.

The archive's own portal offers one page view per file, reached by a numeric
id. There is no way to ask which files date from a given decade, which are
autograph and which typed, or where a phrase occurs. Everything needed to
answer those questions is now in the catalogue, so the site is a thin layer
over it: no server, no database, no build tool, one HTML file and one JSON.

The site data is trimmed rather than served whole. catalog.json is a megabyte
and carries fields a reader does not need; what goes to the browser is a
compact array of arrays, which loads quickly and keeps the page usable on a
phone.

The page is bilingual. Its own text is held in the template, and the archive's
descriptive vocabulary is glossed here into a Russian-to-English map, sent once
rather than per row. Titles and dates are never glossed: a title is the
archival record of what a document is called, and a translated one would give
a citation the archive does not recognise.

    python3 build_site.py
"""
import csv
import glob
import json
import os
import re
import shutil

from vocab import MATERIAL, REPRODUCTION, LANGUAGE, build as build_vocab

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs")

# Column order in the compact rows. The browser unpacks by index, so this
# must match the JavaScript in the template.
COLUMNS = ["opis", "delo", "title", "dates", "year", "conj", "pages",
           "material", "repro", "cls", "portal_id", "txt"]


def transcribed():
    """Which archival files have a published transcription."""
    out = {}
    for p in glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md")):
        opis = os.path.basename(os.path.dirname(p)).replace("opis_", "")
        delo = os.path.basename(p)[:-3].replace("delo_", "")
        out[(opis, delo.lstrip("0") or "0")] = f"opis_{opis}/delo_{delo}"
    return out


def page_mix():
    """Share of handwriting per archival file, as a single rounded percentage.

    A file is rarely all one thing, and the share is more informative than a
    label: 0 is a typed file, 100 a pure autograph, and the middle is where
    the manuscript and its typed copy sit together.
    """
    hand, total = {}, {}
    path = os.path.join(ROOT, "page_classes.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.search(r"opis_([^/]+)/delo_(\d+[а-яa-z]?)/", r["path"])
            if not m:
                continue
            k = (m.group(1), m.group(2).lstrip("0") or "0")
            total[k] = total.get(k, 0) + 1
            if r["class"] == "hand":
                hand[k] = hand.get(k, 0) + 1
    return {k: round(hand.get(k, 0) / v * 100) for k, v in total.items() if v}


def main():
    cat = json.load(open(os.path.join(ROOT, "catalog.json"), encoding="utf-8"))
    txt = transcribed()
    mix = page_mix()

    rows = []
    for r in cat["files"]:
        k = (r["opis_code"], r["delo"])
        rows.append([
            r["opis_code"],
            r["delo"],
            r["title"],
            r["dates"],
            r["year_from"] or 0,
            1 if r["date_conjectural"] else 0,
            r["pages_downloaded"],
            r["material"],
            r["reproduction"],
            mix.get(k, -1),
            r["portal_id"],
            txt.get(k, ""),
        ])
    rows.sort(key=lambda x: (x[0], int(re.sub(r"\D", "", x[1]) or 0), x[1]))

    os.makedirs(OUT, exist_ok=True)
    data = {
        "columns": COLUMNS,
        "vocab": {
            "material": build_vocab({r["material"] for r in cat["files"]}, MATERIAL),
            "repro": build_vocab({r["reproduction"] for r in cat["files"]}, REPRODUCTION),
            "language": build_vocab({r["language"] for r in cat["files"]}, LANGUAGE),
        },
        "files": len(rows),
        "scans": sum(r[6] for r in rows),
        "dated": sum(1 for r in rows if r[4]),
        "transcribed": sum(1 for r in rows if r[11]),
        "rows": rows,
    }
    with open(os.path.join(OUT, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    shutil.copy2(os.path.join(ROOT, "site", "index.html"),
                 os.path.join(OUT, "index.html"))
    size = os.path.getsize(os.path.join(OUT, "catalog.json")) // 1024
    kept = sum(1 for k, v in data["vocab"]["material"].items() if v != k)
    print(f"  docs/catalog.json  {size} KB, {len(rows)} files")
    print(f"  glossed material types: {kept} of {len(data['vocab']['material'])}")
    print(f"  docs/index.html")
    print(f"  dated {data['dated']}, transcribed {data['transcribed']}")


if __name__ == "__main__":
    main()
