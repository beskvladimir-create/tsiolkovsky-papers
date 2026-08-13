#!/usr/bin/env python3
"""
Чтение очереди пакетным заданием Gemini: вдвое дешевле обычного режима.

Пакетный режим берёт задание файлом и отдаёт результат в течение суток. Для
41 212 оставшихся листов это единственный способ уложиться в десятки долларов,
а не в сотни: скидка ровно 50%, замер цены в ОТЧЁТ_чем_читать.md.

Работа идёт частями. Задание уходит одним файлом, а файл ограничен 2 ГБ, тогда
как весь остаток в base64 весит около 9 ГБ даже после пережатия. Часть это
несколько тысяч листов; состояние каждой части лежит в batch_state.json, так
что прогон переживает перезапуск, обрыв связи и закрытый ноутбук.

Результат кладётся туда же, куда его кладёт ночной конвейер, по одному .txt на
скан в data/transcripts_raw/<опись>/<дело>/<лист>.txt, и подхватывается тем же
assemble.py. Лист помечается в очереди сделанным только после того, как текст
записан на диск.

    python3 batch_run.py submit --sheets 200     # отправить часть
    python3 batch_run.py collect                 # забрать готовое
    python3 batch_run.py status                  # что где стоит
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transcribe_gemini import PROMPT, encode_image, load_key

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue.json")
STATE = os.path.join(ROOT, "batch_state.json")
BASE = "https://generativelanguage.googleapis.com"

# Замерено на 12 листах, gemini-3.5-flash-lite: вход 1633 токена на лист,
# выход 559. Цена пакетного режима вдвое ниже обычной.
TOK_IN, TOK_OUT = 1633, 559
PRICE = {"gemini-3.5-flash-lite": (0.30, 2.50), "gemini-3.6-flash": (1.50, 7.50)}

# Файл задания ограничен 2 ГБ; держим запас, потому что base64 и обвязка JSON
# добавляют к скану примерно треть.
MAX_BYTES = 1_600_000_000


def req(url, data=None, headers=None, method=None, timeout=300):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.read(), dict(resp.headers)


def api(key, path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    h = {"x-goog-api-key": key, "Content-Type": "application/json"}
    try:
        out, _ = req(f"{BASE}{path}", body, h, method)
        return json.loads(out)
    except urllib.error.HTTPError as e:
        sys.exit(f"API {e.code}: {e.read().decode()[:400]}")


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"jobs": []}


def save_state(st):
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_queue():
    return json.load(open(QUEUE, encoding="utf-8"))


def save_queue(q):
    json.dump(q, open(QUEUE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cost(n, model):
    pin, pout = PRICE.get(model, PRICE["gemini-3.5-flash-lite"])
    return (n * TOK_IN / 1e6 * pin + n * TOK_OUT / 1e6 * pout) / 2


def build_jsonl(items, quality, thinking, path):
    """Строка на лист. Ключ это индекс в очереди, по нему кладём ответ."""
    written, size = [], 0
    with open(path, "w", encoding="utf-8") as f:
        for idx, it in items:
            img = encode_image(os.path.join(ROOT, it["path"]), quality)
            cfg = {"temperature": 0, "maxOutputTokens": 8192}
            if thinking:
                cfg["thinkingConfig"] = {"thinkingLevel": thinking}
            line = json.dumps({
                "key": str(idx),
                "request": {
                    "contents": [{"parts": [
                        {"text": PROMPT},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img}},
                    ]}],
                    "generationConfig": cfg,
                },
            }, ensure_ascii=False)
            if size + len(line) + 1 > MAX_BYTES and written:
                break
            f.write(line + "\n")
            size += len(line) + 1
            written.append(idx)
    return written, size


def upload(key, path):
    """Заливка файла задания по возобновляемому протоколу."""
    n = os.path.getsize(path)
    _, h = req(f"{BASE}/upload/v1beta/files",
               json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
               {"x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(n),
                "X-Goog-Upload-Header-Content-Type": "application/jsonl",
                "Content-Type": "application/json"})
    url = h.get("X-Goog-Upload-URL") or h.get("x-goog-upload-url")
    if not url:
        sys.exit("сервер не дал адрес для заливки")
    # Файл части весит сотни мегабайт. Одним запросом он рвётся на полпути
    # (broken pipe на 600 МБ), да и смысл возобновляемой заливки в том, чтобы
    # слать кусками: оборвался кусок, повторяется кусок, а не всё задание.
    # Кусок читается с упреждением: команда finalize должна уехать вместе с
    # последним куском данных. Отдельный пустой кусок в конце сервер отвергает
    # с HTTP 400, и заливка на 800 МБ пропадает целиком.
    step = 8 << 20
    sent = 0
    out = b""
    with open(path, "rb") as f:
        chunk = f.read(step)
        while chunk:
            nxt = f.read(step)
            last = not nxt
            cmd = "upload, finalize" if last else "upload"
            for attempt in range(4):
                try:
                    out, _ = req(url, chunk,
                                 {"Content-Length": str(len(chunk)),
                                  "X-Goog-Upload-Offset": str(sent),
                                  "X-Goog-Upload-Command": cmd}, timeout=900)
                    break
                except urllib.error.HTTPError as e:
                    # 400 повтором не чинится, а без тела ответа причину не
                    # видно: прошлый прогон встал именно так
                    sys.exit(f"\n    заливка отклонена на {sent/1e6:.0f} МБ, "
                             f"HTTP {e.code}: {e.read().decode()[:500]}")
                except (urllib.error.URLError, OSError) as e:
                    if attempt == 3:
                        raise
                    print(f"\n    кусок с {sent/1e6:.0f} МБ не ушёл ({e}), повтор")
                    time.sleep(3 + attempt * 5)
            sent += len(chunk)
            chunk = nxt
            print(f"\r    залито {sent/1e6:.0f} из {n/1e6:.0f} МБ", end="", flush=True)
    print()
    return json.loads(out)["file"]["name"]


def cmd_submit(args, key):
    q, st = load_queue(), load_state()
    busy = {int(i) for j in st["jobs"] if j["state"] != "collected" for i in j["keys"]}
    items = [(i, it) for i, it in enumerate(q["items"])
             if it["status"] in ("pending", "failed") and i not in busy]
    if not items:
        print("нечего отправлять: очередь пуста или всё уже в работе")
        return
    items = items[:args.sheets]

    tmp = os.path.join(ROOT, ".batch_input.jsonl")
    print(f"собираю задание на {len(items)} листов…")
    keys, size = build_jsonl(items, args.jpeg or None, args.thinking, tmp)
    print(f"  файл {size/1e6:.0f} МБ, листов {len(keys)}, "
          f"цена пакетно {cost(len(keys), args.model):.2f} $")
    if not args.yes:
        print("  (для отправки добавь --yes)")
        os.remove(tmp)
        return

    try:
        name = upload(key, tmp)
    finally:
        # иначе после обрыва на диске остаётся файл в сотни мегабайт
        if os.path.exists(tmp):
            os.remove(tmp)
    print(f"  залито: {name}")
    job = api(key, f"/v1beta/models/{args.model}:batchGenerateContent",
              {"batch": {"display_name": f"tsiolkovsky-{len(keys)}",
                         "input_config": {"file_name": name}}})
    st["jobs"].append({"name": job["name"], "keys": keys, "model": args.model,
                       "sheets": len(keys), "state": "submitted"})
    save_state(st)
    print(f"  задание принято: {job['name']}")


def write_result(q, idx, text):
    it = q["items"][int(idx)]
    out = os.path.join(ROOT, "data", "transcripts_raw", it["opis"], it["delo"])
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, it["page"].replace(".jpg", ".txt")), "w",
              encoding="utf-8") as f:
        f.write(text)
    it["status"] = "done"


def cmd_collect(args, key):
    st, q = load_state(), load_queue()
    if not st["jobs"]:
        print("отправленных заданий нет")
        return
    changed = False
    for job in st["jobs"]:
        if job["state"] == "collected":
            continue
        d = api(key, "/v1beta/" + job["name"])
        state = d.get("metadata", {}).get("state") or d.get("state", "?")
        job["state"] = state
        print(f"{job['name']}  {state}  листов {job['sheets']}")
        # сервер отвечает BATCH_STATE_*, документация обещает JOB_STATE_*:
        # сверяем по хвосту, чтобы не зависеть от того, какое из двух придёт
        if not state.endswith("SUCCEEDED"):
            continue
        # имя файла ответа лежит в двух местах и ни одно из них не dest,
        # как обещает документация: берём то, которое есть
        fname = ((d.get("response") or {}).get("responsesFile")
                 or d.get("metadata", {}).get("output", {}).get("responsesFile"))
        if not fname:
            print("  ! задание успешно, но файла ответа нет")
            continue
        raw, _ = req(f"{BASE}/download/v1beta/{fname}:download?alt=media",
                     headers={"x-goog-api-key": key}, timeout=1800)
        ok = bad = 0
        for line in raw.decode().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            idx = rec.get("key")
            resp = rec.get("response") or {}
            cand = (resp.get("candidates") or [{}])[0]
            parts = cand.get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            # обрыв по лимиту токенов молча теряет часть листа, поэтому
            # такой ответ считается провалом и лист остаётся в очереди
            if text and cand.get("finishReason") != "MAX_TOKENS":
                write_result(q, idx, text)
                ok += 1
            else:
                # Лист, который не читается, нельзя оставлять в очереди
                # бесконечно: ночной цикл 13 августа 85 раз подряд отправил
                # одни и те же два листа, потому что Gemini отвечает на них
                # RECITATION и будет отвечать так всегда. После трёх попыток
                # лист получает отказ и в очередь больше не берётся.
                it = q["items"][int(idx)]
                it["attempts"] = it.get("attempts", 0) + 1
                it["last_reason"] = cand.get("finishReason") or "пустой ответ"
                if it["attempts"] >= 3:
                    it["status"] = "refused"
                bad += 1
        job["state"] = "collected"
        changed = True   # очередь меняется и провалами: у листа растёт счётчик попыток
        print(f"  записано {ok}, провалов {bad}")
    if changed:
        save_queue(q)
    save_state(st)
    left = sum(1 for it in q["items"] if it["status"] in ("pending", "failed"))
    print(f"\nв очереди осталось {left} листов")


def cmd_status(args, key):
    st, q = load_state(), load_queue()
    left = sum(1 for it in q["items"] if it["status"] in ("pending", "failed"))
    done = sum(1 for it in q["items"] if it["status"] == "done")
    print(f"очередь: сделано {done}, осталось {left}")
    for job in st["jobs"]:
        print(f"  {job['name']:<40} {job['state']:<22} листов {job['sheets']}")
    if left:
        print(f"\nостаток пакетно: {cost(left, 'gemini-3.5-flash-lite'):.0f} $")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("submit", "collect", "status"))
    ap.add_argument("--model", default="gemini-3.5-flash-lite")
    ap.add_argument("--thinking", default="minimal")
    ap.add_argument("--jpeg", type=int, default=90,
                    help="пережатие скана; 0 отключает")
    ap.add_argument("--sheets", type=int, default=2000)
    ap.add_argument("--yes", action="store_true", help="подтвердить отправку")
    args = ap.parse_args()
    key = load_key()
    {"submit": cmd_submit, "collect": cmd_collect, "status": cmd_status}[args.command](args, key)


if __name__ == "__main__":
    main()
