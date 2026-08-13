#!/usr/bin/env python3
"""
Страница фактов в том виде, в каком её откроет журналист.

`ФАКТЫ.md` написан для нас: markdown читают разработчики, а редакция получает
письмо и не станет разбираться с расширением файла. Поэтому та же страница
собирается ещё дважды: html для сайта, чтобы дать ссылку, и pdf во вложение,
чтобы её открыли не глядя.

Источник один, `ФАКТЫ.md`. Числа в нём считаются скриптами и правятся там же:
две копии одной страницы, расходящиеся в цифрах, — ровно тот сорт ошибки,
из-за которого в проекте появился `check_paper.py`.

Требуется pandoc. PDF печатает Chrome в headless-режиме: cupsfilter на этой
системе html не берёт («No filter to convert from text/html»), а ставить
LaTeX ради одной страницы незачем.

    python3 build_facts.py
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "ФАКТЫ.md")
HTML = os.path.join(ROOT, "docs", "facts.html")
PDF = os.path.join(ROOT, "docs", "tsiolkovsky-facts.pdf")

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 15px/1.55 Georgia, "Times New Roman", serif; color: #1a1a1a;
       max-width: 44em; margin: 0 auto; padding: 24px 20px 60px; }
h1 { font-size: 26px; line-height: 1.2; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 32px 0 10px; padding-top: 14px;
     border-top: 1px solid #ddd; }
h1 + p { color: #555; margin-top: 0; }
table { border-collapse: collapse; margin: 14px 0; width: 100%; }
th, td { border: 1px solid #d5d5d5; padding: 6px 10px; text-align: left;
         font-size: 14px; }
th { background: #f4f4f4; }
td:nth-child(2) { white-space: nowrap; }
code { background: #f4f4f4; padding: 1px 4px; font-size: 13px; }
a { color: #14507d; }
strong { color: #000; }
hr { border: 0; border-top: 1px solid #ddd; margin: 26px 0; }
blockquote { margin: 12px 0; padding-left: 14px; border-left: 3px solid #ccc;
             color: #444; }
@media print { a { color: #000; text-decoration: none; } body { padding: 0; } }
"""


def main():
    if not shutil.which("pandoc"):
        sys.exit("нужен pandoc")
    os.makedirs(os.path.dirname(HTML), exist_ok=True)

    css_path = os.path.join(ROOT, ".facts.css")
    open(css_path, "w", encoding="utf-8").write(CSS)
    try:
        # без --metadata title: pandoc печатает его как <h1> в теле, и
        # заголовок задваивается с тем, что уже есть в markdown
        subprocess.run(
            ["pandoc", SRC, "-f", "gfm", "-t", "html5", "-s",
             "--metadata", "title=", "--metadata", "lang=ru",
             "-c", "", "-o", HTML],
            check=True, capture_output=True)
    finally:
        pass

    # вставляем стиль внутрь: страница должна открываться из вложения и с
    # диска, а не только с сайта
    html = open(HTML, encoding="utf-8").read()
    html = html.replace('<link rel="stylesheet" href="" />',
                        f"<style>{CSS}</style>")
    if "<style>" not in html:
        html = html.replace("</head>", f"<style>{CSS}</style>\n</head>")
    html = re.sub(r'<h1 class="title">\s*</h1>\s*', "", html)
    # pandoc подставляет в <title> имя файла («ФАКТЫ»), а это то, что видно
    # во вкладке браузера и в списке вложений
    html = re.sub(r"<title>.*?</title>",
                  "<title>Архив Циолковского: измеренные факты</title>", html)
    open(HTML, "w", encoding="utf-8").write(html)
    os.remove(css_path)
    print(f"  {os.path.relpath(HTML, ROOT)}  {os.path.getsize(HTML)/1024:.0f} КБ")

    chrome = next((p for p in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("chromium") or "") if p and os.path.exists(p)), None)
    if not chrome:
        print("  Chrome не найден: pdf печатать из браузера")
        return
    r = subprocess.run([chrome, "--headless", "--disable-gpu",
                        "--no-pdf-header-footer", f"--print-to-pdf={PDF}",
                        "file://" + HTML],
                       capture_output=True, timeout=180)
    if r.returncode == 0 and os.path.exists(PDF) and os.path.getsize(PDF) > 5000:
        print(f"  {os.path.relpath(PDF, ROOT)}  {os.path.getsize(PDF)/1024:.0f} КБ")
    else:
        print("  pdf собрать не удалось:", r.stderr.decode()[:200])


if __name__ == "__main__":
    main()
