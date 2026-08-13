# Corpus

Transcriptions of fond 555, one Markdown file per archival file. The fond is
now transcribed whole.

## What is here

See the file list in this directory: **2,018 archival files of 2,019, 50,962
scans**, across all five inventories — the whole fond, including both variants
of "The Spaceship" (files 46 and 47), "Exploration of Celestial Space by Means
of Reaction Devices" (34) and "The Reaction Device — the Rocket" (35).

One file is missing: two scans of opis 4, file 340 are refused by every model
tried, which stops the file from being assembled. The refusal is a filter
against reproducing known text verbatim, and it is recorded here rather than
worked around.

Every file here is transcribed **in full**. Partially transcribed files are
not published: a partial transcription reads as a complete text with the
middle silently missing, which is the worst kind of error in an archival
edition.

## How to read the markup

| Marker | Meaning |
| --- | --- |
| `слово[?]` | Read, but the reading is uncertain |
| `[неразборчиво]` | Could not be read |
| `[неразборчиво: N слов]` | A longer illegible passage, with an estimate of its length |
| `~~слово~~` | Struck out by the author |
| `[вставка: ...]` | Inserted above the line or in the margin |
| `[на полях: ...]` | A marginal note |
| `[другой почерк: ...]` | A different hand, usually an archivist's note |
| `[формула: ...]` | A formula that cannot be rendered as plain text |
| `[рисунок: ...]` | A drawing, with a short description |

Original orthography is preserved, including the pre-reform letters ѣ, і, ъ
and ѳ. Nothing is silently modernised.

## What this is and is not

This is a **machine transcription with uncertainty marked**, not a scholarly
edition. It has not been checked by a human against the scans.

Across these 50,962 scans there are **309,900 uncertainty marks** — about six
per scan. That is the point of the method rather than a defect of it: a
transcription whose doubtful places are visible can be checked and corrected
where it matters, while one that reads smoothly because uncertain words were
invented cannot be checked at all.

For the measured accuracy figures and how they were obtained, see the main
README and `validate.py`. In short, against published editions: **98.1% at
character level on typescript, 81.1% on handwriting** once orthography is
folded onto modern spelling.

Those two figures were scored on the part of the corpus read by the earlier
pipeline. The rest was read by a different model and has not been scored
against the editions, so the figures should not be read as covering the whole.
What was measured on the whole is agreement between two readings of one text —
a handwritten sheet against the typed copy of it in the same file — and it is
the same for both parts, 37% over 1,371 pairs from 194 files. That says the
newer part is read no worse than the older one; it does not establish 81% for
it. See `check_batch_quality.py`.

That gap sets a limit worth stating plainly. Two independent readings of one
and the same handwritten page agree on a median 37% of words, and the longest
verbatim run they share is about twelve words
(`calibrate_reading.py`, 294 pairs). So these files carry the substance of a
page reliably, but they will not support word-level collation of two
manuscripts against each other: at that scale the differences between two
readings outweigh the differences between two texts.

## Authorial deletions

These files contain **6,868 passages struck out by Tsiolkovsky himself**,
preserved as `~~...~~`. Published editions print what survived the author's
pen; this shows what did not.

No claim is made here about whether any particular deleted passage is
unknown. Establishing that requires comparison against the published
editions, which is a separate piece of work.

## Method

The per-page instruction given to the model is fixed and published as
`TRANSCRIPTION_SPEC.md` in the repository root, so that a transcription does
not depend on who ran it or when. `assemble.py` builds these documents from
the per-scan output; `build_queue.py` decides which model reads which scan,
routing typescript and short notes to a cheaper model and handwriting to a
stronger one.

Scans are not redistributed here. Each file's header links to its page on the
archive's own site.
