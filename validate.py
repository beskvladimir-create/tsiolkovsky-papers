#!/usr/bin/env python3
"""
Объективная оценка точности транскрипции.

Отчёт А0 давал «примерно 75-85%», и это была оценка на глаз. Здесь цифра
измеряется: часть материалов фонда 555 публиковалась, и опубликованный текст
лежит в Викитеке под свободной лицензией. Где рукопись из фонда соответствует
изданному тексту, транскрипцию можно сверить посимвольно.

Важно, что показывает цифра. Изданный текст прошёл через редактора: сокращения
раскрыты, орфография осовременена, пунктуация выправлена. Поэтому часть
расхождений это не наши ошибки, а разница между рукописью и редакцией, причём
наша версия часто ближе к источнику (сохраняет дореформенные формы). Считаем
две метрики и печатаем сами расхождения, чтобы их можно было разобрать руками.

Использование:
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
        raise SystemExit(f"в Викитеке нет страницы: {title}")
    return page["title"], page.get("extract", "")


def normalize(s, strip_markup=False):
    if strip_markup:
        s = re.sub(r"\[\?\]", "", s)                        # пометки неуверенности
        s = re.sub(r"\[неразборчиво[^\]]*\]", " ", s)
        s = re.sub(r"\[(?:вставка|на полях|другой почерк|формула|рисунок)[^\]]*\]", " ", s)
        s = re.sub(r"~~.*?~~", " ", s)                      # зачёркнутое автором
        s = re.sub(r"^#+.*$|^-{3,}$|^_.*_$", " ", s, flags=re.M)
    s = s.replace("-\n", "")                                # переносы по слогам
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("ё", "е").replace("«", '"').replace("»", '"')
    s = re.sub(r'[^\w\s"]', " ", s)                         # пунктуация редакторская
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("title", help="заголовок страницы в Викитеке")
    ap.add_argument("--from-page", default=None,
                    help="сверять начиная с этого листа, напр. 014")
    ap.add_argument("--show", type=int, default=25, help="сколько расхождений печатать")
    args = ap.parse_args()

    ours = open(args.transcript, encoding="utf-8").read()
    if args.from_page:
        m = re.search(rf"## Лист {args.from_page}(.*)$", ours, re.S)
        if not m:
            raise SystemExit(f"в файле нет листа {args.from_page}")
        ours = m.group(1)

    title, pub = wikisource_text(args.title)
    a, b = normalize(ours, strip_markup=True), normalize(pub)

    ch = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    wa, wb = a.split(), b.split()
    sw = difflib.SequenceMatcher(None, wa, wb, autojunk=False)

    print(f"транскрипция : {args.transcript}"
          + (f" (с листа {args.from_page})" if args.from_page else ""))
    print(f"эталон       : {title}")
    print(f"объём        : {len(wa)} слов против {len(wb)}\n")
    print(f"посимвольное совпадение : {ch*100:.1f}%")
    print(f"пословное совпадение    : {sw.ratio()*100:.1f}%")

    diffs = [(t, wa[i1:i2], wb[j1:j2]) for t, i1, i2, j1, j2 in sw.get_opcodes()
             if t != "equal"]
    print(f"\nрасхождений: {len(diffs)}. Разбирать руками: часть из них это "
          f"редакторская правка издания, а не ошибка чтения.\n")
    for t, o, p in diffs[:args.show]:
        print(f"  [{t:7}] мы: {' '.join(o)[:52]!r:<54} изд.: {' '.join(p)[:52]!r}")


if __name__ == "__main__":
    main()
