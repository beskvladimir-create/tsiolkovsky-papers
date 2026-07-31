#!/usr/bin/env python3
"""Mark scans in the queue. Written through a temp file: the run gets killed."""
import json, os, sys
Q = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue.json")
status, ids = sys.argv[1], sys.argv[2:]
q = json.load(open(Q, encoding="utf-8"))
for i in ids:
    q["items"][int(i)]["status"] = status
tmp = Q + ".tmp"
json.dump(q, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
os.replace(tmp, Q)
