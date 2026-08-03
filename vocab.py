#!/usr/bin/env python3
"""
English glosses for the archive's descriptive vocabulary.

Three fields of the catalogue are drawn from a controlled vocabulary rather
than written freely: the material type, the method of reproduction and the
language. Their values are compound, given as a comma-separated list of terms,
so the glossing works on the terms and reassembles the value.

Titles are not glossed and must not be: a file's title is the archival record
of what the document is called, and translating it would produce a citation
that does not match the archive. Dates likewise stay in the archive's own
format. What is glossed is the description around them, which is what a reader
without Russian needs in order to navigate at all.

Coverage of material types is 95% of occurrences; the tail is long and mostly
unique, and any term without a gloss passes through in Russian rather than
being guessed at.
"""

MATERIAL = {
    "письмо": "letter", "письма": "letters",
    "статья": "article", "статьи": "articles",
    "фотография": "photograph", "фотографии": "photographs",
    "портрет": "portrait", "портреты": "portraits",
    "таблицы": "tables", "чертежи": "technical drawings",
    "формулы": "formulae", "рисунки": "drawings",
    "автобиография": "autobiography", "воспоминания": "memoirs",
    "монография": "monograph", "брошюра": "booklet",
    "отрывок": "extract", "отрывки": "extracts",
    "отрывок статьи": "extract from an article",
    "отрывки статьи": "extracts from an article",
    "фрагмент": "fragment", "фрагменты": "fragments",
    "фрагменты статьи": "fragments of an article",
    "фрагменты статей": "fragments of articles",
    "фрагменты работ": "fragments of works",
    "заметка": "note", "заметки": "notes",
    "записка": "memorandum", "записки": "memoranda",
    "записи": "records", "конспекты": "synopses",
    "выписка": "excerpt", "выписки": "excerpts",
    "предисловие": "preface", "главы": "chapters",
    "проект": "design", "план": "plan", "план работ": "work plan",
    "очерк": "essay", "обзор": "survey", "отзыв": "review",
    "заключение": "opinion", "замечания к статье": "remarks on an article",
    "добавление к статье": "addendum to an article",
    "ответ на возражения": "reply to objections",
    "адреса": "addresses of greeting",
    "протокол": "minutes", "доклад": "report",
    "отчёт": "account", "описание": "description",
    "описание работ": "description of works",
    "описание конструкции": "description of a construction",
    "расчёт": "calculation", "расчёты": "calculations",
    "вычисления": "computations",
    "набросок": "sketch", "наброски": "sketches",
    "набросок статьи": "sketch of an article",
    "черновики": "drafts", "шаблоны": "templates",
    "телеграмма": "telegram", "телеграммы": "telegrams",
    "извещения": "notifications", "объявление": "announcement",
    "заявление": "statement", "обращение": "appeal",
    "ответ": "reply", "ответы": "replies",
    "анкета": "questionnaire", "учётная карточка": "record card",
    "инструкция": "instructions", "смета": "estimate",
    "программа": "programme", "программа лекций": "lecture programme",
    "лекция": "lecture", "текст выступления": "text of an address",
    "список работ": "list of works", "путеводитель": "guide",
    "материалы": "materials", "материалы к ней": "materials for it",
    "конверты": "envelopes",
    "объяснительная записка": "explanatory memorandum",
}

REPRODUCTION = {
    "автограф": "autograph",
    "машинопись": "typescript",
    "машинопись с правкой автора": "typescript with the author's corrections",
    "рукопись": "manuscript",
    "фото": "photograph",
    "фотографии": "photographs",
    "фотокопия": "photocopy",
    "газетные вырезки": "newspaper cuttings",
    "типографская печать": "letterpress",
    "гектограф": "hectograph",
    "ксерокопия": "xerox copy",
}

LANGUAGE = {
    "русский": "Russian", "английский": "English", "немецкий": "German",
    "французский": "French", "украинский": "Ukrainian", "польский": "Polish",
    "испанский": "Spanish", "итальянский": "Italian", "турецкий": "Turkish",
    "латынь": "Latin", "эсперанто": "Esperanto", "чешский": "Czech",
    "болгарский": "Bulgarian", "японский": "Japanese", "шведский": "Swedish",
}


def gloss(value, table):
    """Gloss a compound value term by term, keeping anything unknown as it is."""
    if not value:
        return ""
    out = []
    for part in value.split(","):
        p = part.strip()
        if not p:
            continue
        out.append(table.get(p, table.get(p.lower(), p)))
    return ", ".join(out)


def build(values, table):
    """A Russian-to-English map for exactly the values present in the data."""
    return {v: gloss(v, table) for v in sorted(values) if v}
