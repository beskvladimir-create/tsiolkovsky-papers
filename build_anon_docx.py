#!/usr/bin/env python3
"""
Анонимная копия статьи в Word для журналов со слепым рецензированием.

Journal of Cultural Analytics рецензирует вслепую и требует Word, а не PDF.
Полностью скрыть авторство у этой работы нельзя: она гуглится по одной фразе,
репозиторий назван по автору, DOI зарегистрирован на него. Но формальное
требование выполнимо, а остальное закрывается раскрытием в письме редактору.

Собирается из `paper/paper.md`, того же источника, что и версия для arXiv,
иначе анонимная копия отстанет от статьи — что уже случилось: в присланной
редакции жило «11% of the fond» из времён, когда расшифрована была десятая
часть, при том что весь текст вокруг говорит о полном фонде.

    python3 build_anon_docx.py
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "paper", "paper.md")
OUT = os.path.join(ROOT, "paper", "JCA_submission_anonymised.docx")

WITHHELD = "[repository URL withheld for anonymous review]"

# Что выдаёт автора: имя, домены, идентификаторы. Ссылки на чужие работы
# (arXiv:2201.06170, arXiv:2603.25761) остаются — они и должны остаться.
SCRUB = [
    (r"Vladimir Beskorovainyi", "[Author]"),
    (r"Besk Tech", "[Affiliation]"),
    (r"admin@besk\.tech", "[email]"),
    (r"https?://vladimir\.besk\.tech/?", WITHHELD),
    (r"ORCID:?\s*0009-0004-7005-6242", ""),
    (r"https?://github\.com/beskvladimir-create/tsiolkovsky-papers/?", WITHHELD),
    (r"https?://beskvladimir-create\.github\.io/tsiolkovsky-papers/?", WITHHELD),
    (r"https?://huggingface\.co/\S+", WITHHELD),
    (r"https?://doi\.org/10\.5281/zenodo\.\d+", WITHHELD),
    (r"10\.5281/zenodo\.\d+", "[DOI withheld for anonymous review]"),
    (r"arXiv:2608\.03617", "[preprint identifier withheld for anonymous review]"),
]


def main():
    if not shutil.which("pandoc"):
        sys.exit("нужен pandoc")
    text = open(SRC, encoding="utf-8").read()

    # заголовок статьи оставляем, авторский блок заменяем одной строкой
    text = re.sub(r"^#\s+.*$", lambda m: m.group(0), text, count=1, flags=re.M)
    for pat, repl in SCRUB:
        text = re.sub(pat, repl, text)
    # строка автора под заголовком, если она есть в markdown
    text = re.sub(r"^\*\*\[Author\]\*\*.*$", "[Author details withheld for anonymous review]",
                  text, flags=re.M)

    left = [p for p, _ in SCRUB if re.search(p, text)]
    if left:
        print("  ! осталось не вычищенным:", left)

    tmp = os.path.join(ROOT, ".anon.md")
    open(tmp, "w", encoding="utf-8").write(text)
    try:
        r = subprocess.run(
            ["pandoc", tmp, "--from=markdown", "--to=docx", "--wrap=preserve",
             # без метаданных: имя автора не должно попасть в свойства файла
             "--metadata", "author=", "--metadata", "title=",
             "-o", OUT],
            capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"pandoc failed:\n{r.stderr}")
    finally:
        os.remove(tmp)

    print(f"  {os.path.relpath(OUT, ROOT)}  {os.path.getsize(OUT)/1024:.0f} КБ")
    print(f"  знаков в источнике: {len(text):,}")


if __name__ == "__main__":
    main()
