# Legibility of the handwriting: a feasibility test

**Subject.** Fond 555, opis 1, file 33 — the article "The Reaction Device as a
Means of Flight in Vacuum and in Atmosphere", autograph, c. 1905.

**Method.** Direct reading of the JPEG scans by a vision model, with no
pre-processing of the images, across four pages chosen to span the range of
page types in the file.

**Date.** 26 July 2026. This test was run before any of the pipeline in this
repository existed, to decide whether the project was worth building at all.

## Results by page

| Page | Type | Read with confidence | Notes |
| --- | --- | --- | --- |
| 000 | Archival cover, semi-printed | ~98% | Fond, opis and file number, author, title — read almost without loss |
| 001 | Dense cursive, body text | ~85% | Calculations of the device's "ascent time"; some technical words uncertain |
| 002 | Cursive, badly faded, with deletions | ~70% | The worst case: pale ink and authorial correction |
| 003 | Large heading plus an archivist's note | heading ~90%, note ~70% | Large script is easy; the smaller note in a second hand is harder |

**Average across pages of running text: 75–85% read with confidence.**

These are the reader's own confidence estimates, not a measurement against a
known text. For an objective figure measured against a published edition, see
the accuracy section of the README and `validate.py`.

## What makes it hard

- Faded and pale ink on part of the pages.
- Pre-reform orthography (ѣ, і, ъ, ѳ) — legible, but it raises the proportion
  of uncertain readings.
- Authorial deletions and insertions in the margins.
- Technical terms and numbers are sometimes ambiguous — and those are exactly
  the parts that carry the meaning.

## What works well

- Covers, headings and catalogue data read almost without error. This is what
  makes the catalogue feasible as a first deliverable.
- The sense of a passage survives even where individual words are uncertain.
- Marking uncertainty explicitly — `[?]`, `[неразборчиво]`, struck-through
  text preserved — produces a transcription whose weak points are visible and
  checkable rather than hidden.

## Conclusion: the project is feasible

Machine transcription yields a **useful draft** of the corpus: the text
becomes machine-readable and searchable, with doubtful passages honestly
flagged. It is not a finished scholarly edition — faded pages and technical
passages need human verification.

The working model is standard digital humanities practice:

    machine transcription → explicit marking of uncertainty →
    selective expert verification of significant passages → citable corpus

The value of the result — a machine-readable catalogue and corpus of fond 555
— holds even without perfect transcription accuracy, provided the uncertainty
is marked rather than concealed.

**Recommendation, and what was in fact done.** Build the catalogue first: it
comes out of the retrieval process automatically and is complete and useful on
its own. Transcribe by priority — the substantial and significant files —
rather than sequentially through 51,008 scans.

---

*Russian original: [`ОТЧЁТ_А0_читаемость.md`](ОТЧЁТ_А0_читаемость.md).*
