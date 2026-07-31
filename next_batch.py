#!/usr/bin/env python3
"""Emit the next batch of scans for one model.

Page types alternate within a file, so consecutive scans routed to the same
model are often a single page — and a call for one page is all overhead. The
batch is therefore drawn from scans of the same model within one archival
file, skipping over pages of the other type.
"""
import json, os, sys
Q = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue.json")
q = json.load(open(Q, encoding="utf-8"))
items = q["items"]

first = next((i for i, it in enumerate(items) if it["status"] == "pending"), None)
if first is None:
    sys.exit(0)
model = items[first]["model"]
delo = (items[first]["opis"], items[first]["delo"])

batch = []
for i, it in enumerate(items):
    if it["status"] != "pending" or it["model"] != model:
        continue
    if (it["opis"], it["delo"]) != delo:
        break          # file finished; the next batch starts the next one
    batch.append({"id": str(i), "path": it["path"]})
    if len(batch) >= q["batch"]:
        break
json.dump({"model": model, "items": batch}, sys.stdout, ensure_ascii=False)
