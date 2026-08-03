#!/usr/bin/env python3
"""
A queue for re-reading sheets that went to the wrong model.

The line-regularity classifier was wrong on 29% of the scans. Among what had
already been transcribed, that hit two groups:

  156 typed sheets that Opus read as handwriting and archaised, supplying yats
      and hard signs that are not on the scan (checked by eye on a sample);
  222 handwritten sheets that Sonnet read as typescript, and on the hand it is
      measurably weaker.

Three quarters of the misdirected typescript came out right anyway, so this
re-reads only those two groups rather than everything.

The earlier versions are kept alongside in transcripts_pass1, so that before
and after can be compared rather than taken on trust.
"""
import collections
import csv
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCH_THR = 0.10  # pre-reform characters per word, above which a sheet is suspect

REASON_ARCHAISED = "typescript archaised"
REASON_WEAK_MODEL = "handwriting on the weaker model"


def raw_path(scan):
    p = scan.split("/")
    return os.path.join(ROOT, "data", "transcripts_raw", p[1], p[2],
                        p[3].replace(".jpg", ".txt"))


def archaisation(scan):
    """Share of pre-reform characters per word in what the model produced.

    Yat, decimal i, fita, izhitsa and word-final hard sign. On a typed sheet of
    the Soviet period they should be nearly absent, so a high share means the
    model wrote the page in an orthography the scan does not have.
    """
    t = raw_path(scan)
    if not os.path.exists(t):
        return None
    s = open(t, encoding="utf-8").read()
    w = len(s.split())
    if w < 30:
        return None
    return (len(re.findall(r"[ѣіѳѵ]", s)) + len(re.findall(r"ъ(?=\s|$)", s))) / w


def main():
    new = {r["path"]: r["class"] for r in csv.DictReader(
        open(os.path.join(ROOT, "page_classes.csv"), encoding="utf-8"))}
    q = json.load(open(os.path.join(ROOT, "queue.json"), encoding="utf-8"))

    items = []
    for it in q["items"]:
        now = new.get(it["path"], it["class"])
        was = it["class"]
        if was == "hand" and now == "typed":
            a = archaisation(it["path"])
            if a is not None and a > ARCH_THR:
                items.append(dict(it, class_=now, model="sonnet",
                                  status="pending", reason=REASON_ARCHAISED))
        elif was in ("typed", "note") and now == "hand":
            items.append(dict(it, class_=now, model="opus",
                              status="pending", reason=REASON_WEAK_MODEL))

    # keep the earlier transcriptions, or there will be nothing to compare with
    bak = os.path.join(ROOT, "data", "transcripts_pass1")
    raw_root = os.path.join(ROOT, "data", "transcripts_raw")
    kept = 0
    for it in items:
        src = raw_path(it["path"])
        if not os.path.exists(src):
            continue
        dst = os.path.join(bak, os.path.relpath(src, raw_root))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        kept += 1

    for it in items:
        it["class"] = it.pop("class_")

    shutil.copy2(os.path.join(ROOT, "queue.json"),
                 os.path.join(ROOT, "queue_pass1.json"))
    json.dump({"batch": q["batch"], "items": items},
              open(os.path.join(ROOT, "queue.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    by = collections.Counter(i["reason"] for i in items)
    print(f"  to re-read: {len(items)} scans")
    for k, v in by.items():
        print(f"    {k}: {v}")
    print(f"  earlier versions kept: {kept} files -> data/transcripts_pass1")
    print("  earlier queue -> queue_pass1.json")


if __name__ == "__main__":
    main()
