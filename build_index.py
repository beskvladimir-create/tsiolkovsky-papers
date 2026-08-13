#!/usr/bin/env python3
"""
Build the full-text index for the site.

The paper's complaint about the archive's own portal is that it offers no
full-text search. The site inherited the same fault: it searched titles and
nothing else, so a reader could find the file called "Космический корабль" but
not the page where the word occurs.

The transcriptions are too large to ship whole — 92 MB for the finished fond —
but a search does not need the text, only an index from word to file. That
inverts to 12.8 MB, 3.7 MB over the wire.

3.7 MB before the first word is found is still too much to send to a reader on
a phone, so the index ships in pieces, one per initial letter, fetched only
when a search needs it. The median piece is 8 KB and the largest, п, is 526 KB.
Prefix matching survives the split because the first letter of the query is
known before the lookup, which is the whole reason the split is by initial
letter rather than by anything cleverer.

Words occurring in more than half the fond are dropped. There are 180 of them,
they are prepositions and pronouns, and a search that returns every file
answers nothing.

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
OUT = os.path.join(ROOT, "docs", "ft")
MIN_LEN = 3
# Доля дел, выше которой слово перестаёт что-либо различать.
MAX_SHARE = 0.25

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

    cap = len(files) * MAX_SHARE
    common = sorted((w for w, v in index.items() if len(v) > cap), key=len)
    for w in common:
        del index[w]

    # Кусок на первую букву. Имя файла это код буквы, а не сама буква:
    # кириллица в имени файла переживает не всякий сервер и не всякий архив.
    shards = collections.defaultdict(dict)
    for w, v in sorted(index.items()):
        shards[w[0]][w] = sorted(v)

    os.makedirs(OUT, exist_ok=True)
    for old in glob.glob(os.path.join(OUT, "*.json")):
        os.remove(old)
    # указатель одним файлом, каким он был до разбиения: иначе 13 МБ поедут
    # на сайт вместе с кусками и никем не будут прочитаны
    whole = os.path.join(os.path.dirname(OUT), "fulltext.json")
    if os.path.exists(whole):
        os.remove(whole)
    sizes = {}
    for letter, part in shards.items():
        name = f"{ord(letter)}.json"
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(part, f, ensure_ascii=False, separators=(",", ":"))
        sizes[letter] = len(gzip.compress(
            json.dumps(part, ensure_ascii=False, separators=(",", ":")).encode()))

    meta = {"files": files,
            "shards": {letter: ord(letter) for letter in sorted(shards)},
            "skipped": common}
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))

    packed = sorted(sizes.values())
    meta_size = len(gzip.compress(
        json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode()))
    print(f"  {OUT}/")
    print(f"  дел {len(files)}, различных слов {len(index):,}, кусков {len(shards)}")
    print(f"  отброшено как встречающееся более чем в {cap:.0f} делах: "
          f"{len(common)} слов")
    print(f"  по сети: список дел {meta_size/1024:.0f} КБ, "
          f"кусок медиана {packed[len(packed)//2]/1024:.0f} КБ, "
          f"крупнейший {max(packed)/1024:.0f} КБ")
    print(f"  вместо {sum(packed)/1e6 + meta_size/1e6:.1f} МБ разом")


if __name__ == "__main__":
    main()
