# CLAUDE.md

This file provides guidance for Claude Code when working with this repository.

## Project Overview

**musinsa_snap** is a Python scraper that collects photos and tags from Musinsa Snap (Korean fashion platform). It fetches listing pages, extracts snap detail URLs, and saves metadata (image URLs, author, tags, dates) to JSON Lines format.

## Project Structure

```
musinsa_snap/
├── musinsa_snap/
│   ├── __init__.py    # Package exports
│   ├── cli.py         # CLI entry point (argparse)
│   ├── client.py      # HTTP client with rate limiting
│   ├── models.py      # Snap dataclass
│   └── parser.py      # BeautifulSoup HTML parsing
├── requirements.txt   # Dependencies: requests, beautifulsoup4
└── README.md
```

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper
python -m musinsa_snap.cli --start-page 1 --end-page 2 --limit 20 --output snaps.jsonl

# CLI options
#   --start-page / --end-page  Page range to scrape
#   --limit                    Max snaps to collect
#   --delay                    Seconds between requests (default: 0.5)
#   --output                   Output file path (default: snaps.jsonl)
#   --verbose                  Enable debug logging
```

## Architecture Notes

- **client.py**: `MusinsaClient` handles HTTP requests with configurable delay between requests to avoid rate limiting. Uses `requests.Session` for connection pooling.
- **parser.py**: Two main parsers:
  - `parse_snap_listing()` - Extracts snap URLs from listing pages using regex pattern `/(?:mz/)?snap/(\d+)`
  - `parse_snap_detail()` - Enriches snap data from detail pages using CSS selectors and OpenGraph meta tags
- **models.py**: `Snap` dataclass with fields: id, url, title, author, image_url, tags, taken_at, description
- **cli.py**: `collect_snaps()` orchestrates pagination and data collection

## Development Guidelines

- When modifying parsers, note that Musinsa's HTML structure may change. CSS selectors in `parser.py` may need updates.
- The client includes polite defaults (0.5s delay, proper User-Agent). Maintain these to avoid overloading the target site.
- Output format is JSON Lines (one JSON object per line) for streaming processing.
- All Korean text should use UTF-8 encoding (`ensure_ascii=False` in JSON dumps).
