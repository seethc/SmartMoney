# SmartMoney

A self-hosted Python finance dashboard for reviewed account balances, spending
history, cash-flow forecasts and transfer suggestions. Nothing executes payments.

## Snoop screenshot reader

Choose **Snoop screenshots**, upload account-overview screenshots, then review
each candidate GBP balance. Select an existing account or create a new one, enter
the date Snoop actually refreshed the balance, and confirm before saving.

- Entirely local Tesseract OCR and deterministic geometry/amount parsing. No LLM,
  API key, model download at runtime, cloud OCR, CDN or analytics.
- One image decoded/OCR'd at a time, one OCR thread, at most 1200 × 2400 OCR pixels.
- PNG/JPEG/WebP: maximum 8 MB / 16 megapixels each, up to six images per UI draft.
- Handles GBP amounts, negative balances, horizontal cards with labels underneath,
  and simple account lists. Apparent totals/spending summaries are excluded.
- OCR suggestions start skipped. Account mapping, numbers and dates require review.
  Logos are not interpreted as bank identities. Unsupported/ambiguous layouts may
  require a crop or manual correction; this is not a guaranteed Snoop integration.
- Images and OCR text are processed in memory, not saved to disk. Confirmed balance
  changes and their previous values are recorded in SQLite's `snapshot_audit` table.
- Snapshot commits are atomic; older dates, conflicting updates and duplicate
  account selections are rejected. Existing account planning preferences survive.

This reads **balances only**. Screenshots do not reconstruct transaction history.
Spending reports still use CSV transactions; forecasts use saved balances, planned
payments, buffers and allowances. Snoop itself requires internet to refresh banks.
Once dependencies are installed, SmartMoney's reader works without internet.
Your browser still needs a connection to the Pi; Tailscale remote connectivity is
separate from OCR. A browser on the Pi can use localhost with internet disconnected.

## Run

Python 3.11+ and Tesseract 5 with English language data are required.

On 64-bit Raspberry Pi OS:

```sh
sudo apt install python3-venv tesseract-ocr tesseract-ocr-eng
sh start.sh
```

Open `http://127.0.0.1:8765` in a browser **on that computer**.
For Pi installation and access from Windows/Pixel, use
[the Raspberry Pi guide](docs/raspberry-pi.md).

On Windows install Tesseract (for example the UB Mannheim distribution), then run
`./start.ps1` in PowerShell. Tesseract is found on PATH or in
`C:/Program Files/Tesseract-OCR/tesseract.exe`. Set `SMARTMONEY_TESSERACT` to a different
executable path if needed. Missing OCR produces a setup message; manual entry works.

## Workspaces and transaction history

**Demo workspace** contains fictional records; **My real data** starts empty.
Data lives in `data/` by default or `SMARTMONEY_DATA_DIR`. Databases and screenshots
are excluded from Git and release packages. Financial records are not encrypted
by SmartMoney; use private storage and encrypted backups.

CSV columns: `external_id,date,description,amount,category,kind`. Use UTF-8,
YYYY-MM-DD dates, signed GBP decimals and stable IDs per account. Types are
`expense`, `income`, `transfer`, `adjustment`. Import previews validate the whole
file; matching IDs deduplicate unchanged transactions, conflicting IDs are rejected.
History imports do not update balances. Do not import overlapping old bank history
under new IDs. Classify transfers and card repayments as transfers to exclude them
from spending. Credit-card debt is negative; purchases are expenses.

Forecasts process outgoing payments before incoming money on the same date and
preserve monthly payment days where possible. Funding sources are opted-in current
accounts with fresh snapshots and sufficient headroom after their own obligations.
Recommendations are estimates; make transfers manually in your bank apps.

## Open Banking reference

The retired implementation is preserved at
[`openbanking-reference`](https://github.com/seethc/SmartMoney/tree/openbanking-reference).
It is excluded from the current source tree and Pi package. That tag includes the
old connector, consent UI, vault, tests and instructions; UK personal production
access was never verified. The current product has no bank provider calls or keys.
Upgrades preserve existing financial records and dormant credential files, but do
not load old credentials. Revoke old consent separately in the bank/provider if any
was granted. Do not deploy the reference tag over your current installation.

## Checks

```sh
python -m pytest -q
python tools/package_pi.py
```

Tests cover financial calculations, CSV import, HTTP boundaries, screenshot parsing,
real OCR of synthetic carousel fixtures when Tesseract is installed, and
atomic balance updates. Pi hardware timing and memory must be measured on the
actual device; Windows results are not a Pi benchmark. See
[reader design and validation](docs/screenshot-reader.md).
