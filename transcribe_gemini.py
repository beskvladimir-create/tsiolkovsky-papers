#!/usr/bin/env python3
"""
Транскрипция сканов через Gemini по той же спецификации, что и остальной
конвейер (TRANSCRIPTION_SPEC.md).

Выдаёт markdown в том же формате, что и транскрипции из data/transcripts,
поэтому результат можно сразу скормить validate.py и получить измеренную
точность против опубликованного текста, а не впечатление.

Считает и печатает токены из usageMetadata, чтобы стоимость была замеренной,
а не оценённой.

    python3 transcribe_gemini.py --delo data/opis_1/delo_0033 \
        --pages 003-007 --model gemini-2.5-pro --out /tmp/g.md
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://generativelanguage.googleapis.com/v1beta/models"

PROMPT = """Ты транскрибируешь один скан рукописи К.Э. Циолковского из фонда 555 Архива РАН.

Верни ТОЛЬКО текст этого листа. Без вступления, без комментариев, без выводов,
без замечаний о качестве скана, без заголовков, которых нет на листе. Ответ,
начинающийся со слов «Вот текст» или «На этом листе», считается неверным.

Правила:
1. Сохраняй оригинальную орфографию, включая дореформенные буквы (ѣ, і, ъ на
   конце слов, ѳ). Не модернизируй написание, пунктуацию и запись чисел.
2. Сохраняй авторские переносы строк там, где они видны. Не собирай в абзацы.
3. Помечай неуверенность явно, это главное в задаче:
   слово[?]                    — чтение, в котором не уверен
   [неразборчиво]              — не смог прочитать
   [неразборчиво: N слов]      — длинный нечитаемый кусок
   ~~слово~~                   — зачёркнуто автором
   [вставка: слово]            — вписано над строкой или на полях
   [на полях: текст]           — запись на полях
   [другой почерк: текст]      — другая рука, обычно помета архивиста
   Никогда не угадывай молча. Лист с двадцатью пометками [?] это полезный
   научный результат. Гладкий текст, где сомнительные слова выдуманы,
   бесполезен и хуже пустоты: непонятно, чему верить.
4. Формулы и числа переноси как написано. Если формулу нельзя записать
   текстом, опиши в скобках: [формула: V = w·ln(M1/M2)]. Числа тут важнее
   всего, никогда не приблизительно; не разобрал цифру — ставь [?].
5. Таблицы передавай markdown-таблицей, если структура ясна, иначе построчно
   через |. Нечитаемые ячейки — [?].
6. Рисунки не воспроизводи. Пиши [рисунок: краткое описание] и транскрибируй
   подписи.
7. Пустой лист — ответ [пустой лист] и ничего больше.
"""


def load_key():
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("нет GEMINI_API_KEY в .env")


def encode_image(path, quality=None):
    """base64 скана, при quality — с пережатием.

    Сканы фонда лежат в избыточном для своего разрешения качестве: 624x845
    занимают 378 КБ. Пакетное задание отправляется целиком, поэтому объём
    заливки решает, за сколько заходов уйдёт весь остаток. Размер картинки не
    трогаем: почерк на 624 пикселях и так на пределе.
    """
    if not quality:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    from PIL import Image
    buf = io.BytesIO()
    Image.open(path).save(buf, "JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def transcribe(key, model, path, retries=4, thinking="low", quality=None):
    """Возвращает (текст, входных токенов, выходных токенов).

    У моделей Gemini 3 размышление включено по умолчанию и тратит тот же
    бюджет maxOutputTokens, что и ответ. На рукописи это не гипотеза: замер
    11 августа поймал 3 929 токенов размышления из 4 096, ответ обрывался на
    середине листа с finishReason=MAX_TOKENS, и обрубок выглядел как плохое
    чтение. Отсюда явный уровень размышления и запас по бюджету.
    """
    img = encode_image(path, quality)
    cfg = {"temperature": 0, "maxOutputTokens": 8192}
    if model.startswith("gemini-3") and thinking:
        cfg["thinkingConfig"] = {"thinkingLevel": thinking}
    body = json.dumps({
        "contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": "image/jpeg", "data": img}},
        ]}],
        # температура по умолчанию даёт разброс между прогонами, а нам нужна
        # воспроизводимость: один и тот же скан должен читаться одинаково
        "generationConfig": cfg,
    }).encode()

    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"{API}/{model}:generateContent?key={key}",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.load(r)
            cand = (d.get("candidates") or [{}])[0]
            parts = cand.get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            u = d.get("usageMetadata", {})
            # токены размышления тарифицируются как выходные, поэтому входят
            # в счёт: иначе замер цены занижен в разы
            out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
            if not text:
                last = f"пустой ответ, finishReason={cand.get('finishReason')}"
            elif cand.get("finishReason") == "MAX_TOKENS":
                # обрубок листа хуже пустоты: текст молча теряется, а чтение
                # выглядит просто плохим
                last = (f"обрыв по лимиту токенов "
                        f"(размышление {u.get('thoughtsTokenCount', 0)})")
            else:
                return text, u.get("promptTokenCount", 0), out
        except urllib.error.HTTPError as e:
            try:
                last = json.load(e)["error"].get("message", "")[:120]
            except Exception:
                last = f"HTTP {e.code}"
            if e.code in (400, 403):
                break  # не ретраим то, что не починится повтором
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 + attempt * 3)
    sys.stderr.write(f"  ! {os.path.basename(path)}: {last}\n")
    return None, 0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delo", required=True, help="папка дела, напр. data/opis_1/delo_0033")
    ap.add_argument("--pages", required=True, help="диапазон, напр. 003-007, или 003,014,015")
    ap.add_argument("--model", default="gemini-2.5-pro")
    ap.add_argument("--out", required=True)
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    if "-" in args.pages and "," not in args.pages:
        a, b = args.pages.split("-")
        pages = [f"{i:03d}" for i in range(int(a), int(b) + 1)]
    else:
        pages = [p.strip() for p in args.pages.split(",")]

    key = load_key()
    t0 = time.time()
    tin = tout = 0
    chunks = []
    for p in pages:
        path = os.path.join(ROOT, args.delo, f"{p}.jpg")
        if not os.path.exists(path):
            sys.stderr.write(f"  ! нет файла {path}\n")
            continue
        text, i, o = transcribe(key, args.model, path)
        tin += i
        tout += o
        print(f"  {p}: {o:>5} вых. токенов" + ("" if text else "  ПРОВАЛ"), flush=True)
        chunks.append(f"## Sheet {p}\n\n{text or '[не получено]'}\n")
        time.sleep(args.delay)

    header = (f"# {os.path.basename(args.delo)} — транскрипция {args.model}\n\n"
              f"> Машинная транскрипция по TRANSCRIPTION_SPEC.md. "
              f"Экспертная выверка не проводилась.\n\n---\n\n")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(header + "\n---\n\n".join(chunks))

    dt = time.time() - t0
    n = len(pages)
    print(f"\n  модель  : {args.model}")
    print(f"  листов  : {n} за {dt:.0f} с ({dt/max(n,1):.1f} с/лист)")
    print(f"  токены  : {tin} вход, {tout} выход ({tin/max(n,1):.0f} и {tout/max(n,1):.0f} на лист)")
    print(f"  файл    : {args.out}")


if __name__ == "__main__":
    main()
