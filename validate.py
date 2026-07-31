#!/usr/bin/env python3
"""
Objective scoring of transcription accuracy.

The legibility test gave "roughly 75-85%", which was the reader's own estimate.
This measures it instead. Part of fond 555 was published, and those texts are
on Russian Wikisource under a free licence, so where a document in the fond
corresponds to a published text the transcription can be scored against it
character by character.

What the figure does and does not mean. The published edition went through an
editor: abbreviations expanded, orthography modernised, punctuation corrected.
So a share of the differences are not transcription errors but the distance
between manuscript and edition — and the transcription is frequently the more
faithful of the two, since it keeps pre-reform forms as written. Two metrics
are reported and the differences themselves are printed, so they can be read
rather than trusted.

Usage:
    python3 validate.py data/transcripts/opis_1/delo_0033.md \
        "Письмо в газету «Биржевые ведомости» (Циолковский)" --from-page 014
"""
import argparse
import difflib
import json
import re
import unicodedata
import urllib.parse
import urllib.request

API = "https://ru.wikisource.org/w/api.php"
UA = "tsiolkovsky-papers-research/1.0"


def wikisource_text(title):
    p = dict(action="query", prop="extracts", explaintext=1, titles=title,
             format="json", redirects=1)
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(p),
                                 headers={"User-Agent": UA})
    pages = json.load(urllib.request.urlopen(req, timeout=30))["query"]["pages"]
    page = list(pages.values())[0]
    if "missing" in page:
        raise SystemExit(f"no such page on Wikisource: {title}")
    text = page.get("extract", "") or ""
    if len(text.split()) >= 30:
        return page["title"], text

    # Most proofread texts are assembled by transclusion from scan pages, and
    # prop=extracts returns nothing for those. Fall back to rendering the page
    # and stripping the markup.
    p = dict(action="parse", page=title, prop="text", format="json",
             formatversion="2", redirects=1)
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(p),
                                 headers={"User-Agent": UA})
    html = json.load(urllib.request.urlopen(req, timeout=30)).get("parse", {}).get("text", "")
    html = re.sub(r"<(script|style|table)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    # running heads, page numbers and editorial boxes are not part of the text
    html = re.sub(r'<(sup|span|div)[^>]*class="[^"]*(?:reference|pagenum|ws-noexport|ws-summary)[^"]*"[^>]*>.*?</\1>',
                  " ", html, flags=re.S | re.I)
    import html as _h
    return page["title"], re.sub(r"[ \t]+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", html)))


def fold_orthography(s):
    """Map pre-reform orthography onto modern spelling.

    Published texts on Wikisource are usually modernised while the
    transcription keeps the original. Without this, every "полетъ" against
    "полет" counts as a misreading when the error runs the other way: the
    transcription is the faithful one. Report both figures.
    """
    s = re.sub(r"ъ(?=\s|$)", "", s)          # word-final hard sign
    return (s.replace("ѣ", "е").replace("і", "и").replace("ѳ", "ф")
             .replace("ѵ", "и").replace("Ѣ", "Е").replace("І", "И"))


def normalize(s, strip_markup=False, fold=False):
    """Reduce both texts to comparable form.

    The transcription's own markup is removed, as are the editorial
    differences that would otherwise dominate the diff: case, punctuation, ё/е.
    The markup patterns are Russian because the markers themselves are.
    """
    if strip_markup:
        # document header: title, catalogue fields, the note on method
        s = re.sub(r"^\*\*.*$|^>.*$", " ", s, flags=re.M)
        s = re.sub(r"\[\?\]", "", s)                        # uncertainty marks
        s = re.sub(r"\[неразборчиво[^\]]*\]", " ", s)       # illegible
        s = re.sub(r"\[(?:вставка|на полях|другой почерк|формула|рисунок)[^\]]*\]", " ", s)
        s = re.sub(r"~~.*?~~", " ", s)                      # struck out by the author
        s = re.sub(r"^#+.*$|^-{3,}$|^_.*_$", " ", s, flags=re.M)
    s = s.replace("-\n", "")                                # hyphenation
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("ё", "е").replace("«", '"').replace("»", '"')
    s = re.sub(r'[^\w\s"]', " ", s)                         # punctuation is editorial
    if fold:
        s = fold_orthography(s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser(
        description="Score a transcription against a published text on "
                    "Russian Wikisource.")
    ap.add_argument("transcript")
    ap.add_argument("title", help="page title on Russian Wikisource")
    ap.add_argument("--from-page", default=None,
                    help="compare from this scan onwards, e.g. 014")
    ap.add_argument("--show", type=int, default=25,
                    help="how many differences to print")
    ap.add_argument("--fold-orthography", action="store_true",
                    help="map pre-reform spelling onto modern before comparing")
    args = ap.parse_args()

    ours = open(args.transcript, encoding="utf-8").read()
    if args.from_page:
        m = re.search(rf"## Лист {args.from_page}(.*)$", ours, re.S)
        if not m:
            raise SystemExit(f"no scan {args.from_page} in that file")
        ours = m.group(1)

    title, pub = wikisource_text(args.title)
    a = normalize(ours, strip_markup=True, fold=args.fold_orthography)
    b = normalize(pub, fold=args.fold_orthography)

    ch = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    wa, wb = a.split(), b.split()
    sw = difflib.SequenceMatcher(None, wa, wb, autojunk=False)

    print(f"transcription : {args.transcript}"
          + (f" (from scan {args.from_page})" if args.from_page else ""))
    print(f"reference     : {title}")
    print(f"length        : {len(wa)} words against {len(wb)}\n")
    print(f"character-level agreement : {ch*100:.1f}%")
    print(f"word-level agreement      : {sw.ratio()*100:.1f}%")

    diffs = [(t, wa[i1:i2], wb[j1:j2]) for t, i1, i2, j1, j2 in sw.get_opcodes()
             if t != "equal"]
    print(f"\n{len(diffs)} differences. Read them: a share are editorial "
          f"changes made by the published edition, not misreadings.\n")
    for t, o, p in diffs[:args.show]:
        print(f"  [{t:7}] ours: {' '.join(o)[:52]!r:<54} publ.: {' '.join(p)[:52]!r}")


if __name__ == "__main__":
    main()
