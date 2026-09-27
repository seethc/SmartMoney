# Local Snoop screenshot reader

## Layout research

Reviewed Snoop's [official walkthrough](https://snoop.app/how-it-works/) and its
[published account-overview image](https://images.ctfassets.net/hrr5jwhsjgbv/6ic4RT2tdqZEWinvh6Zy6V/7160f5d62b371d20a7735c829a5786ed/accounts.jpg).
Also checked the [Google Play listing](https://play.google.com/store/apps/details?id=app.snoop)
and [Snoop's feature announcement](https://space.snoop.app/t/new-app-features-bill-warnings-timelines-and-extra-paycycles/1945).
These are public examples, not proof of the exact layout in a user's app version.

The account overview uses horizontal cards: bank logo, amount, then nickname.
Nicknames can wrap to two lines. A Net worth card looks like a balance but sums
other accounts. Spending panels below the cards contain additional currency figures.
Some account identities are only logos, so OCR cannot reliably infer the bank.

The reader therefore uses Tesseract word coordinates to associate amounts with
nearby labels and split adjacent cards. It excludes obvious summary captions,
retains negative signs, and asks the user to choose the actual account. It never
automatically creates accounts based on a logo, assumes every currency figure is
a balance, or writes anything during preview. Every candidate starts skipped.

## Offline design and Pi limits

The spending-category layout is also supported. Coordinates align each category
name with its main amount; transaction counts are below, alongside comparisons
that must not be imported. A plus sign on a spending category means a net refund.
The excluded section separates income and internal transfers from spending.
Small shared images are enlarged before OCR within the same 1200 × 2400 bound.
Unclear amounts stay blank for review. The year, actual coverage dates and account
scope are entered by the user; they are not inferred from a comparison label.

Pillow validates images; the Tesseract 5 executable uses the locally installed
English language file. No LLM, cloud API, internet font, CDN, runtime package/model
download, or external OCR endpoint is used. See the
[Tesseract CLI documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

- Serialize **decoding and OCR**, not only subprocesses.
- Maximum upload: 8 MB. Reject images over 16 million pixels before decoding.
- Resize before making processing copies. OCR input is at most 1200 × 2400 pixels.
- Convert to grayscale, invert dark backgrounds, and adjust contrast.
- Sparse-text segmentation (`--psm 11`) suits separated Snoop cards.
- Single OCR thread (`OMP_THREAD_LIMIT=1`), 45-second subprocess timeout.
- Pipe the image through stdin and collect TSV through stdout; no image temp files.
- Maximum six images per browser draft, read sequentially.
- systemd limits: MemoryHigh=384M, MemoryMax=512M, TasksMax=32.

The memory cap covers the server and its OCR subprocess. It is a limit, not a
measurement of Pi performance. The actual Pi 4B/1 GB still needs a hardware test.
If an image times out, crop fewer cards. Running the browser on Windows/Pixel saves
Pi desktop memory. An offline reader does not make Snoop bank refreshes offline,
nor guarantee that remote network services work without internet.

## What is saved

User-confirmed GBP balance snapshots and separate spending reports. Images and OCR text are not persisted.
SQLite retains account names, balances and dates, and an audit of previous values.
The UI clears its draft after success/discard. OS swap or diagnostic dumps are not
controlled by this app. Credentials are not needed for Snoop screenshot import.

Updates require the prior balance/date to still match, reject older snapshots,
preserve preferences, and commit the entire batch or none of it. Duplicate account
selections and duplicate new account names/institutions are rejected. Repeating an
unchanged snapshot is a no-op. Existing dormant bank-link tables are not consulted.

## Validation and limitations

Tests exercise real Tesseract on synthetic light/dark carousel fixtures with
multi-line account names, net worth, negative credit balances and a spending panel.
They also cover positioned list parsing, non-GBP exclusion, invalid images, upload
size, worker contention, timeout recovery, review confirmation, date/precision
checks, atomic rollback, stale preview conflicts, audit records and workspace
isolation. Real OCR tests prohibit Python socket connections while extracting.

Synthetic fixtures are not a guarantee of accuracy on real screenshots. Marketing
images can be rotated or contain multiple phones; the supported input is a normal
upright account screenshot/crop. Partially hidden cards, small text, truncated
decimals, icons touching signs, non-GBP amounts, bills and transaction lists can
produce missing or incorrect candidates. Correct or skip them before saving.

An actual OCR run on Snoop's published `accounts.jpg` extracted My Main Account
£1,280.56, Barclaycard −£307.10 and Holiday Account £112.89. It excluded Net worth
and March spending, and flagged the partially hidden card. The read took under
one second on the Windows development machine; this is **not** a Pi timing result.
That downloaded third-party image is not included in the repository or release.

Validation includes real OCR on synthetic light/dark account cards and a small
spending-category image, plus report reconciliation and replacement conflicts.
Browser checks exercised upload, review, an existing-account update, a new credit
account and the saved-result screen using a separate disposable database. A
412-pixel mobile viewport showed no horizontal overflow. Pi deployment and a real
user screenshot remain to be tested on the device. The supplied category screenshot
was successfully read on Windows, including every main amount, counts, the refund
sign, and excluded income/transfers. That private image and its values are not
included in the repository or package.

Spending summaries retain category counts, signed spending, excluded amounts,
date range, scope and revision in `spending_summaries`. The headline total must
match the expense rows exactly. A repeated report replaces a month only after
confirmation; stale revisions fail. CSV totals and summaries remain separate.
Forecasts never treat category summaries as transactions or account balances.

CSV history remains available for transaction analysis. Automatic transaction OCR,
account-logo recognition, access to Snoop's
private API, and unattended phone control are outside this implementation.
