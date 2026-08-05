#!/usr/bin/env python3
"""
Build the arXiv submission from the paper's markdown source.

The paper is written and edited as markdown; the LaTeX is generated from it and
never edited by hand. Two versions of one text drift apart, and this paper is
about the cost of numbers that were right when they were typed.

arXiv compiles the source itself, so no local TeX engine is needed and none is
assumed. What is needed is that the source compile there, and the one thing
likely to stop it is the Cyrillic: file titles, quoted passages and the
archive's own field names are in Russian and cannot be transliterated away
without breaking the citations they support. The preamble therefore sets up
T2A encoding and the Russian babel language alongside English, which pdfLaTeX
on arXiv supports directly.

    python3 build_paper.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "paper", "paper.md")
OUT = os.path.join(ROOT, "paper", "paper.tex")

TITLE = ("A machine-readable catalogue of the Tsiolkovsky papers "
         "(fond 555, Archive of the Russian Academy of Sciences), and a way to "
         "measure how well its handwriting can be read")
AUTHOR = r"""Vladimir Beskorovainyi \\[2pt]
\small Besk Tech \ $|$ \ Moscow Institute of Technology and Physics (MIPT) \\[2pt]
\small \texttt{admin@besk.tech} \ $|$ \ \texttt{https://vladimir.besk.tech} \ $|$ \ ORCID: 0009-0004-7005-6242"""

PREAMBLE = r"""\documentclass[11pt,a4paper]{article}

%% Cyrillic is load-bearing here, not decoration: archival file titles and the
%% portal's field names are quoted as the archive records them, because a
%% citation resolves on the Russian wording and on nothing else.
%%
%% This order is the one that compiled and rendered correctly on arXiv, umlauts
%% and all. It looked wrong at first: extracting the text layer of the PDF gave
%% "Str\"obel" with the diaeresis detached, which reads as a font-encoding
%% fault. The rendered page is correct; the detachment is an artefact of text
%% extraction. Left alone deliberately.
\usepackage[T1,T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[english,russian]{babel}
\selectlanguage{english}

\usepackage[margin=2.6cm]{geometry}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{amsmath}
\usepackage{microtype}
\usepackage[hidelinks]{hyperref}
\usepackage{csquotes}

\setlength{\parskip}{0.4em}
\setlength{\parindent}{0pt}

\title{%s}
\author{%s}
\date{}

\begin{document}
\maketitle
""" % (TITLE, AUTHOR)


def convert():
    md = open(SRC, encoding="utf-8").read()
    # The title and the author line are set by the preamble, so drop them from
    # the body rather than letting pandoc render them a second time.
    md = re.sub(r"\A# .*?\n+\*\*[^*]+\*\*\n", "", md, count=1, flags=re.S)
    # LaTeX numbers its own sections, so the numbers written into the markdown
    # headings would come out doubled.
    md = re.sub(r"^(#{2,3}) \d+(?:\.\d+)?\.? ", r"\1 ", md, flags=re.M)
    # Pandoc renders a level-two heading as \section, which is what these are.
    # The markdown title was removed above, so its level-two headings are the
    # document's sections; without the shift pandoc makes them subsections.
    p = subprocess.run(
        ["pandoc", "--from=markdown", "--to=latex", "--wrap=preserve",
         "--shift-heading-level-by=-1", "--top-level-division=section"],
        input=md, text=True, capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"pandoc failed:\n{p.stderr}")
    body = p.stdout
    # The abstract is a section in markdown and an environment in LaTeX.
    body = re.sub(r"\\section\{Abstract\}[^\n]*\n(.*?)(?=\\section\{)",
                  lambda m: "\\begin{abstract}\n" + m.group(1).rstrip()
                            + "\n\\end{abstract}\n\n",
                  body, count=1, flags=re.S)
    return PREAMBLE + body + "\n\\end{document}\n"


def check(tex):
    """Cheap structural checks, since there is no engine here to compile with."""
    problems = []
    if tex.count("{") != tex.count("}"):
        problems.append(f"скобки не сходятся: {tex.count('{')} против {tex.count('}')}")
    envs = re.findall(r"\\begin\{(\w+\*?)\}", tex)
    ends = re.findall(r"\\end\{(\w+\*?)\}", tex)
    for e in set(envs) | set(ends):
        if envs.count(e) != ends.count(e):
            problems.append(f"окружение {e}: {envs.count(e)} begin, {ends.count(e)} end")
    if "\\end{document}" not in tex:
        problems.append("нет \\end{document}")
    # Cyrillic outside a Russian-language switch is fine with T2A loaded, but
    # a stray character in a verbatim or a URL is not.
    for m in re.finditer(r"\\(?:url|href)\{[^}]*[а-яА-Я][^}]*\}", tex):
        problems.append(f"кириллица внутри ссылки: {m.group(0)[:60]}")
    return problems


def main():
    tex = convert()
    problems = check(tex)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(tex)
    words = len(re.findall(r"\w+", tex))
    print(f"  {OUT}")
    print(f"  {len(tex.splitlines())} строк, около {words:,} слов разметки")
    print(f"  таблиц: {tex.count(chr(92) + 'begin{longtable}') + tex.count(chr(92) + 'begin{table}')}, "
          f"разделов: {tex.count(chr(92) + 'section{')}")
    if problems:
        print("  ПРОБЛЕМЫ:")
        for p in problems:
            print(f"    {p}")
        return 1
    print("  структурных ошибок не найдено; собирать будет arXiv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
