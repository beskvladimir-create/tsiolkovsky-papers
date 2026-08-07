# Corpus

Transcriptions of fond 555, one Markdown file per archival file, released as
work proceeds rather than held back until the fond is finished.

## What is here

See the file list in this directory: **359 archival files, 7,932 scans**,
across all five inventories. The rocketry core is complete, including both
variants of "The Spaceship" (files 46 and 47), "Exploration of Celestial Space
by Means of Reaction Devices" (34) and "The Reaction Device — the Rocket" (35).

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

Across these 7,932 scans there are **48,656 uncertainty marks** — about seven
per scan. That is the point of the method rather than a defect of it: a
transcription whose doubtful places are visible can be checked and corrected
where it matters, while one that reads smoothly because uncertain words were
invented cannot be checked at all.

For the measured accuracy figures and how they were obtained, see the main
README and `validate.py`. In short, against published editions: **98.1% at
character level on typescript, 81.1% on handwriting** once orthography is
folded onto modern spelling.

That gap sets a limit worth stating plainly. Two independent readings of one
and the same handwritten page agree on a median 37% of words, and the longest
verbatim run they share is about twelve words
(`calibrate_reading.py`, 294 pairs). So these files carry the substance of a
page reliably, but they will not support word-level collation of two
manuscripts against each other: at that scale the differences between two
readings outweigh the differences between two texts.

## Authorial deletions

These files contain **5,454 passages struck out by Tsiolkovsky himself**,
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
