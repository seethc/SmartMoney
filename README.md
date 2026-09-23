# SmartMoney

A Python + SQLite finance dashboard, hosted on your own computer, with a responsive, installable web app. Built around the account roles in [your shared discussion](https://chatgpt.com/share/6aaed42a-8ce8-83eb-bf6c-8fb43be6db42).

## Raspberry Pi

See [the Raspberry Pi installation guide](docs/raspberry-pi.md) for the 64-bit Raspberry Pi OS installer, Raspberry Pi Connect instructions, automatic systemd startup, backups, and private HTTPS access from both your Windows laptop and Pixel. Linux bank secrets use an encrypted vault with a separate owner-only key; Windows retains DPAPI. Python 3.11+ is supported. You have confirmed the Pi service is active and Connect screen sharing works. You have also confirmed the dashboard opens on the Pi. Continue at step 2 of the guide to connect both Windows and your Pixel to the same private HTTPS address, then verify live bank access.

## Run locally

Windows, from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:8765**. For subsequent starts, run `start.ps1`, or `.\.venv\Scripts\python.exe run.py`. Stop with Ctrl+C. If PowerShell prevents scripts, use the Python command directly; no execution-policy changes are needed.

The server binds only to `127.0.0.1`. It is not published online. The backend must keep running while you use the browser or installed app. Python 3.11+ is required. `requirements-lock.txt` records the dependency versions tested on Windows. The Pi installer uses `requirements.txt` to resolve packages for its Python/ARM platform.

## What works

- Overview: net worth, cash, recorded spending/income, conservative cash-flow headroom.
- Account snapshots: current, savings, credit-card debt, and investment valuations. Each account has a purpose, buffer, spending allowance, snapshot date and optional permission to fund suggestions.
- Spending: category breakdowns and editable classification.
- History: searchable transactions, account/type filters and month selection.
- Forecast: 14/30/60/90 days of planned bills, salary and internal transfers, with per-account daily projections and minimum balances.
- Transfer plan: funding gaps, suggested source amounts, deadlines and a readable calculation. Unfunded gaps are shown explicitly.
- Read-only Open Banking: Enable Banking production setup, bank consent, manual balance/history sync, reconnection and session revocation. Requires your own registered application and supported accounts.
- CSV import: preview, validation, all-or-nothing commit and stable-ID deduplication.
- PWA manifest and installation support for compatible browsers; responsive phone layout.

**No payments, bank login, transfer execution, investment orders, or bank-account changes are possible.** The connector creates and revokes account-information consent sessions; financial changes are limited to your local records and planning preferences. You perform real actions in your native banking apps.

## Start with your own data

The app opens in a clearly labelled demo workspace. Select **My real data** to use the initially empty personal workspace. Demo and personal records use separate databases.

### Connect real bank accounts

Open [Bank connections](http://127.0.0.1:8765/connections.html). The software integration is implemented, but it cannot access a bank until you complete provider registration and bank consent. The connector has been tested against simulated provider responses; a real-bank connection has not yet been verified.

1. Choose **Prepare connection**, then download the public certificate. This creates the bank private key on the backend. Windows uses DPAPI; Linux encrypts it with the separate vault key initialized during installation. The private key is never downloaded by the browser.
2. Sign up in the [Enable Banking control panel](https://enablebanking.com/cp/applications) and register a **PRODUCTION** application for **Account Information (AIS)**. Upload the public certificate and register the exact redirect URL shown in SmartMoney. By default it is `http://127.0.0.1:8765/openbanking-callback`; for a private HTTPS deployment it follows `SMARTMONEY_PUBLIC_URL`.
3. Link your own accounts to that application in the provider control panel to activate restricted production access. Their [terms](https://enablebanking.com/terms/) and [FAQ](https://enablebanking.com/docs/faq/) describe personal use for linked accounts. You must complete provider agreements and bank approval yourself.
4. Paste the application UUID into SmartMoney and choose **Verify application**, then **Load available banks**. Choose a bank and **Continue to bank consent**. Start and finish in the same browser at the configured app address, with the Python server running. The default localhost address can reach the Pi through an SSH tunnel. Bank authentication occurs in the provider/bank flow; SmartMoney never asks for your password or PIN.
5. On return, choose **Sync now**. This imports supported GBP current/savings balances and up to the last 90 days of booked transactions. Bank sync is manual, not scheduled. The page shows last sync, consent expiry and skipped records; approve consent again when it expires.
6. Review imported transactions, especially internal transfers, before they count toward income/spending. Configure each account's role, safety buffer, daily allowance and optional funding-source permission. Newly linked accounts default to no funding permission. Add expected bills and salary to Cash flow: only payments not already reflected in balances. After making a transfer in your bank app, sync again and classify both sides as transfers.

Coverage is loaded from the provider's current UK personal-account list. Do not assume all of Barclays, Santander, Revolut, Chase, or a particular Ulster savings product are supported. Only GBP accounts classified as current/savings are imported; cards, investments, foreign-currency accounts and transactions without stable IDs are currently skipped. The provider must supply a booked balance. If registration refuses a personal application or the loopback redirect, retain the error for diagnosis; do not publish this local server as a workaround.

The data route is **your bank → Enable Banking → your local Python backend → SQLite → your browser/app**. This uses an external data provider; it is not an entirely offline connection. No payment scopes or payment endpoints exist in the adapter. Disconnect revokes its provider session and retains local records. You can also revoke consent with the bank/provider.

### Manual accounts and CSV

Use **Add account** and CSV import for unsupported accounts. Keep manual/CSV accounts separate from bank-linked copies of the same account to avoid duplicated balances and history. CSV imports into a bank-linked account are blocked. Manually record card debt and investment valuations as needed.

Amounts, example account balances, dates and rates of spending in the demo are fictional; the demo does not assert anything about your actual finances. Demo dates are set on first run. Demo snapshots become stale after that day, just like personal snapshots.

### CSV format

```csv
external_id,date,description,amount,category,kind
bank-row-001,2026-09-01,Salary,3200.00,Income,income
bank-row-002,2026-09-02,Groceries,-42.50,Groceries,expense
bank-row-003,2026-09-03,To Santander,-1000.00,Transfers,transfer
```

- UTF-8, comma separated, exact six column names, ISO dates, signed GBP decimal amounts (maximum two decimal places). No currency symbol or thousands separator. The UI accepts a file or pasted CSV.
- `kind`: `expense`, `income`, `transfer`, or `adjustment`. Bank-specific CSV column mapping is not implemented yet; adapt exports to this format.
- `external_id` is stable and unique within an account. Preserve it across repeated exports. Two legitimate identical purchases require different IDs. Duplicate IDs inside an import are rejected; already imported IDs with matching date, description and amount are skipped. Changed transaction details under an existing ID are rejected. Later category edits are preserved on reimport.
- Expenses are negative, refunds are positive expenses. Refunds reduce spending in their category. Negative net category values are shown but excluded from the spending ring.
- Internal movements (including savings transfers and card repayments) use `transfer` on **both** imported sides, and are excluded from income/spending. Card purchases are expenses when booked. The app does not automatically infer transfer pairs or reconcile them.
- Adjustments are excluded from spending and income (e.g. valuation changes).
- **CSV history import never changes an account's balance snapshot.** This prevents double-counting history already reflected in the bank balance. Refresh balances separately.
- At most 10,000 rows, 1.5 MB of CSV text per import. Invalid imports save nothing. No existing personal records are replaced by demo data.

## Forecast rules and limits

All money calculations use integer pence. Decimal input is validated before conversion. Forecasts include today through `today + horizon - 1`.

Start with recorded balances (for bank feeds, the lower of booked and available balances when both are supplied), apply outstanding planned payments, and deduct the daily allowance each day. Process outgoings before incoming funds on the same date so salary cannot conceal an intraday shortfall. Planned transfers affect both source and destination. Monthly recurrence retains its original day and clamps to the last day of shorter months. Past monthly occurrences are skipped; past one-off payments are not forecast. The engine does not automatically reconcile schedules against imported transactions.

An account's funding gap is `buffer - lowest projected balance`. Suggested sources must be opted-in current accounts with today's balance snapshot. Source capacity is their own minimum projected balance minus their buffer. Capacity is allocated once across suggestions, earliest shortfalls first. Savings and investments cannot fund suggestions. Stale target snapshots suppress source allocation. Snapshots reflect their recorded bank or manual observation date; a recent sync is not proof of availability at the time you act.

The suggestion deadline is the day before the first buffer breach, or today if already at risk. This is a planning reminder, **not a guarantee of transfer settlement**. Source capacity is intentionally conservative: the app may show an unfunded gap even where a later salary could cover a later payment.

Cash-flow headroom sums current-account minima less their buffers, includes account deficits, and floors the result at zero. It excludes savings/investments and does not treat future income as immediately available. It is hidden when any balance snapshot is stale. It is an estimate based only on recorded obligations and spending allowances. Confirm all planned payments and bank balances before acting.

Suggested transfers are never inserted into the forecast or marked complete. Updating records is the only way to reflect real changes. Alerts exist inside the dashboard; background notifications, weekly briefings and scheduled bank sync are not implemented.

## App installation and phone use

Open the local URL in Edge or Chrome and use the browser's install-app option; the in-page Install app button opens the browser prompt when available and otherwise gives instructions. The installed app uses the same local backend. The PWA deliberately does **not** cache financial API responses or data for offline viewing. Navigation stays with the browser so its login prompt works; a disconnected backend shows the browser’s offline/error screen. Browser install availability depends on browser/platform support; see [MDN's installability guidance](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable).

The UI fits phones, but a phone cannot reach the Pi through its own localhost address. Follow [the Pi guide](docs/raspberry-pi.md) to configure Tailscale Serve, an HTTPS app origin, and app-password authentication, then install through Chrome on Android. The backend stays bound to loopback. No native iOS/Android binaries are included, and phone installation has not yet been verified on your physical device.

## Local data and boundaries

- `data/personal.sqlite3`: your records. `data/demo.sqlite3`: demo records.
- Windows: `data/openbanking.dpapi` protects bank secrets for the original Windows user. Linux: `data/openbanking.fernet` uses a separate encryption key configured by `SMARTMONEY_VAULT_KEY_FILE` (default `~/.config/smartmoney/vault.key`). The systemd installation stores state in `/var/lib/smartmoney` and passes secrets using systemd credentials. Back up the vault with its matching key. DPAPI files cannot be copied to Linux; reconnect there with a new certificate. Public `.crt` files contain no private key.
- Data directory can be overridden with `SMARTMONEY_DATA_DIR`. It is never served as a static directory.
- Databases are unencrypted SQLite. Rely on device security/disk encryption. For a consistent backup, stop the server, copy `data/personal.sqlite3` somewhere private, then restart. Restore by stopping the server and restoring that file. No cloud backup is configured.
- Single-user design. The default Windows/dev mode has no login and binds to loopback. The Pi service adds a random app password. An HTTPS remote origin requires an access-password file; all app/API routes then require HTTP Basic authentication. Use the documented private proxy setup; this is not public multi-user hosting.
- Same-origin mutation checks, custom request header, trusted-host checks, restrictive content policy, and no CORS access. No external fonts, CDNs, analytics or cloud AI calls.

## Architecture and next stage

`smartmoney/app.py` — FastAPI API, validation and local request boundary. `store.py` — SQLite and demo seeding. `engine.py` — pure forecast/recommendation calculations. `frontend/` — framework-free HTML/CSS/JavaScript PWA. No Node build step is required. [FastAPI documentation](https://fastapi.tiangolo.com/tutorial/) describes the underlying API framework.

`bankfeed.py` implements the Enable Banking AIS API with signed JWT authentication and an explicit read-only endpoint allowlist. `openbanking.py` provides setup, single-use browser-bound consent state, production validation, staged sync and revocation. `vault.py` stores secrets using Windows DPAPI or authenticated Fernet encryption on Linux, with owner-only key files. `config.py` validates the app origin and remote authentication configuration. `providers.py` contains types for possible additional adapters. See the [provider API reference](https://enablebanking.com/docs/api/reference/).

Sync fetches all eligible balances and pages before atomically writing local records. Stable account identities deduplicate reconnections; stable transaction IDs deduplicate repeated imports. Pending entries are excluded. New or changed transactions require review before inclusion in totals; existing category edits survive unchanged reimports. Expired consents are reported and skipped so they do not block renewed connections. Access logs are disabled to avoid logging callback codes, and callback parameters are removed from browser history after capture.

Further useful stages: bank-specific CSV mapping; validated transfer matching with user review; recurring-bill detection; multi-currency valuations; budget/allocation targets; background reports; richer mobile login and notifications. Each can build on this local foundation.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check frontend/app.js
node --check frontend/connections.js
node --check frontend/bank-callback.js
```

Tests use temporary databases, never your personal data. They cover shortfalls, same-day posting order, recurrence, transfer conservation, source capacity, stale records, precise money input, refunds, card repayments, duplicate imports, atomic import failure, category edits, dataset isolation and HTTP boundaries. Bank-feed tests run against DPAPI and Fernet where available and cover secret protection, production-only configuration, cookie/state binding, callback replay rejection, paginated imports, idempotence, review gating, failed-sync atomicity, reconnection, expiry, revocation and the payment-endpoint prohibition. Platform tests also cover missing/wrong keys, ciphertext tampering, HTTPS authentication, configured callbacks and POSIX file permissions (the permissions test runs only on POSIX). Provider responses are simulated: passing these tests does not verify live bank coverage or provider onboarding.
