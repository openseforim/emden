# Jacob Emden, *Megillat Sefer*: Hebrew text and English draft translation

Reader: https://openseforim.org/emden/

Work in progress: the autobiography of R. Jacob Emden (1697–1776), page by page, in Hebrew with an English draft
translation.

- **Hebrew base text:** ed. David Kahana, Warsaw 1896/97, from the HebrewBooks scan no. 37017
  (https://hebrewbooks.org/37017). This copy is Gershom Scholem's: it has his library stamp, handwritten
  insertions from the manuscript in the margins, and a typed sheet bound in after p. 8.
- **OCR:** Kraken 7.1 with the PP-OCRv6 (medium) model (Kiessling, Inria; Apache-2.0), checked line by line
  against the scan. Corrections are recorded in `data/fixes.json`.
- **Second reader:** the Pninim project's typed text of Bick's edition (Jerusalem 1979) is used only to find
  differences. It is not included here (GFDL with invariant sections); `scripts/fetch_pninim.ps1` downloads it.
- **English:** draft translation by Claude (Anthropic), not yet reviewed.

See `NOTES.md` for the choice of base text (Kahana vs. Bick), the OCR test, and what Scholem's copy shows.

## Layout

| Path | Content |
|---|---|
| `data/kraken/` | raw Kraken output per scan page (`sNNN.txt`, logical order) |
| `data/body/`, `data/notes_kahana/` | main text and Kahana's footnotes, split |
| `data/fixes.json` | corrections made against the scan |
| `data/text/` | checked Hebrew (`sNNN.he.txt`) and Kahana's notes (`sNNN.notes.txt`) |
| `data/scholem/notes_*.tsv` | margin readings in Scholem's copy (collation with the Oxford MS, by a key sheet in the copy made by Ḥayyim Wirszubski): anchor, mark (V = omission, X = substitution), reading, certainty |
| `data/align/` | differences against the Pninim/Bick text |
| `translation/` | English, one section per book page |
| `docs/` | the GitHub Pages reader (built by `scripts/build_site.py`): home page, one page per chapter, index, search, scan images (`docs/scans/`, 1-bit PNG rendered from the PDF) |
| `data/site/` | `intro.md` (home-page introduction), `entities.json` (index of names: regex patterns over the English), `review.json` (review status per page) |
| `scripts/site/` | `style.css`, `app.js`, `search.js`, copied to `docs/` |

## Pipeline

```
py -3.13 scripts/ocr_kraken.py FIRST LAST 3      # scan pages, needs the PDF and Kraken
py -3.13 scripts/align_pninim.py FIRST LAST      # needs source/pninim/
py -3.13 scripts/apply_fixes.py FIRST LAST
py -3.13 scripts/build_site.py
```

Scan page to book page: scan 11 = p. 3; scan 17 is the typed insert, scan 18 is blank; scan 19 = p. 9 (offset +10).

## Licence

Code: MIT. Translation and notes: CC BY 4.0. Kahana's 1896 text is in the public domain.
