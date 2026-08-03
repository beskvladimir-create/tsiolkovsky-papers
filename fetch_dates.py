#!/usr/bin/env python3
"""
The dating of the files, taken from the archive's portal.

While the scans were being fetched, only the title and the image links were
read out of each file's card, and the "Крайние даты" field was thrown away:
the title parser stopped right at it. That field is the only precise dating the
fond has. A year appears in the file description itself for just 46 files out
of 2,019, the file covers are not always dated, and the transcriptions have no
bearing on dating at all and carry reading errors besides. "Крайние даты" was
assigned by archivists when the fond was described and carries no recognition
error whatsoever.

The dates are written in several ways: "12.08.1934", "июль 1924 г. - 8.06.1926",
"1903", "[июнь 1925 г.]". Square brackets are the archivists' mark for a
conjectural date, established from the contents rather than written by the
author. That distinction is preserved: conjectural dates cannot carry an
argument about what preceded what.

The years of the opening and closing dates are parsed out; everything else is
kept verbatim, so the parse can be checked against the original string.

    python3 fetch_dates.py          # resumes where it left off
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsiolkovsky_downloader import fetch, polite_sleep, BASE

OUT = "delo_dates.csv"
FIELDS = ["portal_id", "opis_code", "delo", "dates_raw", "year_from", "year_to",
          "conjectural", "material", "reproduction"]


def parse_dates(s):
    """Opening and closing years, plus the conjectural-dating flag."""
    conj = 1 if "[" in s else 0
    years = [int(y) for y in re.findall(r"\b(1[89]\d\d)\b", s)]
    if not years:
        return None, None, conj
    return min(years), max(years), conj


def field(text, name, stop):
    """One field of the card.

    The pattern allows an empty value on purpose. Demanding at least one
    character makes an empty field swallow everything after it: two cards
    carry no closing date, and a greedy read pulled in the rest of the page,
    navigation and analytics script included.
    """
    m = re.search(rf"{name}:\s*(.*?)(?:{stop})", text)
    return m.group(1).strip() if m else ""


def scrape(portal_id):
    html = fetch(f"{BASE}/ktsiolkovskyarchive/1_actview.aspx?id={portal_id}")
    polite_sleep()
    if not html:
        return None
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    # Field names are the portal's own Russian markup, so they stay in Russian.
    stop = "Вид материала|Способ воспроизведения|Языки|Крайние даты|Изображения страниц|$"
    raw = field(t, "Крайние даты", stop)
    yf, yt, conj = parse_dates(raw)
    return dict(dates_raw=raw,
                year_from=yf if yf else "",
                year_to=yt if yt else "",
                conjectural=conj,
                material=field(t, "Вид материала", stop),
                reproduction=field(t, "Способ воспроизведения", stop))


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["portal_id"]: r for r in csv.DictReader(f)}


def save(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(rows, key=lambda x: int(x)):
            w.writerow(rows[k])
    os.replace(tmp, path)


def main():
    with open("catalog.csv", encoding="utf-8") as f:
        cat = list(csv.DictReader(f))
    have = load(OUT)
    todo = [r for r in cat if r["portal_id"] not in have]
    print(f"{len(cat)} files in all, {len(have)} already held, "
          f"{len(todo)} to fetch", flush=True)

    for i, r in enumerate(todo, 1):
        d = scrape(r["portal_id"])
        if d is None:
            print(f"  id={r['portal_id']}: card did not load, skipped", flush=True)
            continue
        have[r["portal_id"]] = dict(portal_id=r["portal_id"],
                                    opis_code=r["opis_code"], delo=r["delo"], **d)
        if i % 25 == 0:
            save(OUT, have)
            print(f"  {i}/{len(todo)}", flush=True)
    save(OUT, have)
    dated = sum(1 for v in have.values() if v["year_from"])
    print(f"done: {len(have)} files, {dated} of them dated")


if __name__ == "__main__":
    main()
