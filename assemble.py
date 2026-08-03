#!/usr/bin/env python3
"""
Assembling transcriptions: one file per scan -> one markdown per archival file.

The nightly run drops one .txt per scan into data/transcripts_raw. Here they
are gathered into a finished document per archival file: a header with the
archival particulars from the catalogue, a link to the source, a note on the
method, then the sheets in order.

Only files transcribed in full are assembled. A partly transcribed file reads
as a complete text with the middle silently missing, and that is the worst kind
of error an archival publication can carry.

The assembled documents are in Russian throughout, since they are the archival
texts themselves; only this program is not.

    python3 assemble.py                 assemble everything ready
    python3 assemble.py --list          what is ready and what is not
"""
import argparse
import csv
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "transcripts_raw")
OUT = os.path.join(ROOT, "data", "transcripts")
BASE = "https://www.ras.ru/ktsiolkovskyarchive"


def catalog():
    return {(r["opis_code"], r["delo"]): r
            for r in csv.DictReader(
                open(os.path.join(ROOT, "catalog.csv"), encoding="utf-8"))}


def split_fields(raw):
    """Pull the title and the descriptive fields out of the portal's run-on
    "Название" string. The field names are the portal's own Russian markup."""
    s = re.sub(r"\s+", " ", raw or "").strip()
    out = {}
    for key, pat in (
        ("material", r"Вид материала:\s*(.+?)(?=Способ воспроизведения:|Крайние даты:|Языки:|$)"),
        ("repro", r"Способ воспроизведения:\s*(.+?)(?=Вид материала:|Крайние даты:|Языки:|$)"),
        ("dates", r"Крайние даты:\s*(.+?)(?=Вид материала:|Способ воспроизведения:|Языки:|$)"),
    ):
        m = re.search(pat, s, re.I)
        out[key] = m.group(1).strip(" .;") if m else ""
    out["title"] = re.split(
        r"Вид материала:|Способ воспроизведения:|Крайние даты:|Языки:",
        s, maxsplit=1)[0].strip(" .;")
    return out


def scan_state(cat):
    """For each archival file: how many scans are transcribed, out of how many."""
    state = {}
    if not os.path.isdir(RAW):
        return state
    for opis in sorted(os.listdir(RAW)):
        code = opis.replace("opis_", "")
        d = os.path.join(RAW, opis)
        if not os.path.isdir(d):
            continue
        for delo in sorted(os.listdir(d)):
            dd = os.path.join(d, delo)
            if not os.path.isdir(dd):
                continue
            num = delo.replace("delo_", "")
            row = cat.get((code, num))
            if not row:
                continue
            txts = sorted(x for x in os.listdir(dd) if x.endswith(".txt"))
            state[(code, num)] = (len(txts), int(row["pages"] or 0), row, txts, dd)
    return state


def build(num, row, txts, dd):
    f = split_fields(row.get("name", ""))
    head = [
        f"# Фонд 555, {row['opis'].lower()}, дело {num.lstrip('0')}",
        "",
        f"**Название:** {f['title']}",
    ]
    if f["material"]:
        head.append(f"**Вид материала:** {f['material']}")
    if f["repro"]:
        head.append(f"**Способ воспроизведения:** {f['repro']}")
    if f["dates"]:
        head.append(f"**Крайние даты:** {f['dates']}")
    head += [
        f"**Сканов:** {len(txts)}",
        f"**Источник:** {BASE}/1_actview.aspx?id={row['portal_id']}",
        "",
        "> Машинная транскрипция по `TRANSCRIPTION_SPEC.md`. Экспертная выверка",
        "> не проводилась. Пометки: `[?]` неуверенное чтение, `[неразборчиво]`",
        "> нечитаемое, `~~зачёркнуто~~` правка автора, `[вставка: ...]`,",
        "> `[на полях: ...]`, `[другой почерк: ...]`. Орфография оригинала",
        "> сохранена, включая дореформенные буквы.",
        "",
        "---",
    ]
    body = []
    for t in txts:
        text = open(os.path.join(dd, t), encoding="utf-8").read().strip()
        body.append(f"## Лист {t.replace('.txt','')}\n\n{text or '[пустой лист]'}\n")
    return "\n".join(head) + "\n\n" + "\n---\n\n".join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    cat = catalog()
    state = scan_state(cat)
    ready = {k: v for k, v in state.items() if v[0] >= v[1] > 0}
    partial = {k: v for k, v in state.items() if k not in ready}

    if args.list:
        print(f"  complete: {len(ready)}")
        for (c, n), (a, b, row, _, _) in sorted(ready.items()):
            print(f"    {row['opis']} no.{n.lstrip('0'):<6} {a}/{b}  "
                  f"{row['name'][:56]}")
        if partial:
            print(f"  in progress: {len(partial)}")
            for (c, n), (a, b, row, _, _) in sorted(partial.items()):
                print(f"    {row['opis']} no.{n.lstrip('0'):<6} {a}/{b}")
        return

    made = 0
    for (c, n), (a, b, row, txts, dd) in sorted(ready.items()):
        out_dir = os.path.join(OUT, f"opis_{c}")
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, f"delo_{n}.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(build(n, row, txts, dd))
        made += 1
        print(f"  {p}  ({a} sheets, {os.path.getsize(p)//1024} KB)")
    print(f"\n  assembled: {made}; not yet complete: {len(partial)}")


if __name__ == "__main__":
    main()
