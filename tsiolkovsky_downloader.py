#!/usr/bin/env python3
"""
Скачивание оцифрованного архива К.Э. Циолковского (фонд 555, Архив РАН).
Портал: https://www.ras.ru/ktsiolkovskyarchive/

Описи (номер в URL = страница описи):
  1 -> Опись 1,  2 -> Опись 1А,  3 -> Опись 2,  4 -> Опись 3,  5 -> Опись 4

Свойства:
  - парсит страницу дела, берёт реальные ссылки на сканы; если их нет -> шаблон пути (fallback);
  - сохраняет в data/opis_{N}/delo_{ID:04d}/{page:03d}.jpg;
  - resume: уже скачанные валидные файлы не перекачивает;
  - пауза 0.5-1 c между запросами, ретраи при сбоях;
  - catalog.csv: опись, номер дела, название, число страниц, статус;
  - несуществующие id дел пропускает.

Одна закачка за раз (без параллельных запросов) — это государственный портал.
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

OPIS_NAME = {1: "Опись 1", 2: "Опись 1А", 3: "Опись 2", 4: "Опись 3", 5: "Опись 4"}

# минимальный валидный jpeg — по сигнатуре FFD8FF и хвосту FFD9
JPEG_SOI = b"\xff\xd8\xff"


def qurl(url):
    """Дела с буквенным номером (555\\1_145а) приходят из HTML с кириллицей в
    пути; urllib кодирует URL в ascii и падает, поэтому квотим сами. % в safe,
    чтобы уже готовый %5C не закодировался повторно."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def fetch(url, binary=False, retries=10):
    """GET c ретраями. Сервер РАН нестабилен: ~треть запросов падает в 500,
    но со следующей попытки отдаёт целый файл. Поэтому 500/сеть ретраим упорно,
    только 404 = реального объекта нет."""
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
                return None  # объекта нет — не ретраим
            last = e
        except http.client.IncompleteRead as e:
            # обрыв на крупном файле: повторять целиком бесполезно, сервер
            # обрежет и следующий ответ. Пусть вызывающий идёт в fetch_chunked.
            if binary:
                sys.stderr.write(f"  ~ обрыв на {url}, беру по частям\n")
                return None
            last = e
        except Exception as e:
            last = e
        # бэкофф с джиттером, но не слишком длинный (сбой мгновенный, не бан)
        time.sleep(min(1.0 + attempt * 0.7, 6.0) + random.uniform(0, 0.5))
    sys.stderr.write(f"  ! не удалось получить {url}: {last}\n")
    return None


CHUNK = 100_000  # ниже порога, на котором сервер обрывает ответ (~130 КБ)


def fetch_chunked(url, retries=6):
    """Докачка крупного файла по частям.

    Сервер РАН обрывает большие ответы примерно на 130 КБ: мелкие сканы
    приходят целиком, а листы по 800 КБ падают в IncompleteRead сколько ни
    повторяй. При этом сервер отдаёт Accept-Ranges: bytes, поэтому берём файл
    кусками ниже порога обрыва и склеиваем. Возвращает bytes или None.
    """
    url = qurl(url)
    buf, total = b"", None
    # HEAD отдельным запросом не делаем: сервер сыпет 500 примерно на трети
    # обращений, и лишняя точка отказа роняет всю докачку. Полный размер
    # приходит в Content-Range первого же куска.
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
                    return None  # Range не поддержан для этого объекта
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
            sys.stderr.write(f"  ! кусок {len(buf)}-{end} не взялся: {url}\n")
            return None
        time.sleep(random.uniform(0.15, 0.35))
    return buf


# пауза между запросами; переопределяется из --delay
DELAY_MIN, DELAY_MAX = 0.5, 1.0


def polite_sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def parse_delo(html, opis):
    """Из HTML страницы дела достаёт название и список URL сканов (в порядке)."""
    name = ""
    # снимаем теги, потом ищем поле «Название:» в чистом тексте
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"Название:\s*(.+?)(?:Крайние даты|Количество (?:дел|листов)|Даты|$)", text)
    if m:
        name = m.group(1).strip().strip('"').strip()

    # реальные ссылки на сканы (бэкслэш в HTML)
    raw = re.findall(r"/CArchive/pageimages/[^\"'> ]+?\.jpg", html, re.I)
    seen, links = set(), []
    for p in raw:
        if p not in seen:
            seen.add(p)
            links.append(BASE + p.replace("\\", "%5C"))
    return name, links


def template_urls(opis, delo_id, count):
    folder = f"555%5C{opis}_{delo_id:03d}"
    return [f"{BASE}/CArchive/pageimages/{folder}/{p:03d}.jpg" for p in range(count)]


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


def download_delo(opis, delo_id):
    """Скачивает одно дело. Возвращает dict для каталога или None если дела нет."""
    delo_dir = os.path.join(DATA, f"opis_{opis}", f"delo_{delo_id:04d}")
    html = fetch(f"{BASE}/ktsiolkovskyarchive/{opis}_actview.aspx?id={delo_id}")
    polite_sleep()

    name, links = ("", [])
    if html:
        name, links = parse_delo(html, opis)

    # если ссылок в HTML нет — пробуем шаблон: качаем пока идут 000,001,...
    from_template = False
    if not links:
        # пробный первый файл; если нет — дело отсутствует
        probe = template_urls(opis, delo_id, 1)[0]
        first = fetch(probe, binary=True)
        polite_sleep()
        if not first:
            return None  # дела нет
        from_template = True

    os.makedirs(delo_dir, exist_ok=True)
    saved = 0
    page = 0
    while True:
        if not from_template:
            if page >= len(links):
                break
            url = links[page]
        else:
            url = template_urls(opis, delo_id, page + 1)[page]

        dest = os.path.join(delo_dir, f"{page:03d}.jpg")
        if os.path.exists(dest) and valid_jpeg(dest):
            saved += 1
            page += 1
            continue

        # три обычные попытки, потом докачка по частям: на крупных сканах
        # сервер режет ответ всегда, и повторять целиком бессмысленно
        blob = fetch(url, binary=True, retries=3)
        if not blob:
            blob = fetch_chunked(url)
        polite_sleep()
        if not blob:
            if from_template:
                break  # шаблон исчерпан
            else:
                sys.stderr.write(f"  ! пропущен скан {url}\n")
                page += 1
                continue
        with open(dest, "wb") as f:
            f.write(blob)
        if valid_jpeg(dest):
            saved += 1
        else:
            sys.stderr.write(f"  ! битый jpeg {dest}\n")
        page += 1

    # "ok" только если скачаны ВСЕ листы, объявленные в HTML.
    # частично скачанное (сервер резал) -> "partial", докачается при resume.
    if not saved:
        status = "empty"
    elif not from_template and saved < len(links):
        status = "partial"
    else:
        status = "ok"
    expected = len(links) if not from_template else saved
    return {"opis": OPIS_NAME.get(opis, opis), "opis_page": opis,
            "delo": delo_id, "name": name, "pages": saved,
            "expected": expected, "status": status}


def load_done_catalog():
    done = set()
    if os.path.exists(CATALOG):
        with open(CATALOG, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "ok":
                    done.add((int(row["opis_page"]), int(row["delo"])))
    return done


def append_catalog(row):
    new = not os.path.exists(CATALOG)
    with open(CATALOG, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["opis", "opis_page", "delo", "name", "pages", "expected", "status"])
        if new:
            w.writeheader()
        w.writerow(row)


def run_opis(opis, id_from, id_to, miss_stop):
    done = load_done_catalog()
    print(f"=== {OPIS_NAME.get(opis, opis)} (страница {opis}), id {id_from}..{id_to} ===", flush=True)
    misses = 0
    total_delos = total_pages = 0
    for delo_id in range(id_from, id_to + 1):
        if (opis, delo_id) in done:
            print(f"  дело {delo_id}: уже в каталоге, пропуск", flush=True)
            continue
        row = download_delo(opis, delo_id)
        if row is None:
            misses += 1
            if misses >= miss_stop:
                print(f"  подряд {misses} несуществующих id -> конец описи на {delo_id}", flush=True)
                break
            continue
        misses = 0
        append_catalog(row)
        total_delos += 1
        total_pages += row["pages"]
        print(f"  дело {delo_id}: {row['pages']} стр. | {row['name'][:70]}", flush=True)
    print(f"--- итог: {total_delos} дел, {total_pages} страниц ---", flush=True)


def rewrite_catalog(rows):
    with open(CATALOG, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["opis", "opis_page", "delo", "name", "pages", "expected", "status"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})


def redo_incomplete(opis_filter=None):
    """До-качивает дела со статусом partial/empty. Сервер РАН нестабилен,
    поэтому вызывать проходами, пока все не станут ok."""
    if not os.path.exists(CATALOG):
        print("каталога нет"); return 0
    rows = list(csv.DictReader(open(CATALOG, encoding="utf-8")))
    todo = [r for r in rows if r["status"] in ("partial", "empty")
            and (opis_filter is None or int(r["opis_page"]) == opis_filter)]
    if not todo:
        print("неполных дел нет — всё ok"); return 0
    print(f"до-качиваю {len(todo)} неполных дел", flush=True)
    fixed = 0
    for r in todo:
        op, did = int(r["opis_page"]), int(r["delo"])
        new = download_delo(op, did)
        if new is None:
            continue
        # обновляем строку в каталоге
        for i, x in enumerate(rows):
            if int(x["opis_page"]) == op and int(x["delo"]) == did:
                rows[i] = new
                break
        rewrite_catalog(rows)
        mark = "ok" if new["status"] == "ok" else new["status"]
        if new["status"] == "ok":
            fixed += 1
        print(f"  дело {did}: {new['pages']}/{new.get('expected','?')} л. [{mark}]", flush=True)
    print(f"вылечено до ok: {fixed} из {len(todo)}", flush=True)
    return len(todo) - fixed  # осталось неполных


def run_full(id_to, miss_stop, heal_passes=8):
    """Весь фонд: описи 1..5, каждая = основной проход + циклическое долечивание.
    Один процесс (переживает nohup). Сервер РАН нестабилен, но скорость его не
    банит — дыры добиваем повторами."""
    for opis in (1, 2, 3, 4, 5):
        print(f"\n########## ОПИСЬ {OPIS_NAME[opis]} (страница {opis}) ##########", flush=True)
        run_opis(opis, 1, id_to, miss_stop)
        for p in range(1, heal_passes + 1):
            left = redo_incomplete(opis)
            if left == 0:
                break
            print(f"опись {opis}: проход долечивания {p}, осталось {left}", flush=True)
            time.sleep(60)
        print(f"########## ОПИСЬ {opis} готова ##########", flush=True)
    print("\n===== ВЕСЬ ФОНД 555 ОБРАБОТАН =====", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opis", type=int, default=1, help="номер страницы описи 1..5")
    ap.add_argument("--from", dest="id_from", type=int, default=1)
    ap.add_argument("--to", dest="id_to", type=int, default=600)
    ap.add_argument("--miss-stop", type=int, default=40,
                    help="сколько несуществующих id подряд считать концом описи")
    ap.add_argument("--only", type=int, default=None, help="скачать одно дело по id")
    ap.add_argument("--redo-incomplete", action="store_true",
                    help="до-качать дела со статусом partial/empty")
    ap.add_argument("--full", action="store_true",
                    help="весь фонд: описи 1..5 с долечиванием, один процесс")
    ap.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"),
                    default=[0.5, 1.0], help="пауза между запросами, сек (мин макс)")
    args = ap.parse_args()

    global DELAY_MIN, DELAY_MAX
    DELAY_MIN, DELAY_MAX = args.delay
    os.makedirs(DATA, exist_ok=True)
    if args.full:
        run_full(args.id_to, args.miss_stop)
        return
    if args.redo_incomplete:
        left = redo_incomplete(args.opis if args.opis else None)
        sys.exit(0 if left == 0 else 3)
    if args.only is not None:
        row = download_delo(args.opis, args.only)
        if row is None:
            print("дела нет")
        else:
            append_catalog(row)
            print(f"дело {args.only}: {row['pages']} стр. | {row['name']}")
        return
    run_opis(args.opis, args.id_from, args.id_to, args.miss_stop)


if __name__ == "__main__":
    main()
