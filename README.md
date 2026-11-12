# Penalty decoder

An unofficial fan tool that reads public Formula 1 stewards' documents and says, in plain English, what happened, which Sporting Regulations article the stewards cited, and how many similar decisions in this file carried the same penalty tag.

It is not affiliated with the FIA or with Formula 1. It does not replace the decision PDF or the regulations.

![Layout sample of the timing-tower screen. The rows are not a real decision.](assets/timing-tower.svg)

## What you can do

- Browse decisions from the 2022 season through the latest race weekend stored in this file. Pick a season and a Grand Prix, then a decision.
- Read a short explanation. The article number and the penalty wording come from the document. The article text comes from the regulation PDF linked for that year. If that article is not in the file, the page says **I don't know**.
- Ask whether a similar incident is already in the file (track limits, unsafe release, causing a collision, impeding, and the other tags the parser knows). The counts are the number of rows with that tag. They are not a claim about every decision the stewards have ever written.
- Paste the text of a document if it is not in the list. The note uses that paste plus the regulation file for the season selected in the sidebar.

With no API key, the note is a fixed summary of those fields. If you set `XAI_API_KEY` or `GEMINI_API_KEY`, the app asks that model to rewrite the same fields. The model is told not to add incidents, quotes, or article text that are not in the fields. If the call fails, the fixed summary is shown.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app reads `data/decisions.json` and `data/regulations/`. It does not download anything when it starts.

Streamlit Community Cloud can host this file (Python 3.12, `streamlit run app.py`) without a key. This repository is not deployed.

## Data

Stewards' documents are the public PDFs linked from the FIA decision-document pages for the Formula One World Championship, seasons 2022, 2023, 2024, 2025, and 2026. The collector keeps documents whose titles are an infringement, an offence, or a decision, and skips summons, classifications, notes, and grids. Each stored row has the season, event, session, driver, car number, a short incident line, the article cited, the penalty line, and the PDF link.

The file is not a complete set. A first download stored many PDFs under one cache name when their paths shared a long prefix, so one document's text was attached to other titles. Every row that shared an extract with a different title, or that named a different car from its title, was deleted. A retry was not finished: fia.com answered HTTP 429, and this project does not try to get around that limit. After the deletions the file holds **665** decisions:

| Season | Decisions kept |
| --- | --- |
| 2022 | 90 |
| 2023 | 66 |
| 2024 | 59 |
| 2025 | 264 |
| 2026 | 186 |

2023 and 2024 are thin. Precedent counts for those seasons are counts inside this file only. `data/ingest_failures.json` lists the dropped titles and the download errors. The ingest script does not invent rows to fill the gap.

Regulation text is taken from one public PDF per season, named in `data/regulations/<year>.json`:

| Season | File used |
| --- | --- |
| 2022 | Sporting Regulations, Issue 9, 19 October 2022 |
| 2023 | Sporting Regulations, Issue 8, 6 December 2023 |
| 2024 | Sporting Regulations, Issue 7, 31 July 2024 |
| 2025 | Sporting Regulations, Issue 5, 30 April 2025 |
| 2026 | Regulations Section B (Sporting), Issue 9, 1 October 2026 |

A race weekend may have been run under an earlier issue. The explanation names the file above. It does not claim that file was the issue in force on the day.

OpenF1 is not called. The driver and session lines are copied from the stewards' PDF when that PDF contains them.

### Refresh after a race

```bash
PYTHONPATH=src python -m f1_penalty_decoder.ingest
```

The script is single-threaded. It waits 1.5 seconds after a response, and on HTTP 429 or 403 it waits longer and then records a failure instead of hammering the site. A PDF already in `data/.cache/pdf/` (the filename is a hash of the full URL) is parsed again and not downloaded. Run it again after a race weekend, or after the 429 has cleared, to add documents that are still missing. A document that cannot be fetched stays in `data/ingest_failures.json`.

GitHub Actions workflow **Refresh decision data** runs only when someone starts it by hand. It is separate from **CI**, so a failed refresh does not fail the test workflow. CI runs the tests with empty API keys.

## Tests

```bash
pytest -q
```

Unit tests cover the parser and the precedent counts. `tests/test_golden.py` checks about twenty real documents: the article, penalty tag, and incident tag must match the checked examples. Those examples are excerpts taken from the PDFs, so the test does not need the network or a key.

## Limits

- Titles that are not an infringement, offence, or decision are not in the file. A summons alone is not treated as a penalty.
- Bulk documents (for example a sheet of deleted lap times) may fail parsing and show up only in the failure list.
- Incident tags are keyword labels for search. They are not the stewards' own categories.
- Team colours in the list are a reading aid for the competitor name. They are not liveries or logos.
- Nothing here is legal advice, a prediction of a future decision, or an official result.

## Licence

MIT. The FIA documents and regulations remain the FIA's. This project stores links and short excerpts so a reader can find the source.
