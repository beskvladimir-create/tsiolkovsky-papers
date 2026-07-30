#!/usr/bin/env python3
"""
Retrieval of the digitised K.E. Tsiolkovsky archive (fond 555, Archive of the
Russian Academy of Sciences). Portal: https://www.ras.ru/ktsiolkovskyarchive/

HOW THE PORTAL IS ACTUALLY ORGANISED (established empirically, 29 July 2026)

The inventory number in a page address is decorative: 1_actview.aspx?id=834
and 5_actview.aspx?id=834 return the same document. The id is a single
sequence across the whole fond, running from 1 to about 2050.

The real inventory ("opis") and the real archival file number ("delo") appear
only inside the scan paths:

    /CArchive/pageimages/555\\1_033/000.jpg   ->  opis 1,  file 33
    /CArchive/pageimages/555\\4_585a/012.jpg  ->  opis 4,  file 585a

The portal id is not the file number either: id 300 is file 1_297. The two
drift apart because files with letter suffixes (145a, 077b, 585a — 31 of them)
occupy an id without advancing the numeric sequence.

Boundaries, found by binary search over the id space and confirmed against the
completed catalogue:

    id    1 -  595   folders 1_ and 1а_   Опись 1 (568) and Опись 1А (24)
    id  596 -  807   folder  2_           Опись 2 (212)
    id  808 - 1005   folder  3_           Опись 3 (198)
    id 1006 - ~2050  folder  4_           Опись 4 (1017)

Опись 1А carries a letter in its prefix (1а_), so looking only at numeric
prefixes suggests there are four inventories when there are five.

Behaviour:
  - one pass over the id space; inventory and file number come from the HTML
  - saves to data/opis_{prefix}/delo_{number}/{page:03d}.jpg
  - resumable: files already on disk and structurally valid are not refetched
  - oversized scans are fetched in ranged chunks (the server truncates
    responses at about 130 KB)
  - maintains catalog.csv: inventory, file number, portal id, title, page
    count, status

One request at a time, never in parallel: this is a public archive's server.
"""
import csv
import http.client
import os
import random
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse

BASE = "https://www.ras.ru"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 archive-research/1.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CATALOG = os.path.join(ROOT, "catalog.csv")

# The scan folder's prefix is the inventory designation: 555\1а_012 is
# Опись 1А, file 12. Values stay in Russian because they are the archival
# designations that go into the catalogue.
OPIS_NAME = {"1": "Опись 1", "1а": "Опись 1А", "2": "Опись 2",
             "3": "Опись 3", "4": "Опись 4"}

# A JPEG is considered intact if it opens with FFD8FF and ends with FFD9.
JPEG_SOI = b"\xff\xd8\xff"


def qurl(url):
    """Percent-encode a URL that may contain Cyrillic.

    Files with letter suffixes (555\\4_585а) come out of the HTML with
    Cyrillic in the path. urllib encodes URLs as ascii and raises, so the
    encoding is done here instead. % stays in the safe set so an already
    encoded %5C is not encoded a second time.
    """
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def fetch(url, binary=False, retries=10):
    """GET with retries.

    The server is unreliable: roughly a third of requests fail with a 500 and
    then serve the same URL correctly on the next attempt. So 500s and network
    errors are retried persistently; only a 404 means the object is genuinely
    absent.
    """
    url = qurl(url)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # not there; do not retry
            last = e
        except http.client.IncompleteRead as e:
            # The file is over the truncation threshold. Retrying the whole
            # thing just gets it truncated again, so hand off to fetch_chunked.
            if binary:
                sys.stderr.write(f"  ~ truncated: {url} — fetching in chunks\n")
                return None
            last = e
        except Exception as e:
            last = e
        # Backoff with jitter, kept short: these are momentary faults, not
        # rate limiting.
        time.sleep(min(1.0 + attempt * 0.7, 6.0) + random.uniform(0, 0.5))
    sys.stderr.write(f"  ! could not fetch {url}: {last}\n")
    return None


CHUNK = 100_000  # below the ~130 KB point at which the server truncates


def fetch_chunked(url, retries=6):
    """Fetch a large file in ranged chunks and reassemble it.

    The server truncates large responses at about 130 KB: small scans arrive
    whole, while scans of 800 KB and up fail with IncompleteRead however many
    times they are retried. It does honour Accept-Ranges, so the file is taken
    in pieces below the truncation point. Returns bytes, or None on failure.
    """
    url = qurl(url)
    buf, total = b"", None
    # No separate HEAD request: the server 500s on roughly a third of calls,
    # and an extra un-retried point of failure would sink the whole download.
    # The full size arrives in Content-Range on the first chunk instead.
    while total is None or len(buf) < total:
        end = len(buf) + CHUNK - 1
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA, "Range": f"bytes={len(buf)}-{end}"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    part = r.read()
                    status = r.status
                    m = re.match(r"bytes\s+\d+-\d+/(\d+)",
                                 r.headers.get("Content-Range", ""))
                if status != 206 or not m:
                    return None  # ranges not honoured for this object
                total = int(m.group(1))
                if part:
                    buf += part
                    break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
            except Exception:
                pass
            time.sleep(min(1.0 + attempt * 0.7, 5.0) + random.uniform(0, 0.4))
        else:
            sys.stderr.write(f"  ! chunk {len(buf)}-{end} failed: {url}\n")
            return None
        time.sleep(random.uniform(0.15, 0.35))
    return buf


# Pause between requests; overridden by --delay.
DELAY_MIN, DELAY_MAX = 0.5, 1.0


def polite_sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def norm_delo(raw):
    """'033' -> '0033', '585а' -> '0585а'.

    Leading zeros are the portal's padding; a letter suffix is part of the
    real archival number and is kept.
    """
    m = re.match(r"0*(\d+)(.*)$", raw)
    if not m:
        return raw
    return f"{int(m.group(1)):04d}{m.group(2)}"


def parse_delo(html):
    """Extract the title, the scan folder and the scan URLs from a file's page.

    The folder is the only source of truth for which inventory a file belongs
    to and what its real archival number is — neither appears in the page
    address. The patterns match the portal's Russian markup and so stay in
    Russian.
    """
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    name = ""
    m = re.search(r"Название:\s*(.+?)(?:Крайние даты|Количество (?:дел|листов)|Даты|$)", text)
    if m:
        name = m.group(1).strip().strip('"').strip()

    raw = re.findall(r"/CArchive/pageimages/[^\"'> ]+?\.jpg", html, re.I)
    seen, links, folder = set(), [], None
    for p in raw:
        if p in seen:
            continue
        seen.add(p)
        if folder is None:
            f = re.search(r"/pageimages/555\\([^/\"'> ]+)/", p)
            if f:
                folder = f.group(1)
        links.append(BASE + p.replace("\\", "%5C"))

    opis_code, delo_no = (None, None)
    if folder and "_" in folder:
        opis_code, delo_no = folder.split("_", 1)
    return name, opis_code, delo_no, links


def valid_jpeg(path):
    try:
        if os.path.getsize(path) < 1024:
            return False
        with open(path, "rb") as f:
            if f.read(3) != JPEG_SOI:
                return False
            f.seek(-2, os.SEEK_END)
            return f.read(2) == b"\xff\xd9"
    except Exception:
        return False


def download_delo(portal_id):
    """Retrieve one file by its portal id.

    Returns a catalogue row, or None if there is no such file. The inventory
    and file number come from the scan paths rather than from the id: id 300
    is file 297 of opis 1.
    """
    html = fetch(f"{BASE}/ktsiolkovskyarchive/1_actview.aspx?id={portal_id}")
    polite_sleep()
    if not html:
        return None

    name, opis_code, delo_no, links = parse_delo(html)
    if not links or not opis_code:
        return None  # no such file, or it has not been digitised

    delo = norm_delo(delo_no)
    delo_dir = os.path.join(DATA, f"opis_{opis_code}", f"delo_{delo}")
    os.makedirs(delo_dir, exist_ok=True)

    saved = 0
    for page, url in enumerate(links):
        dest = os.path.join(delo_dir, f"{page:03d}.jpg")
        if os.path.exists(dest) and valid_jpeg(dest):
            saved += 1
            continue

        # Three ordinary attempts, then the chunked path: on large scans the
        # server truncates every time, so repeating the whole request is waste.
        blob = fetch(url, binary=True, retries=3)
        if not blob:
            blob = fetch_chunked(url)
        polite_sleep()
        if not blob:
            sys.stderr.write(f"  ! skipped scan {url}\n")
            continue
        with open(dest, "wb") as f:
            f.write(blob)
        if valid_jpeg(dest):
            saved += 1
        else:
            sys.stderr.write(f"  ! malformed jpeg {dest}\n")

    # "ok" only when every scan declared in the HTML arrived. A partial result
    # is recorded as such and completed on a later pass.
    status = "empty" if not saved else ("ok" if saved == len(links) else "partial")
    return {"opis": OPIS_NAME.get(opis_code, f"opis {opis_code}"),
            "opis_code": opis_code, "delo": delo, "portal_id": portal_id,
            "name": name, "pages": saved, "expected": len(links),
            "status": status}


FIELDS = ["opis", "opis_code", "delo", "portal_id", "name",
          "pages", "expected", "status"]


def read_catalog():
    if not os.path.exists(CATALOG):
        return []
    with open(CATALOG, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_catalog(rows):
    """Write through a temporary file.

    The process is killed regularly when the machine sleeps, and a torn write
    would corrupt the catalogue.
    """
    tmp = CATALOG + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, CATALOG)


def upsert_catalog(row):
    """Write a file's row, replacing any earlier one.

    Keyed on the portal id: it is unique and known before the request, unlike
    the (inventory, file number) pair, which is only discovered afterwards.
    """
    rows = read_catalog()
    clean = {k: str(row.get(k, "")) for k in FIELDS}
    for i, r in enumerate(rows):
        if r.get("portal_id") == str(row["portal_id"]):
            rows[i] = clean
            break
    else:
        rows.append(clean)
    write_catalog(rows)


def done_ids():
    return {r["portal_id"] for r in read_catalog() if r.get("status") == "ok"}


def run_fond(id_from, id_to, miss_stop):
    """One pass over the id space.

    Inventories are not iterated: they do not exist as separate id spaces and
    are determined by the scan folder.
    """
    done = done_ids()
    print(f"=== fond 555, id {id_from}..{id_to} ===", flush=True)
    misses = 0
    total_delos = total_pages = 0
    for pid in range(id_from, id_to + 1):
        if str(pid) in done:
            continue
        row = download_delo(pid)
        if row is None:
            misses += 1
            if misses >= miss_stop:
                print(f"  {misses} missing ids in a row -> end of fond at {pid}",
                      flush=True)
                break
            continue
        misses = 0
        upsert_catalog(row)
        total_delos += 1
        total_pages += row["pages"]
        print(f"  id {pid} = {row['opis']} d.{row['delo']}: "
              f"{row['pages']}/{row['expected']} scans | {row['name'][:60]}", flush=True)
    print(f"--- pass complete: {total_delos} files, {total_pages} scans ---", flush=True)


def redo_incomplete():
    """Complete files left partial or empty.

    The server is unreliable enough that this needs calling in passes until
    everything reaches ok.
    """
    rows = read_catalog()
    todo = [r for r in rows if r.get("status") in ("partial", "empty")]
    if not todo:
        print("no incomplete files — all ok")
        return 0
    print(f"completing {len(todo)} incomplete files", flush=True)
    fixed = 0
    for r in todo:
        new = download_delo(int(r["portal_id"]))
        if new is None:
            continue
        upsert_catalog(new)
        if new["status"] == "ok":
            fixed += 1
        print(f"  {new['opis']} d.{new['delo']}: "
              f"{new['pages']}/{new['expected']} scans [{new['status']}]", flush=True)
    print(f"brought to ok: {fixed} of {len(todo)}", flush=True)
    return len(todo) - fixed


def main():
    ap = argparse.ArgumentParser(
        description="Retrieve fond 555 (K.E. Tsiolkovsky) from the Archive of "
                    "the Russian Academy of Sciences.")
    ap.add_argument("--from", dest="id_from", type=int, default=1)
    ap.add_argument("--to", dest="id_to", type=int, default=2200,
                    help="the fond's id space ends at about 2050")
    ap.add_argument("--miss-stop", type=int, default=60,
                    help="how many missing ids in a row mean the end of the fond")
    ap.add_argument("--only", type=int, default=None,
                    help="retrieve a single file by portal id")
    ap.add_argument("--redo-incomplete", action="store_true",
                    help="complete files left partial or empty")
    ap.add_argument("--heal-passes", type=int, default=8,
                    help="completion passes to run after the main pass")
    ap.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"),
                    default=[0.5, 1.0], help="pause between requests, seconds")
    args = ap.parse_args()

    global DELAY_MIN, DELAY_MAX
    DELAY_MIN, DELAY_MAX = args.delay
    os.makedirs(DATA, exist_ok=True)

    if args.redo_incomplete:
        sys.exit(0 if redo_incomplete() == 0 else 3)

    if args.only is not None:
        row = download_delo(args.only)
        if row is None:
            print("no such file")
        else:
            upsert_catalog(row)
            print(f"id {args.only} = {row['opis']} d.{row['delo']}: "
                  f"{row['pages']}/{row['expected']} scans | {row['name']}")
        return

    run_fond(args.id_from, args.id_to, args.miss_stop)
    for p in range(1, args.heal_passes + 1):
        left = redo_incomplete()
        if left == 0:
            break
        print(f"completion pass {p}, {left} still incomplete", flush=True)
        time.sleep(60)
    print("\n===== FOND 555 COMPLETE =====", flush=True)


if __name__ == "__main__":
    main()
