#!/usr/bin/env python3
"""
Building the transcription queue over a list of priority files.

Each scan is assigned a model according to its page type, taken from
page_classes.csv:
  typescript      -> sonnet (measured 98.2%, level with opus but cheaper on quota)
  note or cover   -> sonnet, the output is tiny
  handwriting     -> opus (noticeably more accurate on the hand)

The type comes from page_classes.csv specifically. The earlier feature, the
regularity of line spacing, was rejected: neat cursive is as evenly spaced as
print. What decides is the spread of ink-run lengths along a line
(typescript_features.py), and it has been checked both against sheets labelled
by hand and against the agreement of two readings of one text
(calibrate_reading.py).

The priority file supplies the list of archival files and their order. Order
matters: the queue is worked through in sequence, so whatever stands higher
gets transcribed the same night.

State lives in queue.json: every scan is pending, done or failed. A run can be
interrupted at any moment and at most one batch is lost.

    python3 build_queue.py                          rebuild
    python3 build_queue.py --priority other.csv     a different list
    python3 build_queue.py --status                 what is left
"""
import argparse
import csv
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue.json")
BATCH = 4  # scans per call: at 1 the overhead eats everything,
           # at 6+ the context inside a single call grows too far


def load_classes():
    """The page type of every scan, by the validated feature."""
    out = {}
    with open(os.path.join(ROOT, "page_classes.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["path"].replace("\\", "/")] = r["class"]
    return out


def already_done():
    """Scans that have been transcribed, judged by the files on disk.

    Deliberately not read out of the previous queue.json. The queue gets
    rebuilt against a different list of files, and then the old queue simply
    does not contain those scans even though their transcriptions are sitting
    there. The file on disk is the only dependable evidence of work done.
    """
    done = set()
    raw = os.path.join(ROOT, "data", "transcripts_raw")
    for dirpath, _, files in os.walk(raw):
        rel = os.path.relpath(dirpath, raw)
        for fn in files:
            if fn.endswith(".txt"):
                done.add(f"data/{rel}/{fn[:-4]}.jpg".replace(os.sep, "/"))
    return done


def show_status():
    if not os.path.exists(QUEUE):
        raise SystemExit("no queue; build one without --status")
    items = json.load(open(QUEUE, encoding="utf-8"))["items"]
    by = {}
    for it in items:
        by[it["status"]] = by.get(it["status"], 0) + 1
    print(f"  scans in the queue: {len(items)}")
    for k in ("done", "pending", "failed"):
        if by.get(k):
            print(f"    {k:<8} {by[k]}")
    print(f"  complete: {by.get('done', 0)/len(items)*100:.1f}%")
    left = [i for i in items if i["status"] == "pending"]
    if left:
        d = left[0]
        print(f"  next up: {d['opis']}/{d['delo']} sheet {d['page']} ({d['model']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--priority", default="priority.csv",
                    help="which files to transcribe, and in what order")
    args = ap.parse_args()

    if args.status:
        show_status()
        return

    classes = load_classes()
    done = already_done()
    prio = list(csv.DictReader(
        open(os.path.join(ROOT, args.priority), encoding="utf-8")))
    cat = list(csv.DictReader(
        open(os.path.join(ROOT, "catalog.csv"), encoding="utf-8")))
    by_number = {(r["opis"], r["delo"].lstrip("0")): r for r in cat}

    items = []
    for p in prio:
        row = by_number.get((p["opis"], p["delo"]))
        if not row:
            continue
        opis_dir = f"opis_{row['opis_code']}"
        delo_dir = f"delo_{row['delo']}"
        d = os.path.join(ROOT, "data", opis_dir, delo_dir)
        if not os.path.isdir(d):
            continue
        for page in sorted(x for x in os.listdir(d) if x.endswith(".jpg")):
            rel = f"data/{opis_dir}/{delo_dir}/{page}"
            cls = classes.get(rel, "hand")
            items.append({
                "opis": opis_dir, "delo": delo_dir, "page": page,
                "path": rel,
                "class": cls,
                "model": "opus" if cls == "hand" else "sonnet",
                "status": "done" if rel in done else "pending",
            })

    json.dump({"batch": BATCH, "items": items},
              open(QUEUE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by_cls, by_model = {}, {}
    for it in items:
        by_cls[it["class"]] = by_cls.get(it["class"], 0) + 1
        by_model[it["model"]] = by_model.get(it["model"], 0) + 1
    left = sum(1 for it in items if it["status"] == "pending")
    print(f"  queue: {len(items)} scans from {len(prio)} files, "
          f"priority {args.priority}")
    print(f"  by type : {by_cls}")
    print(f"  by model: {by_model}")
    print(f"  left to transcribe: {left}")


if __name__ == "__main__":
    main()
