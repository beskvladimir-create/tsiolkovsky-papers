# Transcription specification

The instruction given to the model for every page. Fixed on purpose: the
transcription of one page must not depend on who ran it or when, and the
method has to be stateable in a paper.

## Task

Read one scanned page of a manuscript from fond 555 and return its text.

## Rules

1. **Return the text of the page and nothing else.** No preamble, no
   commentary, no summary, no observations about legibility or condition, no
   headings you invented. Page headings, file structure and notes about
   condition are added by the pipeline, not by the model. Output that begins
   with "Here is" or "This page contains" is a failed transcription.

2. **Preserve the original orthography**, including pre-reform letters
   (ѣ, і, ъ at word end, ѳ). Do not modernise spelling, punctuation or
   number formatting.

3. **Preserve the author's line breaks** where they are visible. Do not
   reflow into paragraphs.

4. **Mark uncertainty explicitly** — this is the point of the method, not an
   optional courtesy:
   - `слово[?]` — a reading you believe is right but are not sure of
   - `[неразборчиво]` — a word you cannot read
   - `[неразборчиво: N слов]` — a longer illegible passage, with your estimate
   - `~~слово~~` — struck through by the author
   - `[вставка: слово]` — inserted above the line or in the margin
   - `[на полях: текст]` — marginal note
   - `[другой почерк: текст]` — text in a different hand (usually an
     archivist's note)

   Never silently guess. A page with twenty `[?]` marks is a useful
   scientific result. A page that reads smoothly because uncertain words were
   invented is worthless and worse than nothing, because nobody can tell
   which parts to trust.

5. **Formulas and numbers.** Transcribe as written. If a formula cannot be
   rendered in plain text, describe it in square brackets:
   `[формула: V = w·ln(M1/M2)]`. Numbers are the most consequential thing on
   these pages — never approximate a digit you cannot see; mark it `[?]`.

6. **Tables.** Transcribe as a markdown table if the structure is clear,
   otherwise row by row with `|` separators. Missing or unreadable cells are
   `[?]`.

7. **Drawings and diagrams.** Do not attempt to reproduce them. Emit
   `[рисунок: краткое описание]` and transcribe any lettering or captions.

8. **An empty or near-empty page** returns `[пустой лист]` and nothing else.

## Output

Plain text, no markdown fences. The pipeline wraps each page with its own
heading and provenance.

## Why the constraints on output length

Output tokens are the binding constraint on this project, and every sentence
of commentary is a sentence of manuscript not transcribed. The instruction to
return only the text is a cost control as much as a formatting rule.
