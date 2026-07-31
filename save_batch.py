#!/usr/bin/env python3
"""Split the model's reply into one .txt per scan, beside its archival file."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
q = json.load(open(os.path.join(ROOT, "queue.json"), encoding="utf-8"))
ids = sys.argv[1:]
resp = sys.stdin.read()
parts = re.split(r"^===\s*([^=\n]+?)\s*===\s*$", resp, flags=re.M)
by_name = {}
for k in range(1, len(parts) - 1, 2):
    by_name[parts[k].strip()] = parts[k + 1].strip()
saved = 0
for i in ids:
    it = q["items"][int(i)]
    out = os.path.join(ROOT, "data", "transcripts_raw", it["opis"], it["delo"])
    os.makedirs(out, exist_ok=True)
    key = next((k for k in by_name if it["page"] in k), None)
    text = by_name.get(key, "") if key else ""
    if not text and len(by_name) == 1 and len(ids) == 1:
        text = next(iter(by_name.values()))
    with open(os.path.join(out, it["page"].replace(".jpg", ".txt")), "w", encoding="utf-8") as f:
        f.write(text)
    saved += 1 if text else 0
print(f"    saved {saved} of {len(ids)}", file=sys.stderr)
