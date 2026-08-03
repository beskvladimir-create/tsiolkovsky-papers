#!/usr/bin/env python3
"""
English translations of the archival file titles.

A title in this catalogue is not a work's name but the archivists' description
of what the file contains: who wrote to whom, which article in which variant,
what is attached. Left in Russian it shuts the catalogue to most of its
readers; replaced by a translation it destroys the citation, because the
archive knows the file by its Russian description and by nothing else.

So both are kept. The original stays in the catalogue as the citable record,
and the translation is a separate column the site shows alongside it.

Rules would not do the job. Only 70% of the titles follow a handful of
patterns; the remaining 604 are ordinary prose, and a rule that meets prose it
was not written for produces confident nonsense. They are translated by the
same model and the same subscription that transcribes the scans, in batches,
overnight, at no cost.

The batch is written out only if the model returns exactly as many lines as it
was given, numbered as they were sent. A partial or reordered reply is
discarded rather than guessed at: a title silently attached to the wrong file
is worse than no translation.

    python3 translate_titles.py --limit 20     try it on a few
    python3 translate_titles.py                everything, resumable
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "title_en.csv")
BATCH = 40
MODEL = "sonnet"

PROMPT = """You are translating archival file descriptions from the catalogue of
fond 555 of the Archive of the Russian Academy of Sciences, the personal papers
of Konstantin Tsiolkovsky.

These are not titles of works. They are the archivists' descriptions of what
each file holds, and they must stay descriptions: do not shorten them, do not
turn them into headlines, do not add or drop information.

Rules:
- Render personal names in normal English transliteration. К.Э. Циолковский is
  K. E. Tsiolkovsky throughout.
- A work's own title, the part in quotation marks, is translated into English
  and kept in double quotes.
- Institutions, journals and newspapers get their established English name if
  they have one, otherwise a plain translation.
- Keep archival vocabulary exact: вариант is variant, автограф is autograph,
  машинопись с правкой автора is typescript with the author's corrections,
  черновик is draft, отрывок is extract, лист is sheet.
- Dates and numbers stay as they are.
- Square brackets carry meaning here: they mark what the archivists added
  themselves. Keep the ones that are in the original and never introduce a
  bracket of your own. Do not insert clarifying words, in brackets or
  otherwise: if the Russian is elliptical, the English is elliptical too.
- Translate nothing that is already English.

Reply with exactly one line per input, numbered the same way, in the same
order, with no commentary before or after. If a line cannot be translated,
repeat it unchanged rather than omitting it.

Translate:
"""


def load_done():
    if not os.path.exists(OUT):
        return {}
    with open(OUT, encoding="utf-8") as f:
        return {r["portal_id"]: r["title_en"] for r in csv.DictReader(f)}


def save(rows):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["portal_id", "title_ru", "title_en"])
        for pid in sorted(rows, key=int):
            w.writerow([pid, rows[pid][0], rows[pid][1]])
    os.replace(tmp, OUT)


def ask(batch):
    """Send one batch. Returns a list of translations, or None if unusable."""
    body = "\n".join(f"{i}. {t}" for i, (_, t) in enumerate(batch, 1))
    try:
        p = subprocess.run(
            ["claude", "-p", "--model", MODEL],
            input=PROMPT + body, text=True, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    out = p.stdout.strip()
    if re.search(r"session limit|rate.?limit|usage limit|exceeded your", out, re.I):
        raise SystemExit("subscription limit reached, stopping cleanly")
    got = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s*(.+?)\s*$", line)
        if m:
            got[int(m.group(1))] = m.group(2)
    if len(got) != len(batch) or set(got) != set(range(1, len(batch) + 1)):
        return None
    return [got[i] for i in range(1, len(batch) + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="translate only this many titles, for a trial run")
    args = ap.parse_args()

    cat = json.load(open(os.path.join(ROOT, "catalog.json"), encoding="utf-8"))
    done = load_done()
    rows = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["portal_id"]] = (r["title_ru"], r["title_en"])

    todo = [(str(r["portal_id"]), r["title"]) for r in cat["files"]
            if str(r["portal_id"]) not in done and r["title"]]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(cat['files'])} titles, {len(done)} already done, "
          f"{len(todo)} to translate", flush=True)

    bad = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        res = ask(batch)
        if res is None:
            bad += 1
            print(f"  batch at {i}: unusable reply, left for a later run", flush=True)
            continue
        for (pid, ru), en in zip(batch, res):
            rows[pid] = (ru, en)
        save(rows)
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    print(f"done: {len(rows)} translated, {bad} batches skipped")


if __name__ == "__main__":
    main()
