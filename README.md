# Tsiolkovsky Papers

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21705221.svg)](https://doi.org/10.5281/zenodo.21705221)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Catalogue: CC0](https://img.shields.io/badge/catalogue-CC0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)

**A machine-readable catalogue of the personal archive of Konstantin
Tsiolkovsky — all 2,019 files, 51,008 scans — and the pipeline that produced
it.**

Konstantin Tsiolkovsky (1857–1935) derived the rocket equation and described
the multistage rocket, the orbital station and the space elevator decades
before anyone could test them. His papers are held as **fond 555 of the
Archive of the Russian Academy of Sciences**. The archive scanned the fond and
put the images online, but with no catalogue you can query, no full-text
search and no dataset: to find anything you click through page views one file
at a time.

This repository closes the first of those gaps.

## What is here

| | |
| --- | --- |
| `catalog.csv` / `catalog.json` | Every file in the fond: inventory, archival file number, title, material type, reproduction method, dates, scan count, link to the source page. **2,019 files, complete.** |
| `priority.csv` | The rocketry core of the fond, selected by title: 97 files, 4,046 sheets |
| Pipeline | Retrieval, page classification and transcription scoring — the code that produced the above and can reproduce it |

The catalogue is released **CC0**; the code is **MIT**.

### The fond

| Inventory | Files | Scans |
| --- | ---: | ---: |
| Опись 1 | 568 | 27,954 |
| Опись 1А | 24 | 2,283 |
| Опись 2 | 212 | 6,579 |
| Опись 3 | 198 | 2,881 |
| Опись 4 | 1,017 | 11,311 |
| **Total** | **2,019** | **51,008** |

Every scan was retrieved and checked: 51,008 files, all structurally valid
JPEGs, zero corrupt, catalogue and tree matching file for file.

The archive describes the fond as 31,680 *sheets*. That is not the number of
images — a sheet has a reverse side and each side is scanned separately. The
ratio measured across the whole fond is 1.61 scans per sheet, which matches
the archival cover of file 33: "9½ sheets", 16 scans.

## Why the catalogue was not trivial to build

The portal's structure is not what its URLs suggest. The inventory number in a
page address is decorative — `1_actview.aspx?id=834` and
`5_actview.aspx?id=834` return the same document. The id is a single sequence
across the whole fond, and the **real** inventory and archival file number
appear only inside the scan paths: `555\1_033` is opis 1, file 33. The id is
not the file number either — id 300 is file 297, because 31 files carry letter
suffixes (145а, 077б, 585а) that consume an id without advancing the count.

A catalogue built on the obvious reading of the URLs would label every file as
opis 1 and cite the wrong file numbers, making every row useless as an
archival reference. This one resolves each file from its scan path, so
`opis` + `delo` together form a citable archival address.

## The gap this closes next

*Issledovanie mirovykh prostranstv reaktivnymi priborami* ("The Exploration of
Cosmic Space by Means of Reaction Devices", 1903) is the founding paper of
astronautics. It is absent from Russian Wikisource, which carries 91 other
Tsiolkovsky works as full text — checked on 29 July 2026 by title search and
by full-text search for the phrase. The manuscript is in fond 555, file 45, as
126 scanned images.

*Kosmicheskiy korabl'* ("The Spaceship", files 46 and 47, two variants, 359
scans) is absent by the same check. No claim is made about sources that were
not searched; the digitised collected works held by the Russian State Library
are page images, which is a different question from machine-readable text and
has not been assessed.

Turning those images into text is the next stage of this project.

## What has been measured

**Page composition.** `classify_pages.py` measures every scan without a neural
network — printed baselines are evenly spaced, handwriting is not — at 18 ms
per page. Over all 51,008 scans:

| Class | Scans | Share |
| --- | ---: | ---: |
| Handwritten | 42,087 | 83% |
| Typewritten / printed | 6,367 | 12% |
| Notes and archival covers | 2,554 | 5% |

Typewriting is 14.3% of opis 1 and 13.8% of opis 4, but only 1.8% of opis 1A.
A further 2.3% of scans are faded enough to be hard cases. This decides how the
corpus gets processed: only the handwritten 83% needs a vision model, the
typewritten portion is ordinary OCR, and the faded pages can be routed
separately.

**Legibility.** A reading test across four page types of file 33 put confident
legibility at 75–85% on pages of running text — covers and headings read
almost without loss, faded ink and authorial deletions are the hard cases.
Full report: [`legibility-report.md`](legibility-report.md), also in
[Russian](legibility-report.ru.md).

**Transcription accuracy.** Reported as a measured figure, not an estimate.
Where a document in the fond corresponds to a text published on Russian
Wikisource, `validate.py` scores the transcription against it character by
character.

First measurement — file 33 pages 014–015, a typewritten letter to a newspaper
editor dated 12 May 1905, against "Письмо в газету «Биржевые ведомости»":
**98.1% at character level, 91.7% at word level.** Most of the residual
difference is editorial rather than error: the published edition expands
abbreviations and modernises orthography, where the transcription keeps the
source as written.

That figure is for typewriting and does not transfer to handwriting. The
handwriting figure has to be measured the same way, against a manuscript whose
text is also published.

## Contents

| File | What it does |
| --- | --- |
| `tsiolkovsky_downloader.py` | Walks the fond's flat id space, resolves the real inventory and file number from each scan path, resumes, retries, fetches oversized scans in ranged chunks, validates JPEG structure, maintains the catalogue |
| `classify_pages.py` | Per-scan metrics: ink coverage, text-line count, baseline regularity, contrast |
| `export_catalog.py` | Builds `catalog.json` and the priority list from `catalog.csv` |
| `validate.py` | Scores a transcription against a published text on Russian Wikisource |
| `keeper.sh` | Restarts the downloader after the machine sleeps |
| `TRANSCRIPTION_SPEC.md` | The fixed per-page instruction given to the model |

Two engineering notes, because both cost a day to find:

- The server truncates responses at about 130 KB. Small scans arrive whole;
  scans over ~800 KB fail with `IncompleteRead` however many times you retry.
  It does honour `Accept-Ranges`, so large files are fetched in 100 KB chunks
  and reassembled.
- It returns HTTP 500 on roughly a third of requests while serving the same
  URL correctly on the next attempt, so retry logic has to distinguish
  "temporarily broken" from "not there".

## Reproducing

Python 3, standard library only, plus `numpy` and `pillow` for the classifier.

```bash
python3 tsiolkovsky_downloader.py --only 33   # one file, by portal id
python3 tsiolkovsky_downloader.py            # the whole fond, resumable
python3 classify_pages.py                    # page metrics
python3 export_catalog.py                    # catalogue + priority list
```

The downloader makes **one request at a time** with a pause between them. This
is a public archive's server and it is not robust; please do not parallelise
it.

Scans are not redistributed here — 18 GB, and they are the archive's to
publish. The pipeline retrieves them from the source.

## Method for the corpus

Machine transcription produces a **useful draft**, not a finished scholarly
edition. Uncertain readings are marked `[?]`, unreadable passages
`[неразборчиво]`, authorial deletions preserved. This follows normal digital
humanities practice: machine transcription, explicit marking of uncertainty,
selective expert verification of significant passages, and an accuracy figure
measured against published texts rather than asserted.

## What comes next

- Transcription of the 97 priority files (4,046 sheets), with accuracy
  measured against published editions where they exist
- English translations of the principal works
- Release of the corpus as a dataset, with a paper describing the method

## Sources and licensing

Source: Archive of the Russian Academy of Sciences, fond 555 —
<https://www.ras.ru/ktsiolkovskyarchive/>

Tsiolkovsky died in 1935; his works are in the public domain. The scans are
produced and hosted by the Archive of the RAS and are not redistributed here.
Code in this repository is MIT; the catalogue is released CC0.

This is an independent research project, not affiliated with or endorsed by
the Archive of the Russian Academy of Sciences.

## Author and citation

Vladimir Beskorovainyi — sole author of this work.

    Beskorovainyi, V. (2026). Tsiolkovsky Papers: a machine-readable
    catalogue of fond 555, Archive of the Russian Academy of Sciences
    (v1.0.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.21705221

The DOI above is the concept DOI and always resolves to the latest release;
this release is 10.5281/zenodo.21705222. See `CITATION.cff` for the machine-readable form.
