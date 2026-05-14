---
name: ieee-xplore-harvester
description: |
  IEEE Xplore academic literature automation tool using Edge browser CDP protocol.
  Connects to a logged-in Edge browser, searches IEEE Xplore, extracts metadata
  (title, authors, DOI, abstract, keywords, citations), downloads PDF full-text,
  and generates structured CSV/JSON/HTML reports. Fully local, no Zotero needed.
  Use when the user wants to: (1) search and collect IEEE papers by keyword/year/IF,
  (2) batch-download PDFs from IEEE Xplore, (3) extract structured metadata from
  IEEE search results or detail pages, (4) generate academic literature reports,
  or (5) build a local IEEE paper library.
---

# IEEE Xplore Harvester

## Overview

Lightweight academic literature collector for IEEE Xplore. Connects to an already-open
Edge browser via CDP (Chrome DevTools Protocol), reuses the existing login session,
searches by keyword, extracts metadata, downloads PDFs, and produces structured output.

## Quick Start

### Prerequisites

1. Close all Edge windows, then launch with remote debugging:
   ```
   msedge.exe --remote-debugging-port=9222
   ```
2. In that Edge window, navigate to https://ieeexplore.ieee.org and sign in.
3. Install Python dependencies:
   ```
   pip install playwright websocket-client
   playwright install chromium
   ```

### Run

```bash
python scripts/harvester.py --keyword "solid electrolyte interphase" --years 2020-2025 --count 200 --download-pdf
```

默认输出到桌面 `论文` 文件夹下的 `{timestamp}_{keyword}` 子目录；如需其它位置，使用 `--output` 指定。

## Workflow

### 1. Detect Edge Browser

Run `scripts/cdp_detector.py` to list available Edge tabs and verify IEEE Xplore login.
The script queries `http://127.0.0.1:9222/json/list`, filters tabs with
`ieeexplore.ieee.org` in the URL, and checks login status via DOM inspection.

### 2. Execute Search and Extract Candidates

Run `scripts/harvester.py` with search parameters. The script:
- Connects to the IEEE Xplore tab via Playwright CDP
- Constructs search URL with keyword and year-range filters
- Uses IEEE search parameters `returnType=SEARCH`, `matchPubs=true`, and `rowsPerPage=100` to collect larger result sets
- De-duplicates candidates by IEEE article number / DOI / URL / title while paginating
- Saves candidates to `metadata/candidates.json` and `metadata/candidates.csv`
- Classifies papers into high/medium/low priority tiers

### 3. Extract Full Metadata

For each candidate, the script opens the detail page and extracts:
- Abstract, keywords, references
- Citation formats (BibTeX, RIS)
- EasyScholar IF label (if browser extension is installed)
- Access status (Open Access / Subscription)

### 4. Download PDFs

When `--download-pdf` is set, the script:
- Checks the desktop `论文` library for existing PDFs before downloading
- Skips existing PDFs and papers without an accessible PDF link instead of repeatedly failing
- Reuses browser session cookies for authenticated downloads
- Validates downloaded files (minimum 50KB, valid PDF header)
- Retries up to 3 times with exponential backoff on failure
- Logs all download results to `pdfs/download_log.json`

### 5. Generate Reports

After collection completes, the script generates:
- `reports/summary.html` - interactive HTML report with tables, charts, and stats
- `reports/statistics.json` - machine-readable statistics
- `reports/search_log.txt` - human-readable execution log

## Output Structure

桌面 `论文` 文件夹下：

```
论文/{timestamp}_{keyword}/
  metadata/
    candidates.json / candidates.csv
    high_priority.json / medium_priority.json / low_priority.json
    references.bib
  pdfs/
    001_{title}_{arnumber}.pdf
    download_log.json
  citations/
    001_citation.bib / 001_citation.ris
    all_references.bib
  abstracts/
    001_abstract.txt
    all_abstracts.txt
  reports/
    summary.html
    statistics.json
    search_log.txt
  urls.csv
  pending.csv
  config.json
```

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/harvester.py` | Main entry point; orchestrates full pipeline |
| `scripts/cdp_detector.py` | Edge CDP browser detection and login verification |
| `scripts/ieee_automation.py` | IEEE Xplore search, pagination, metadata extraction |
| `scripts/pdf_downloader.py` | PDF download with retry, validation, and logging |
| `scripts/storage.py` | Output directory creation, file organization, CSV/JSON I/O |
| `scripts/reporter.py` | HTML report and statistics generation |
| `scripts/utils.py` | Shared helpers: logging, filename sanitization, retry decorator |

## Key Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--keyword` | str | (required) | Search keyword(s) |
| `--years` | str | `2020-2025` | Year range, e.g. `2020-2025` |
| `--count` | int | `50` | Max papers to collect; pagination now requests up to 100 results per page |
| `--sort` | str | `relevance` | Sort order: `relevance`, `newest`, `oldest`, `cited` |
| `--download-pdf` | flag | `False` | Enable PDF download |
| `--min-if` | float | `0` | Minimum impact factor filter (requires EasyScholar) |
| `--output` | str | auto | Output directory (auto-generates if not set) |
| `--cdp-port` | int | `9222` | Edge remote debugging port |

## Error Handling

- **No Edge debug port**: Instruct user to restart Edge with `--remote-debugging-port=9222`
- **Not logged in**: Prompt user to sign in at ieeexplore.ieee.org
- **Paywall**: Mark paper as `pending` in `pending.csv`
- **CAPTCHA**: Pause and alert user to solve manually
- **Network timeout**: Auto-retry up to 3 times with exponential backoff
- **PDF validation failure**: Re-download once, then mark as failed

## References

Load `references/ieee_cdp_reference.md` when debugging CDP connection issues or
understanding IEEE Xplore page DOM structure and selectors.
