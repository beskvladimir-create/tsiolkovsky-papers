#!/usr/bin/env python3
"""
Build the full-text index for the site.

The paper's complaint about the archive's own portal is that it offers no
full-text search. The site inherited the same fault: it searched titles and
nothing else, so a reader could find the file called "Космический корабль" but
not the page where the word occurs.

The transcriptions are too large to ship whole — 10 MB now, some 95 MB once the
fond is finished — but a search does not need the text, only an index from word
to file. That inverts to 1.9 MB, half a megabyte over the wire, and perhaps
3 MB compressed when the fond is complete.

Russian morphology is handled by prefix rather than by stemming: the index
stores whole word forms and the browser matches any term beginning with what
was typed, so "ракет" finds ракета, ракеты, ракетой and ракетоплан alike. A
stemmer would be more precise and would need a dictionary the page cannot
afford; prefix matching errs towards showing too much, which is the safer
direction when the alternative is finding nothing.

Editorial markup is stripped before indexing. Searching for "неразборчиво"
should not return every file in the corpus.

    python3 build_index.py
"""
import collections
import glob
import gzip
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "fulltext.json")
MIN_LEN = 3

# Markup the transcription convention adds, which is about the reading rather
# than about the text, and which would otherwise match everywhere.
MARKUP = re.compile(r"\[[^\]]*\]|~~|^#+.*$|^\*\*.*$|^>.*$", re.M)


def words(text):
    text = MARKUP.sub(" ", text.lower())
    for w in re.findall(r"[а-яёa-z]{%d,}" % MIN_LEN, text):
        yield w.replace("ё", "е")


def main():
    files, index = [], collections.defaultdict(set)
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md"))):
        opis = os.path.basename(os.path.dirname(path))
        delo = os.path.basename(path)[:-3]
        i = len(files)
        files.append(f"{opis}/{delo}")
        for w in words(open(path, encoding="utf-8").read()):
            index[w].add(i)

    data = {"files": files,
            "index": {w: sorted(v) for w, v in sorted(index.items())}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(OUT)
    packed = len(gzip.compress(open(OUT, "rb").read()))
    once = sum(1 for v in index.values() if len(v) == 1)
    print(f"  {OUT}")
    print(f"  дел {len(files)}, различных слов {len(index):,}")
    print(f"  из них встречаются в одном деле: {once:,} ({once/len(index)*100:.0f}%)")
    print(f"  {size/1024/1024:.1f} МБ, по сети около {packed/1024/1024:.1f} МБ")


if __name__ == "__main__":
    main()
