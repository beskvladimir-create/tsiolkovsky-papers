#!/usr/bin/env python3
"""
Check every figure in the paper against the data it claims to describe.

The corpus grows with each night's run, so every number in the paper is a
snapshot of a moving thing. Editing them by hand is how the abstract came to
say 36% where section 6 said 37%: the pair count had been updated and the
percentage had not. One number wrong in one place is worse than a number
missing, because a reader who checks it stops trusting the rest.

So the figures are not maintained by hand any more. This recomputes each of
them from the files on disk and compares it with what the paper says, and it is
meant to be run before the paper is touched or sent anywhere.

It reports a disagreement rather than fixing it. A changed number can mean the
corpus grew, which calls for an edit, or that something broke, which calls for
an investigation, and a script cannot tell the two apart.

    python3 check_paper.py
"""
import csv
import glob
import os
import re
import statistics as st
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.join(ROOT, "paper", "paper.md")


def load(path):
    p = os.path.join(ROOT, path)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def corpus():
    """Счёт по листам, без шапки дела.

    В шапке каждого файла стоит легенда разметки, и примеры в ней — `[?]`,
    `[неразборчиво]`, `~~зачёркнуто~~` — счётчик принимал за настоящие пометки.
    Это ровно по одному лишнему зачёркиванию и по два лишних знака сомнения на
    дело: 2 019 и 4 038 на весь фонд. Отсюда опубликованные 303 977 вместо
    299 939.
    """
    files = sheets = marks = struck = 0
    for p in glob.glob(os.path.join(ROOT, "data", "transcripts", "*", "*.md")):
        t = open(p, encoding="utf-8").read()
        files += 1
        sheets += len(re.findall(r"^## Лист ", t, re.M))
        body = t.split("## Лист", 1)[1] if "## Лист" in t else ""
        marks += body.count("[?]") + len(re.findall(r"\[неразборчиво", body))
        struck += len(re.findall(r"~~.+?~~", body))
    return files, sheets, marks, struck


def main():
    text = re.sub(r"\s+", " ", open(PAPER, encoding="utf-8").read())

    cat = load("catalog.csv")
    dates = [r for r in load("delo_dates.csv") if r["year_from"]]
    cls = Counter(r["class"] for r in load("page_classes.csv"))
    cal = load("reading_calibration.csv")
    val = load("calibration_validation.csv")
    ab = load("ab_models.csv")
    files, sheets, marks, struck = corpus()

    # Figures that depend on the corpus are checked against the snapshot the
    # paper was submitted with, not against today's data. The repository copy
    # must stay the paper that went to arXiv; drift is reported separately, as
    # information rather than as a fault.
    snap = {}
    sp = os.path.join(ROOT, "paper", "snapshot.json")
    if os.path.exists(sp):
        import json
        snap = json.load(open(sp, encoding="utf-8"))
    cf = snap.get("corpus_files", files)
    cs = snap.get("corpus_sheets", sheets)
    cm = snap.get("uncertainty_marks", marks)
    cd = snap.get("deletions", struck)

    checks = [
        ("files in the fond", f"{len(cat):,} files"),
        ("scans", f"{sum(int(r['pages'] or 0) for r in cat):,} scans"),
        ("dated", f"{len(dates):,} of those files"),
        ("conjectural", f"{sum(1 for r in dates if r['conjectural'] == '1')} of the dated"),
        ("handwritten", f"{cls['hand']:,}"),
        ("typewritten", f"{cls['typed']:,}"),
        ("notes", f"{cls['note']:,}"),
        ("corpus (as submitted)", f"{cf:,} files and {cs:,} scans"),
        ("uncertainty marks", f"{cm:,} uncertainty marks"),
        ("deletions", f"{cd:,} passages struck out"),
    ]
    if cal:
        # Как и корпусные числа, калибровочные сверяются со снимком: при
        # подаче замер шёл по одной описи, потому что остальное ещё не было
        # прочитано. Расширение на весь фонд — это рост данных, а не ошибка
        # в статье, и путать одно с другим нельзя.
        snap_cal = snap.get("calibration", {})
        live = dict(pairs=len(cal),
                    files=len({(r.get("opis", ""), r["delo"]) for r in cal})
                          or len({r["delo"] for r in cal}),
                    median_agreement=st.median(float(r["ratio"]) for r in cal),
                    median_longest_run=st.median(int(r["longest_run"]) for r in cal),
                    short_runs=sum(1 for r in cal
                                   if int(r["longest_run"]) < 10) / len(cal))
        g = lambda k: snap_cal.get(k, live[k])
        checks += [
            ("calibration pairs", f"{g('pairs'):,} such pairs"),
            ("calibration files", f"{g('pairs'):,} pairs from {g('files')} files"),
            ("median agreement", f"median {g('median_agreement')*100:.0f}%"),
            ("median longest run", f"median of {g('median_longest_run'):.0f} words"),
            ("short runs", f"on {g('short_runs')*100:.0f}% of pairs"),
        ]
        if snap_cal and snap_cal.get("pairs") != live["pairs"]:
            drift = (f"калибровка расширена: было {snap_cal['pairs']} пар из "
                     f"{snap_cal['files']} дел, стало {live['pairs']} из "
                     f"{live['files']}; медиана согласия "
                     f"{live['median_agreement']*100:.0f}%")
        else:
            drift = None
    if val:
        checks += [("validation pairs", f"Over {len(val)} such pairs")]
        # Ранговые связи: раньше не сверялись вовсе, и подвыборочные числа
        # (0.92 на 32 парах, 0.97 на 17) нельзя было проверить запуском. На
        # этом их легко спутать со связью по всем парам, что и случилось
        # 14 августа: 0.67 приняли за расхождение со статьёй.
        def rank(v):
            order = sorted(range(len(v)), key=lambda i: v[i])
            out = [0] * len(v)
            for pos, i in enumerate(order):
                out[i] = pos
            return out

        def rho_of(sub):
            if len(sub) < 3:
                return None
            a = rank([float(r["agree"]) for r in sub])
            b = rank([float(r["acc_hand"]) for r in sub])
            n = len(sub)
            d2 = sum((a[i] - b[i]) ** 2 for i in range(n))
            return 1 - 6 * d2 / (n * (n * n - 1))

        allp = rho_of(val)
        w85 = [r for r in val if float(r["acc_typed"]) >= 0.85]
        w90 = [r for r in val if float(r["acc_typed"]) >= 0.90]
        if allp is not None:
            checks.append(("rank correlation, all pairs",
                           f"{allp:.2f} over all {len(val)} pairs"))
        if rho_of(w85) is not None:
            checks.append(("rank correlation, faithful witness",
                           f"{rho_of(w85):.2f} over {len(w85)}"))
        if rho_of(w90) is not None:
            checks.append(("rank correlation, closest witness",
                           f"{rho_of(w90):.2f} over the {len(w90)} pairs"))
    if ab:
        win = sum(1 for r in ab
                  if float(r["agree_strong"]) > float(r["agree_cheap"]))
        checks += [("model test", f"wins on {win} and loses on {len(ab)-win}")]

    # Presence is not enough. A stale figure elsewhere in the text contradicts
    # the right one without ever making it absent, which is exactly how the
    # abstract came to disagree with section 6. So each quantity that has a
    # recognisable phrasing is also required to be stated the same way
    # everywhere it appears.
    contradictions = []
    if cal:
        want = f"{st.median(float(r['ratio']) for r in cal)*100:.0f}"
        found = set(re.findall(r"median (\d+)% of words", text))
        odd = found - {want}
        if odd:
            contradictions.append(
                f"«median N% of words»: сказано {sorted(odd)}, а по данным {want}")
    # "all 2,019 files and 51,008 scans" is the fond, not the corpus; the
    # corpus is always introduced by "currently" or "holds".
    for pat, want in ((r"(?:currently|holds) (\d[\d,]*) (?:archival )?files and [\d,]+ scans",
                       f"{cf:,}"),
                      (r"(?:currently|holds) [\d,]+ (?:archival )?files and ([\d,]*) scans",
                       f"{cs:,}")):
        found = set(re.findall(pat, text))
        odd = found - {want}
        if odd:
            contradictions.append(f"«{pat}»: сказано {sorted(odd)}, а по данным {want}")

    bad = 0
    for label, claim in checks:
        ok = claim.lower() in text.lower()
        bad += 0 if ok else 1
        print(f"  {'OK ' if ok else 'НЕТ'}  {label:<20} «{claim}»")

    print()
    for c in contradictions:
        print(f"  ПРОТИВОРЕЧИЕ  {c}")
    bad += len(contradictions)
    if bad:
        print(f"  расходится: {bad}. Числа в статье устарели или что-то сломалось;")
        print(f"  разобраться нужно вручную, скрипт этого не различает.")
    else:
        print(f"  все {len(checks)} величин совпадают с данными")
    if locals().get("drift"):
        print(f"\n  {drift}")
        print(f"  это тоже не расхождение: замер стал шире, а не другим.")
    if snap and files != cf:
        print(f"\n  корпус вырос с публикации: было {cf} дел и {cs:,} листов, "
              f"стало {files} и {sheets:,}.")
        print(f"  это не расхождение, а то, что раздел 8 статьи и предсказывает.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
