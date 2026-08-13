#!/usr/bin/env python3
"""
Точность корпуса против опубликованных текстов, посчитанная по всему, что
удалось сопоставить, а не по одному делу за раз.

`validate.py` сверяет одно дело с одной страницей Викитеки, и название
страницы ему называют вручную. Пока корпус был пятой частью фонда, этого
хватало. Теперь дел 2 018, и руками их с публикациями не свести.

Соответствие ищется по названию: в Викитеке берутся все тексты Циолковского
из его категорий, названия чистятся от служебного хвоста архивной описи и
сравниваются с заголовком дела. Порог намеренно высокий: пара, в которой не
уверены, не годится для замера точности вообще, а число, посчитанное по
случайно склеенным парам, хуже отсутствия числа.

Дело и публикация редко совпадают по составу: в деле бывают черновики,
варианты и то, что в издание не вошло. Поэтому сходство считается по лучшему
куску, а не по всей длине, и рядом печатается, какую долю дела этот кусок
занимает. Дело, от которого совпал огрызок, честнее выбросить, чем засчитать.

Дореформенные варианты страниц (/ДО) для нас точнее модернизированных: корпус
хранит орфографию как в рукописи. Считаются оба варианта.

    python3 validate_corpus.py              # весь корпус
    python3 validate_corpus.py --limit 5    # быстрая проба
"""
import argparse
import csv
import difflib
import glob
import json
import os
import re
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import wikisource_text, normalize

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "corpus_validation.csv")
CATS = ["Категория:Константин Эдуардович Циолковский"]
MIN_TITLE = 0.75      # ниже этого пара не считается сопоставленной
MIN_COVER = 0.20      # ниже этого тексты слишком разной длины, чтобы
                      # считать их одним и тем же произведением


def api(**p):
    """Викитека отвечает 429, если её торопить."""
    import urllib.parse, urllib.request
    p.setdefault("format", "json")
    p.setdefault("formatversion", "2")
    url = "https://ru.wikisource.org/w/api.php?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={
        "User-Agent": "tsiolkovsky-papers-research/1.0 (beskvladimir@gmail.com)"})
    for attempt in range(6):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(5 + attempt * 5)


def wikisource_titles():
    seen, texts, todo = set(), [], list(CATS)
    while todo:
        cat = todo.pop()
        if cat in seen:
            continue
        seen.add(cat)
        for m in api(action="query", list="categorymembers",
                     cmtitle=cat, cmlimit=500)["query"]["categorymembers"]:
            t = m["title"]
            if t.startswith("Категория:"):
                todo.append(t)
            elif m["ns"] == 0 and not t.startswith("Автор:"):
                texts.append(t)
        time.sleep(2)
    return sorted(set(texts))


def clean(s):
    s = s.lower().replace("ё", "е")
    s = re.sub(r"\(циолковский\)|/до", " ", s)
    s = re.sub(r"вид материала.*|способ воспроизведения.*|языки.*", " ", s)
    s = re.sub(r"[^а-яa-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def delo_title(name):
    """Заголовок дела: то, что архив взял в кавычки, иначе всё описание."""
    m = re.search(r'"([^"]+)"', name)
    return clean(m.group(1) if m else name)


def transcribed():
    have = {f"opis_{r['opis_code']}/delo_{r['delo']}": r["name"]
            for r in csv.DictReader(open(os.path.join(ROOT, "catalog.csv"),
                                         encoding="utf-8"))}
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md"))):
        key = f"{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)[:-3]}"
        if key in have:
            out.append((key, p, delo_title(have[key])))
    return out


def best_block(a, b):
    """Сходство сопоставимых частей и то, насколько они вообще сопоставимы.

    Дело и публикация почти никогда не равны по составу, причём в обе
    стороны: дело 38 это черновой фрагмент «Вне Земли» в 1 166 слов против
    изданной повести в 45 338, а дело 395 наоборот вдвое длиннее издания, за
    счёт вариантов и не вошедшего. Сравнение по всей длине в первом случае
    даёт 1%, и это число не про чтение, а про то, что тексты разной длины.

    Поэтому короткий текст сличается с окном той же длины в длинном, взятым
    вокруг самого длинного дословного совпадения. Отдельно возвращается доля
    короткого в длинном: она говорит, какую часть публикации дело покрывает,
    и не даёт принять фрагмент за целое.
    """
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if not short:
        return 0.0, 0.0
    m = difflib.SequenceMatcher(None, short, long_,
                                autojunk=False).find_longest_match(
                                    0, len(short), 0, len(long_))
    if not m.size:
        return 0.0, len(short) / len(long_)
    lo = max(0, min(m.b - m.a, len(long_) - len(short)))
    window = long_[lo:lo + len(short)]
    return (difflib.SequenceMatcher(None, short, window, autojunk=False).ratio(),
            len(short) / len(long_))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("собираю тексты Циолковского в Викитеке…")
    titles = wikisource_titles()
    files = transcribed()
    print(f"  текстов {len(titles)}, расшифрованных дел {len(files)}\n")

    pairs = []
    for t in titles:
        nt = clean(t)
        key, path, dt = max(files, key=lambda f: difflib.SequenceMatcher(
            None, nt, f[2]).ratio())
        r = difflib.SequenceMatcher(None, nt, dt).ratio()
        if r >= MIN_TITLE:
            pairs.append((t, key, path, round(r, 2)))
    print(f"сопоставлено по названию: {len(pairs)} пар\n")
    if args.limit:
        pairs = pairs[:args.limit]

    rows = []
    for title, key, path, tr in pairs:
        try:
            got, pub = wikisource_text(title)
        except SystemExit as e:
            print(f"  ! {title}: {e}")
            continue
        ours = open(path, encoding="utf-8").read()
        for fold in (False, True):
            a = normalize(ours, strip_markup=True, fold=fold)
            b = normalize(pub, fold=fold)
            ch, cover = best_block(a, b)
            wa, wb = a.split(), b.split()
            wr, _ = best_block(wa, wb)
            if not fold:
                raw = (ch, wr, cover)
            else:
                rows.append(dict(delo=key, wikisource=title, title_match=tr,
                                 words_ours=len(wa), words_pub=len(wb),
                                 coverage=round(cover, 3),
                                 chars_raw=round(raw[0], 3), words_raw=round(raw[1], 3),
                                 chars_folded=round(ch, 3), words_folded=round(wr, 3)))
        r = rows[-1]
        flag = "" if r["coverage"] >= MIN_COVER else "  (разной длины, не в счёт)"
        print(f"  {key}  {title[:40]:<40} знаков {r['chars_folded']*100:>5.1f}%"
              f"  слов {r['words_folded']*100:>5.1f}%{flag}")
        time.sleep(1)

    if not rows:
        print("\nсверять нечего")
        return
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    report(rows)


def report(rows):
    good = [r for r in rows if r["coverage"] >= MIN_COVER]
    med = lambda x: sorted(x)[len(x) // 2] if x else 0
    print(f"\nсверено дел: {len(good)} из {len(rows)} сопоставленных")
    print("  с приведением орфографии к современной:")
    print(f"    знаков {med([r['chars_folded'] for r in good])*100:.1f}%   "
          f"слов {med([r['words_folded'] for r in good])*100:.1f}%")
    print("  без приведения (публикация модернизирована, корпус нет):")
    print(f"    знаков {med([r['chars_raw'] for r in good])*100:.1f}%   "
          f"слов {med([r['words_raw'] for r in good])*100:.1f}%")

    # Числа расходятся не плавно, а на две кучи, и это не свойство чтения.
    # Там, где в деле лежит та же редакция, что напечатана, выходит 87-98%.
    # Там, где в деле черновик, выписки или материалы к статье, выходит 6-25%,
    # и это расстояние между рукописью и изданием, а не ошибки чтения: в деле
    # 76 к «Целям звездоплавания» лежит перечень трудов, а не сама статья.
    hi = [r for r in good if r["chars_folded"] >= 0.60]
    lo = [r for r in good if r["chars_folded"] < 0.60]
    print(f"\n  дел, где издание и дело это одна редакция ({len(hi)}):")
    print(f"    знаков {med([r['chars_folded'] for r in hi])*100:.1f}%   "
          f"слов {med([r['words_folded'] for r in hi])*100:.1f}%")
    print(f"  дел, где состав дела и издания разошёлся ({len(lo)}):")
    print(f"    знаков {med([r['chars_folded'] for r in lo])*100:.1f}%")
    for r in sorted(lo, key=lambda x: x["chars_folded"])[:4]:
        print(f"      {r['delo']}  {r['wikisource'][:44]:<44} "
              f"{r['words_ours']} слов против {r['words_pub']}")
    print("\n  Общая медиана поэтому не есть точность чтения: в неё входит")
    print("  расстояние между рукописью и печатным изданием. Как точность")
    print("  читается только верхняя группа, и то с оглядкой на редактуру.")
    print(f"\n  таблица: {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
