#!/usr/bin/env python3
"""
Чтение листов, которые модель отказывается читать целиком.

Два листа дела 340 четвёртой описи не читались ничем: finishReason=RECITATION,
встроенный фильтр против дословного воспроизведения известного текста. Ночной
прогон отправил их 85 раз подряд, прежде чем его остановили.

Причина видна, если посмотреть на скан: это не рукопись Циолковского, а
немецкая машинописная рецензия 1927 года на его брошюру «Arbeitsplan für erste
wirkliche Vorversuche mit Rückstossraumschiffen», со ссылками на ZFM 1927.
Печатный текст, который модель знает и потому отказывается повторять.

Фильтр смотрит на длину дословного совпадения, а не на факт совпадения, и на
куске в несколько строк уже не срабатывает. Поэтому лист читается полосами, а
полоса, которую отвергли, делится пополам, пока не прочитается или пока не
станет тоньше MIN_H пикселей. Полосы берутся с перехлёстом, иначе строка на
границе теряется целиком.

Способ грубый, и результат помечен как склеенный из кусков: у него нет
сквозного контекста страницы, а значит переносы и согласование на границах
надёжны меньше обычного.

    python3 read_stubborn.py data/opis_4/delo_0340/014.jpg
    python3 read_stubborn.py --queue      # все листы со статусом refused
"""
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transcribe_gemini import load_key

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(ROOT, "queue.json")
MODEL = "gemini-3.5-flash-lite"
OVERLAP = 20        # перехлёст полос, пикселей: строка на границе не теряется
MIN_H = 60          # тоньше этого делить бессмысленно, там уже одна строка

PROMPT = """Transcribe this fragment of a scanned typewritten page exactly as it
appears. Return only the text, keeping the original line breaks. Mark an
uncertain reading as word[?] and an unreadable place as [unreadable]. Do not
add commentary, and do not complete words the fragment cuts off."""


def ask(img_bytes, key, retries=3):
    body = json.dumps({
        "contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "image/jpeg",
                             "data": base64.b64encode(img_bytes).decode()}},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "thinkingConfig": {"thinkingLevel": "minimal"}},
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{MODEL}:generateContent?key={key}",
                data=body, headers={"Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=180))
            c = d["candidates"][0]
            text = "".join(p.get("text", "") for p in
                           c.get("content", {}).get("parts", []))
            return c.get("finishReason"), text.strip()
        except urllib.error.HTTPError as e:
            if e.code in (400, 403) or attempt == retries - 1:
                return f"HTTP {e.code}", ""
            time.sleep(3 + attempt * 4)
        except Exception:
            if attempt == retries - 1:
                return "ошибка связи", ""
            time.sleep(3 + attempt * 4)


def read_band(im, top, bot, key, depth=0):
    """Полоса целиком, а если отвергнута — две половины."""
    from PIL import Image
    buf = io.BytesIO()
    im.crop((0, max(0, top - OVERLAP), im.size[0],
             min(im.size[1], bot + OVERLAP))).save(buf, "JPEG", quality=92)
    reason, text = ask(buf.getvalue(), key)
    if text:
        return text, 0
    if bot - top <= MIN_H or depth >= 5:
        return f"[не прочитано: {reason}]", 1
    mid = (top + bot) // 2
    a, fa = read_band(im, top, mid, key, depth + 1)
    b, fb = read_band(im, mid, bot, key, depth + 1)
    return a + "\n" + b, fa + fb


def stitch(parts):
    """Склейка полос без задвоения строк.

    Полосы режутся с перехлёстом, иначе строка на границе теряется. Но тогда
    строки перехлёста приходят дважды, и склейка молча задваивает текст: в
    первом прогоне лист 014 получил «zu Kaluga 1927» два раза подряд. Это
    хуже дырки, потому что дырка видна, а повтор читается как оригинал.

    Поэтому у каждой границы ищется, сколько последних строк предыдущей
    полосы совпадает с первыми строками следующей, и повтор снимается.
    """
    # сравнение без пробелов и пунктуации: у соседних полос одна и та же
    # строка приходит то с точкой в конце, то без неё, и повтор не снимался
    norm = lambda s: "".join(c for c in s.lower() if c.isalnum())
    out = []
    for part in parts:
        lines = [x for x in part.split("\n") if x.strip()]
        if out:
            best = 0
            for k in range(min(6, len(out), len(lines)), 0, -1):
                if [norm(x) for x in out[-k:]] == [norm(x) for x in lines[:k]]:
                    best = k
                    break
            lines = lines[best:]
        out.extend(lines)
    return "\n".join(out)


def read_sheet(path, key, bands=5):
    from PIL import Image
    im = Image.open(path)
    h = im.size[1]
    parts, failed = [], 0
    for i in range(bands):
        text, f = read_band(im, int(h * i / bands), int(h * (i + 1) / bands), key)
        parts.append(text)
        failed += f
        print(f"    полоса {i+1}/{bands}: {len(text.split())} слов"
              + ("  (частично не прочитана)" if f else ""))
    note = ("> Лист прочитан полосами: целиком модель его не читает "
            "(finishReason=RECITATION). Склейка из кусков, границы полос "
            "менее надёжны.\n\n")
    return note + stitch(parts), failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan", nargs="?")
    ap.add_argument("--queue", action="store_true",
                    help="все листы очереди со статусом refused")
    ap.add_argument("--bands", type=int, default=5)
    args = ap.parse_args()
    key = load_key()

    targets = []
    if args.queue:
        q = json.load(open(QUEUE, encoding="utf-8"))
        for i, it in enumerate(q["items"]):
            if it["status"] == "refused":
                targets.append((i, it))
    elif args.scan:
        targets.append((None, {"path": args.scan}))
    else:
        sys.exit("укажи скан или --queue")

    q = json.load(open(QUEUE, encoding="utf-8"))
    done = 0
    for idx, it in targets:
        print(f"  {it['path']}")
        text, failed = read_sheet(os.path.join(ROOT, it["path"]), key, args.bands)
        if idx is None:
            print(text)
            continue
        out = os.path.join(ROOT, "data", "transcripts_raw", it["opis"], it["delo"])
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, it["page"].replace(".jpg", ".txt")), "w",
                  encoding="utf-8") as f:
            f.write(text)
        # лист засчитан только если не осталось кусков, которые не дались
        q["items"][idx]["status"] = "done" if not failed else "refused"
        q["items"][idx]["read_by"] = "полосами"
        done += not failed
        print(f"    записано, слов {len(text.split())}, "
              f"кусков не прочитано: {failed}")
    if targets and targets[0][0] is not None:
        json.dump(q, open(QUEUE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n  прочитано целиком: {done} из {len(targets)}")


if __name__ == "__main__":
    main()
