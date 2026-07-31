# Corpus

Transcriptions of fond 555, one Markdown file per archival file, released as
work proceeds rather than held back until the fond is finished.

## What is here

| File | Title | Scans |
| --- | --- | ---: |
| `opis_1/delo_0033.md` | The Reaction Device as a Means of Flight in Vacuum and in Atmosphere | 16 |
| `opis_1/delo_0034.md` | Exploration of Celestial Space by Means of Reaction Devices | 176 |
| `opis_1/delo_0035.md` | The Reaction Device — the Rocket | 208 |
| `opis_1/delo_0046.md` | **The Spaceship, first variant** | 185 |
| `opis_1/delo_0047.md` | **The Spaceship, second variant** | 174 |
| `opis_1/delo_0051.md` | The Aeroplane — Rocket | 175 |
| `opis_1/delo_0084.md` | Album of Space Journeys | 162 |
| `opis_1/delo_0150.md` | Four Ways of Moving over Land and Water | 20 |
| `opis_1/delo_0252.md` | Life in the Cosmic Ether | 142 |
| | **Total** | **1,258** |

Every file above is transcribed **in full**. Partially transcribed files are
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

Across these 1,238 scans there are **8,421 uncertainty marks** — about seven
per scan. That is the point of the method rather than a defect of it: a
transcription whose doubtful places are visible can be checked and corrected
where it matters, while one that reads smoothly because uncertain words were
invented cannot be checked at all.

For the measured accuracy figure and how it was obtained, see the main README
and `validate.py`. In short: 98.1% at character level against a published
edition, measured on typescript. The equivalent figure for handwriting has
not yet been established and will be lower.

## Authorial deletions

These files contain **2,394 passages struck out by Tsiolkovsky himself**,
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
