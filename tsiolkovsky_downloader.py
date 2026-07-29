#!/usr/bin/env python3
"""
Скачивание оцифрованного архива К.Э. Циолковского (фонд 555, Архив РАН).
Портал: https://www.ras.ru/ktsiolkovskyarchive/

КАК УСТРОЕН ПОРТАЛ (выяснено опытным путём 29.07.2026)

Номер описи в адресе страницы декоративный: 1_actview.aspx?id=834 и
5_actview.aspx?id=834 отдают один и тот же документ. id сквозной по всему
фонду, примерно от 1 до 2050.

Настоящая опись и настоящий архивный номер дела зашиты в пути к сканам:
    /CArchive/pageimages/555\\1_033/000.jpg  ->  опись 1, дело 33
    /CArchive/pageimages/555\\4_585а/012.jpg ->  опись 3, дело 585а
Причём id портала не равен номеру дела: id 300 это дело 1_297.

Границы (двоичный поиск по id, уточнено переразметкой):
    id    1 -  595   папки 1_ и 1а_   Опись 1 и Опись 1А
    id  596 -  807   папка  2_        Опись 2
    id  808 - 1005   папка  3_        Опись 3
    id 1006 - ~2050  папка  4_        Опись 4
Опись 1А обозначена буквой в префиксе (1а_), поэтому по одним числовым
префиксам её не видно и кажется, будто описей четыре.

Свойства:
  - один проход по сквозному id, опись и номер дела берутся из HTML;
  - сохраняет в data/opis_{префикс}/delo_{номер}/{стр:03d}.jpg;
  - resume: уже скачанные валидные файлы не перекачиваются;
  - крупные сканы берутся кусками через Range (сервер режет ответ на ~130 КБ);
  - catalog.csv: опись, номер дела, id портала, название, число страниц, статус.

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

# Префикс папки со сканами и есть обозначение описи: 555\1а_012 это опись 1А,
# дело 12. Опись 1А обозначена буквой, а не цифрой, поэтому описей пять, а не
# четыре, как показалось по одним лишь числовым префиксам.
OPIS_NAME = {"1": "Опись 1", "1а": "Опись 1А", "2": "Опись 2",
             "3": "Опись 3", "4": "Опись 4"}

# минимальный валидный jpeg — по сигнатуре FFD8FF и хвосту FFD9
JPEG_SOI = b"\xff\xd8\xff"


def qurl(url):
    """Дела с буквенным номером (555\\4_585а) приходят из HTML с кириллицей в
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


def norm_delo(raw):
    """'033' -> '0033', '585а' -> '0585а'. Нули слева это padding портала,
    буквенный суффикс — часть настоящего архивного номера."""
    m = re.match(r"0*(\d+)(.*)$", raw)
    if not m:
        return raw
    return f"{int(m.group(1)):04d}{m.group(2)}"


def parse_delo(html):
    """Из HTML страницы дела достаёт название, папку со сканами и список URL.

    Папка — единственный источник правды о том, к какой описи относится дело
    и какой у него настоящий архивный номер: в адресе страницы этого нет.
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
    """Скачивает одно дело по сквозному id портала.

    Возвращает dict для каталога или None, если дела нет. Опись и номер дела
    берём из пути к сканам, а не из id: id 300 это дело 297 описи 1.
    """
    html = fetch(f"{BASE}/ktsiolkovskyarchive/1_actview.aspx?id={portal_id}")
    polite_sleep()
    if not html:
        return None

    name, opis_code, delo_no, links = parse_delo(html)
    if not links or not opis_code:
        return None  # дела нет или оно не оцифровано

    delo = norm_delo(delo_no)
    delo_dir = os.path.join(DATA, f"opis_{opis_code}", f"delo_{delo}")
    os.makedirs(delo_dir, exist_ok=True)

    saved = 0
    for page, url in enumerate(links):
        dest = os.path.join(delo_dir, f"{page:03d}.jpg")
        if os.path.exists(dest) and valid_jpeg(dest):
            saved += 1
            continue

        # три обычные попытки, потом докачка по частям: на крупных сканах
        # сервер режет ответ всегда, и повторять целиком бессмысленно
        blob = fetch(url, binary=True, retries=3)
        if not blob:
            blob = fetch_chunked(url)
        polite_sleep()
        if not blob:
            sys.stderr.write(f"  ! пропущен скан {url}\n")
            continue
        with open(dest, "wb") as f:
            f.write(blob)
        if valid_jpeg(dest):
            saved += 1
        else:
            sys.stderr.write(f"  ! битый jpeg {dest}\n")

    # "ok" только если скачаны ВСЕ листы, объявленные в HTML.
    # частично скачанное (сервер резал) -> "partial", докачается при resume.
    status = "empty" if not saved else ("ok" if saved == len(links) else "partial")
    return {"opis": OPIS_NAME.get(opis_code, f"опись {opis_code}"),
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
    """Пишем через временный файл: процесс регулярно убивают при засыпании
    ноутбука, оборванная запись испортила бы каталог."""
    tmp = CATALOG + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, CATALOG)


def upsert_catalog(row):
    """Пишет дело в каталог, заменяя прежнюю строку. Ключ — id портала: он
    уникален и стабилен, в отличие от пары (опись, дело), которую мы узнаём
    только после запроса."""
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
    """Один проход по сквозному id. Описи не перебираем: их не существует как
    отдельных пространств id, они определяются папкой со сканами."""
    done = done_ids()
    print(f"=== фонд 555, id {id_from}..{id_to} ===", flush=True)
    misses = 0
    total_delos = total_pages = 0
    for pid in range(id_from, id_to + 1):
        if str(pid) in done:
            continue
        row = download_delo(pid)
        if row is None:
            misses += 1
            if misses >= miss_stop:
                print(f"  подряд {misses} несуществующих id -> конец фонда на {pid}",
                      flush=True)
                break
            continue
        misses = 0
        upsert_catalog(row)
        total_delos += 1
        total_pages += row["pages"]
        print(f"  id {pid} = {row['opis']} д.{row['delo']}: "
              f"{row['pages']}/{row['expected']} стр. | {row['name'][:60]}", flush=True)
    print(f"--- итог прохода: {total_delos} дел, {total_pages} страниц ---", flush=True)


def redo_incomplete():
    """До-качивает дела со статусом partial/empty. Сервер РАН нестабилен,
    поэтому вызывать проходами, пока все не станут ok."""
    rows = read_catalog()
    todo = [r for r in rows if r.get("status") in ("partial", "empty")]
    if not todo:
        print("неполных дел нет — всё ok")
        return 0
    print(f"до-качиваю {len(todo)} неполных дел", flush=True)
    fixed = 0
    for r in todo:
        new = download_delo(int(r["portal_id"]))
        if new is None:
            continue
        upsert_catalog(new)
        if new["status"] == "ok":
            fixed += 1
        print(f"  {new['opis']} д.{new['delo']}: "
              f"{new['pages']}/{new['expected']} л. [{new['status']}]", flush=True)
    print(f"вылечено до ok: {fixed} из {len(todo)}", flush=True)
    return len(todo) - fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="id_from", type=int, default=1)
    ap.add_argument("--to", dest="id_to", type=int, default=2200,
                    help="id-пространство фонда кончается примерно на 2050")
    ap.add_argument("--miss-stop", type=int, default=60,
                    help="сколько несуществующих id подряд считать концом фонда")
    ap.add_argument("--only", type=int, default=None, help="одно дело по id портала")
    ap.add_argument("--redo-incomplete", action="store_true")
    ap.add_argument("--heal-passes", type=int, default=8,
                    help="проходов долечивания после основного")
    ap.add_argument("--delay", type=float, nargs=2, metavar=("MIN", "MAX"),
                    default=[0.5, 1.0], help="пауза между запросами, сек")
    args = ap.parse_args()

    global DELAY_MIN, DELAY_MAX
    DELAY_MIN, DELAY_MAX = args.delay
    os.makedirs(DATA, exist_ok=True)

    if args.redo_incomplete:
        sys.exit(0 if redo_incomplete() == 0 else 3)

    if args.only is not None:
        row = download_delo(args.only)
        if row is None:
            print("дела нет")
        else:
            upsert_catalog(row)
            print(f"id {args.only} = {row['opis']} д.{row['delo']}: "
                  f"{row['pages']}/{row['expected']} стр. | {row['name']}")
        return

    run_fond(args.id_from, args.id_to, args.miss_stop)
    for p in range(1, args.heal_passes + 1):
        left = redo_incomplete()
        if left == 0:
            break
        print(f"проход долечивания {p}, осталось {left}", flush=True)
        time.sleep(60)
    print("\n===== ФОНД 555 ОБРАБОТАН =====", flush=True)


if __name__ == "__main__":
    main()
