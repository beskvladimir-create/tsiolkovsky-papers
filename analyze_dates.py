#!/usr/bin/env python3
"""
What the fond shows once every file has a date.

The dating comes from the archive's own portal (fetch_dates.py). Archivists
assigned it when the fond was described, so unlike everything derived from the
transcriptions it carries no reading error at all. The findings below therefore
rest only on dates, sheet counts and file titles, never on transcribed content.

Conjectural dating is kept as a separate flag: a date in square brackets was
established by the archivists from the contents rather than written by the
author. Wherever the order of two files matters, such files are called out.

The report is generated in Russian or English from the same code, so the two
cannot drift apart.

    python3 analyze_dates.py --lang en --out fond-in-dates.md
    python3 analyze_dates.py --lang ru --out fond-in-dates.ru.md
"""
import argparse
import csv
import re
from collections import Counter, defaultdict

# Month stems as the portal writes them. Russian only because the source is.
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
          "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11,
          "декабр": 12}

DAY, MONTH, YEAR = 3, 2, 1  # how precisely a date is given


def start_date(raw):
    """The opening date and how precisely it is given.

    The fond records dates unevenly: "19.10.1920", "март 1932 г.", "1932 г.",
    "июль 1924 г. - 8.06.1926". Take the first date and remember its precision.
    Two dates may only be compared down to the precision both of them have:
    "1932 г." and "март 1932 г." cannot be ordered.
    """
    s = raw.strip().split("-")[0]
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(1[89]\d\d)", s)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1))), DAY
    m = re.search(r"\b(1[89]\d\d)", s)
    if not m:
        return None, None
    y, low = int(m.group(1)), s.lower()
    for stem, num in MONTHS.items():
        if re.search(rf"\b{stem}[а-я]*\b", low):
            return (y, num, 0), MONTH
    return (y, 0, 0), YEAR


def load():
    dates = {r["portal_id"]: r
             for r in csv.DictReader(open("delo_dates.csv", encoding="utf-8"))}
    cat = {r["portal_id"]: r
           for r in csv.DictReader(open("catalog.csv", encoding="utf-8"))}
    rows = []
    for pid, d in dates.items():
        c = cat.get(pid)
        if not c:
            continue
        rows.append(dict(pid=pid, opis=d["opis_code"], delo=c["delo"],
                         name=c["name"], pages=int(c["pages"] or 0),
                         raw=d["dates_raw"],
                         yf=int(d["year_from"]) if d["year_from"] else None,
                         conj=d["conjectural"] == "1"))
    return rows


def by_decade(rows):
    files, sheets = Counter(), Counter()
    for r in rows:
        files[r["yf"] // 10 * 10] += 1
        sheets[r["yf"] // 10 * 10] += r["pages"]
    return files, sheets


def variants(rows):
    """Files marked as variants of one work, grouped, with their dating.

    The variant number in the description and the order of writing are two
    different things, and they do not always agree. This checks it directly.
    """
    def work(n):
        # Title as written, plus a lowercased key so that inconsistent quoting
        # does not split one work across several groups.
        m = re.search(r"[«\"]([^»\"]{5,})[»\"]", n)
        if not m:
            return None, None
        t = m.group(1).strip()
        return t, t.lower().replace("ё", "е")

    g = defaultdict(list)
    for r in rows:
        if "вариант" in r["name"].lower():
            title, key = work(r["name"])
            if key:
                r["work_title"] = title
                g[key].append(r)
    out = []
    for key, v in sorted(g.items()):
        if len(v) < 2:
            continue
        for r in v:
            m = re.search(r"(\d)-й вариант", r["name"])
            r["vnum"] = int(m.group(1)) if m else None
        v.sort(key=lambda r: (r["vnum"] or 9))
        out.append((v[0]["work_title"], v))
    return out


def out_of_order(pair):
    """True when variant 2 is dated earlier than variant 1, both dates firm.

    Conjectural dates are excluded: they were inferred from the contents, and
    an inference about the order must not rest on an inference about the date.
    """
    a, b = pair
    if a["conj"] or b["conj"]:
        return False
    da, pa = start_date(a["raw"])
    db, pb = start_date(b["raw"])
    if not (da and db):
        return False
    k = min(pa, pb)
    return db[:k] < da[:k]


def bolide(rows):
    """The response to the notice "Кто видел болид?", over time.

    A bolide crossed the Moscow region on 14 May 1934. Tsiolkovsky placed a
    notice in the newspapers asking eyewitnesses to write to him, and the
    replies entered the fond as separate files, one per correspondent. The
    dating shows the campaign as an event: when the letters came and how
    quickly they stopped.
    """
    letters = [r for r in rows
               if "в ответ на" in r["name"] and "олид" in r["name"]]
    months = Counter()
    for r in letters:
        d, prec = start_date(r["raw"])
        if d and prec in (DAY, MONTH):
            months[(d[0], d[1])] += 1
    return letters, months


T = {
 "ru": {
  "title": "# Фонд 555 в датах",
  "coverage": "Дел в фонде: {n}. С датировкой: {d} ({dp}%). Предположительно "
              "датированных: {c} ({cp}%).",
  "source": "Даты стоят в карточке каждого дела на портале архива, но в само "
            "описание дела год попадает лишь у 46 дел из 2019. Здесь они "
            "собраны в таблицу, так что фонд можно смотреть по времени целиком.",
  "h_dec": "## Собственные работы по десятилетиям",
  "dec_lead": "Опись 1, {n} дел, {s} листов, {a}-{b}.",
  "dec_head": "| Десятилетие | Дел | Доля дел | Листов | Листов на дело |",
  "dec_row": "| {k}-е | {f} | {fp}% | {s} | {per} |",
  "late": "На последние четыре года жизни, 1932-1935, приходится {f} дел из "
          "{tf}, то есть {fp}%, и {s} листов из {ts}, то есть {sp}%.",
  "late_note": "Доли по делам и по листам расходятся, и это не мелочь: поздние "
               "дела заметно короче ранних. Работа не прекращается, но меняет "
               "форму, переходя от развёрнутых сочинений к коротким заметкам. "
               "Столбец «листов на дело» по 1870-м и 1880-м годам держится на "
               "четырёх делах каждый и сам по себе ничего не значит; убыль "
               "видна на 1900-х и позже, где дел уже десятки и сотни.",
  "h_var": "## Номер варианта и хронология",
  "var_lead": "Часть сочинений хранится в нескольких делах, помеченных как "
              "1-й и 2-й вариант. Номер варианта и порядок написания "
              "совпадают не всегда.",
  "var_head": "| Сочинение | Дело | Вариант | Даты по описанию |",
  "var_row": "| {w} | д.{d} | {v} | {raw} |",
  "var_conflict": "У сочинения «{w}» второй вариант датирован раньше первого: "
                  "д.{db} это {rb}, а д.{da} это {ra}. Обе даты точные, без "
                  "квадратных скобок.",
  "var_note": "Отсюда следует практическое: ссылаться на «1-й вариант» как на "
              "более ранний нельзя, порядок надо брать из датировки.",
  "h_bol": "## Отклик на заметку «Кто видел болид?»",
  "bol_lead": "14 мая 1934 года над Московской областью прошёл болид. "
              "Циолковский дал в газеты заметку с просьбой к очевидцам писать "
              "ему. Ответы отложились в фонде отдельными делами, по делу на "
              "корреспондента: {n} писем, {s} листов, все в описи 4.",
  "bol_head": "| Месяц | Писем |",
  "bol_row": "| {m:02d}.{y} | {n} |",
  "bol_tail": "Датировано с точностью до месяца {t} писем из {n}. Отклик "
              "укладывается в считанные недели: на пик приходится {top} "
              "писем, то есть {tp}% всех датированных.",
  "bol_who": "Корреспонденты названы в описании дел с должностями: "
             "преподаватель физики сельхозтехникума, начальник отдела "
             "технического контроля завода, мастер химзавода, зоотехник, "
             "редактор журнала, сельский совет. Это наблюдательная кампания, "
             "поставленная частным лицом через газету и охватившая людей, к "
             "науке отношения не имевших.",
 },
 "en": {
  "title": "# Fond 555 in dates",
  "coverage": "Files in the fond: {n}. Dated: {d} ({dp}%). Conjecturally "
              "dated: {c} ({cp}%).",
  "source": "The archive's portal carries a date on every file's card, but "
            "only 46 of the 2,019 file descriptions state a year in the title "
            "itself. Collected here into a table, the fond can be read "
            "chronologically as a whole. Titles and dates are quoted "
            "throughout as the archive records them, in Russian and in the "
            "archive's own date format.",
  "h_dec": "## The author's own work, by decade",
  "dec_lead": "Opis 1, {n} files, {s} sheets, {a}-{b}.",
  "dec_head": "| Decade | Files | Share | Sheets | Sheets per file |",
  "dec_row": "| {k}s | {f} | {fp}% | {s} | {per} |",
  "late": "The last four years of his life, 1932-1935, account for {f} files "
          "of {tf}, that is {fp}%, and {s} sheets of {ts}, that is {sp}%.",
  "late_note": "The two shares diverge, and the gap matters: late files are "
               "markedly shorter than early ones. The work does not stop, it "
               "changes form, moving from extended treatises to short notes. "
               "The sheets-per-file column rests on four files each for the "
               "1870s and 1880s and means nothing on its own; the decline is "
               "visible from the 1900s on, where the counts run to tens and "
               "hundreds.",
  "h_var": "## Variant number against chronology",
  "var_lead": "Some works are held as several files marked 1st and 2nd "
              "variant. The variant number and the order of writing do not "
              "always agree.",
  "var_head": "| Work | File | Variant | Dates as described |",
  "var_row": "| {w} | no. {d} | {v} | {raw} |",
  "var_conflict": "For «{w}» the second variant is dated earlier than the "
                  "first: file {db} is {rb}, while file {da} is {ra}. Both "
                  "dates are firm, with no square brackets.",
  "var_note": "The practical consequence: the 1st variant cannot be cited as "
              "the earlier one, the order has to be taken from the dating.",
  "h_bol": "## The response to the notice \"Who saw the bolide?\"",
  "bol_lead": "A bolide crossed the Moscow region on 14 May 1934. Tsiolkovsky "
              "placed a notice in the newspapers asking eyewitnesses to write "
              "to him. The replies entered the fond as separate files, one per "
              "correspondent: {n} letters, {s} sheets, all in opis 4.",
  "bol_head": "| Month | Letters |",
  "bol_row": "| {y}-{m:02d} | {n} |",
  "bol_tail": "Of the {n} letters, {t} are dated to the month or better. The "
              "response is over within weeks: the peak month holds {top} "
              "letters, {tp}% of all dated ones.",
  "bol_who": "The file descriptions name the correspondents with their "
             "occupations: a physics teacher at an agricultural college, the "
             "head of quality control at a factory, a foreman at a chemical "
             "works, a livestock specialist, a magazine editor, a village "
             "council. This is an observational campaign run by a private "
             "individual through the newspapers, reaching people with no "
             "connection to science.",
 },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("ru", "en"), default="ru")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    t = T[args.lang]

    rows = load()
    dated = [r for r in rows if r["yf"]]
    own = [r for r in dated if r["opis"] == "1"]
    conj = sum(1 for r in dated if r["conj"])
    L = []
    p = L.append

    p(t["title"] + "\n")
    p(t["coverage"].format(n=f"{len(rows):,}", d=f"{len(dated):,}",
                           dp=f"{len(dated)/len(rows)*100:.0f}", c=conj,
                           cp=f"{conj/len(dated)*100:.0f}") + "\n")
    p(t["source"] + "\n")

    p(t["h_dec"] + "\n")
    own_sheets = sum(r["pages"] for r in own)
    p(t["dec_lead"].format(n=len(own), s=f"{own_sheets:,}",
                           a=min(r["yf"] for r in own),
                           b=max(r["yf"] for r in own)) + "\n")
    files, sheets = by_decade(own)
    p(t["dec_head"])
    p("|---|---:|---:|---:|---:|")
    for k in sorted(files):
        p(t["dec_row"].format(k=k, f=files[k], fp=f"{files[k]/len(own)*100:.0f}",
                              s=f"{sheets[k]:,}", per=f"{sheets[k]/files[k]:.0f}"))
    late = [r for r in own if r["yf"] >= 1932]
    late_sheets = sum(r["pages"] for r in late)
    p("\n" + t["late"].format(f=len(late), tf=len(own),
                              fp=f"{len(late)/len(own)*100:.0f}",
                              s=f"{late_sheets:,}", ts=f"{own_sheets:,}",
                              sp=f"{late_sheets/own_sheets*100:.0f}") + "\n")
    p(t["late_note"] + "\n")

    p(t["h_var"] + "\n")
    p(t["var_lead"] + "\n")
    p(t["var_head"])
    p("|---|---|---:|---|")
    conflicts = []
    for w, v in variants(rows):
        for r in v:
            p(t["var_row"].format(w=w, d=r["delo"].lstrip("0"),
                                  v=r["vnum"] or "?", raw=r["raw"]))
        if len(v) == 2 and out_of_order(v):
            conflicts.append((w, v[0], v[1]))
    p("")
    for w, a, b in conflicts:
        p(t["var_conflict"].format(w=w, db=b["delo"].lstrip("0"), rb=b["raw"],
                                   da=a["delo"].lstrip("0"), ra=a["raw"]) + "\n")
    p(t["var_note"] + "\n")

    letters, months = bolide(rows)
    if letters:
        p(t["h_bol"] + "\n")
        p(t["bol_lead"].format(n=len(letters),
                               s=f"{sum(r['pages'] for r in letters):,}") + "\n")
        p(t["bol_head"])
        p("|---|---:|")
        for (y, m), n in sorted(months.items()):
            p(t["bol_row"].format(y=y, m=m, n=n))
        tot, top = sum(months.values()), max(months.values())
        p("\n" + t["bol_tail"].format(t=tot, n=len(letters), top=top,
                                      tp=f"{top/tot*100:.0f}") + "\n")
        p(t["bol_who"] + "\n")

    text = "\n".join(L)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"  {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
