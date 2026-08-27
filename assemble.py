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


def titles_en():
    """Английские названия дел: они переведены отдельно (title_en.csv) и здесь
    ставятся рядом с русским, а не вместо него. Русское название — цитируемая
    запись архива, и ссылка резолвится по нему."""
    out = {}
    p = os.path.join(ROOT, "title_en.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8")):
            out[r["portal_id"]] = r["title_en"]
    return out


EN = titles_en()


def build(num, row, txts, dd):
    f = split_fields(row.get("name", ""))
    # Служебные поля по-английски: корпус лежит на международных площадках, и
    # читатель, открывший файл, должен понимать хотя бы что перед ним. Значения
    # остаются как в описи, по-русски: это цитируемая архивная запись.
    en = EN.get(row.get("portal_id", ""))
    head = [
        f"# Fond 555, opis {row['opis'].lower().replace('опись', '').strip()}, "
        f"delo {num.lstrip('0')}",
        "",
        f"**Title (as catalogued):** {f['title']}",
    ]
    if en:
        head.append(f"**Title (English):** {en}")
    if f["material"]:
        head.append(f"**Material:** {f['material']}")
    if f["repro"]:
        head.append(f"**Reproduction:** {f['repro']}")
    if f["dates"]:
        head.append(f"**Dates:** {f['dates']}")
    head += [
        f"**Scans:** {len(txts)}",
        f"**Source:** {BASE}/1_actview.aspx?id={row['portal_id']}",
        "",
        "> Machine transcription per `TRANSCRIPTION_SPEC.md`; no expert check has",
        "> been made against the scans. Markup: `[?]` uncertain reading,",
        "> `[неразборчиво]` illegible, `~~struck~~` deleted by the author,",
        "> `[вставка: ...]` insertion, `[на полях: ...]` marginal note,",
        "> `[другой почерк: ...]` a different hand. Original orthography is kept,",
        "> including pre-reform letters.",
        "",
        "---",
    ]
    body = []
    for t in txts:
        text = open(os.path.join(dd, t), encoding="utf-8").read().strip()
        body.append(f"## Sheet {t.replace('.txt','')}\n\n{text or '[пустой лист]'}\n")
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
