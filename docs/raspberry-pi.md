# SmartMoney on your Raspberry Pi

Your Pi already runs SmartMoney, and you administer it through **Raspberry Pi
Connect → Remote shell**. The new version replaces bank setup with Snoop screenshot
imports. Updating files on Windows does not update the Pi automatically.

## Upgrade your existing Pi through Connect

The GitHub repository is the project's source. The `openbanking-reference` tag
preserves the old implementation; use the current main branch for this version.
Run the following small commands in Connect's Remote shell, not by pasting the
contents of an archive or transfer file:

```sh
sudo apt update
sudo apt install git python3-venv python3-pip tesseract-ocr tesseract-ocr-eng
mkdir -p ~/smartmoney-releases
cd ~/smartmoney-releases
git clone https://github.com/seethc/SmartMoney.git snoop-release
cd snoop-release
```

If `snoop-release` already exists, choose a different new folder name rather than
overwriting files. For subsequent updates, clone into a fresh release directory.
Before installing, preserve your existing records and configuration:

```sh
sudo systemctl stop smartmoney
sudo install -d -m 0700 /var/backups/smartmoney
sudo sh -c 'umask 077; tar -czf /var/backups/smartmoney/before-snoop-$(date +%Y%m%d-%H%M%S).tar.gz /var/lib/smartmoney /etc/smartmoney'
sudo bash deploy/install-rpi.sh
sudo systemctl status smartmoney --no-pager
```

If backup or installation fails, keep the error for diagnosis. Restart the old
service only if its code has not yet been replaced. The installer preserves your
existing app password, configuration and databases. It removes the known retired
bank connector/pages from `/opt/smartmoney`, and no longer loads the old vault/key.
Old credential files are retained for recovery, not used by the new product. If
you granted bank consent, revoke it yourself in the provider/bank controls.

Installation downloads packages once. Screenshot interpretation subsequently
runs offline using locally installed Tesseract and English language data.

## Open from Windows and your Pixel

Continue using your existing private HTTPS address on **both devices**, with
Tailscale connected. Find the exact address on the Pi with:

```sh
sudo tailscale serve status
```

Use the `https://...ts.net` serving address, not a `login.tailscale.com` setup link.
Your existing configuration should already contain that origin in
`/etc/smartmoney/app.conf`. You do not need to register an application or callback.

Sign in as **smartmoney** using your existing app password. If you need to read it,
run this in your private Connect shell and do not paste the result into chat:

```sh
sudo cat /etc/smartmoney/access.password
```

| Browser location | Address |
| --- | --- |
| Pi desktop, including through Connect screen sharing | `http://127.0.0.1:8765` |
| Windows laptop, Chrome or Edge | Your existing Pi private HTTPS address |
| Pixel, Chrome or installed web app | The same Pi private HTTPS address |

`127.0.0.1` means the device running the browser. It does not reach your Pi from
Windows or the Pixel. Both remote devices share the same database on the Pi.
Refresh a page after saving on another device.

## Import Snoop screenshots

1. Open Snoop and refresh/check your accounts. Note the **balance refresh date**.
2. Capture the account cards or list with GBP amounts and account names. If the
   carousel hides accounts, scroll sideways and capture the next group. A crop
   around account cards helps exclude spending panels and other figures.
3. Open **Snoop screenshots** in SmartMoney on your Pixel or Windows browser.
4. Choose **My real data** (or Demo to practise), select up to six PNG/JPEG/WebP
   screenshots, then choose **Read screenshots**. Files stay on your Pi for OCR;
   they are not sent to any cloud service and are not retained on disk.
5. Each result starts skipped. Select its existing account, or **Create a new
   account** and enter the institution/type. Never use Net worth as another account.
6. Check every digit, minus sign and account mapping against the image. Enter the
   actual balance date. Remove duplicate cards from overlapping screenshots.
7. Confirm and save. Existing balances change atomically; history does not change.
8. On Accounts, set buffers and spending allowances. On Cash flow, enter planned
   bills/income. Continue importing transaction CSVs for spending analysis.

Credit-card debt must be negative. A screenshot date does not prove a bank balance
is current. The reader does not recognise bank logos or infer institutions from
nicknames. Ambiguous text requires correction. No transfers are executed.

## Pi 4B with 1 GB RAM

Use 64-bit Raspberry Pi OS and Python 3.11+. Close memory-heavy Pi desktop/browser
apps when testing; use the Windows/Pixel browser for the dashboard.

The reader serialises image decoding/OCR, limits OCR images to 1200 × 2400 pixels,
sets Tesseract to one CPU thread, and times out OCR after 45 seconds. The systemd
service has a 384 MB soft memory threshold and 512 MB hard cap. If it exceeds the
cap, systemd can terminate/restart the service; no unreviewed balances are saved.
These are configured limits, not a measured claim about your particular Pi.

Check the installed engine and memory while processing a screenshot:

```sh
tesseract --version
tesseract --list-langs
free -h
sudo systemctl show smartmoney -p MemoryCurrent -p MemoryPeak -p MemoryMax
```

English (`eng`) must appear. If OCR is unavailable, install the packages above and
reload the page. For slow reads, crop a smaller set of cards. No LLM or GPU needed.
SmartMoney has no runtime internet dependency for OCR, but your browser must still
reach the Pi. Tailscale/Connect are separate network services; for a strict offline
test use a browser on the Pi at localhost. Snoop needs internet to update its banks.

## Install the frontend as an app

On Pixel Chrome, open your private HTTPS address and use the browser menu's
**Install app / Add to home screen** option. Windows Chrome/Edge can install the
same site as an app window. Both are frontends for the Pi; Python stays on the Pi.
Keep the Pi running and Tailscale connected. Financial records are not cached for
offline viewing in the browser.

## Operations and recovery

```sh
sudo systemctl status smartmoney --no-pager
sudo journalctl -u smartmoney -n 50 --no-pager
sudo systemctl restart smartmoney
```

Data is in `/var/lib/smartmoney/personal.sqlite3` and `demo.sqlite3`. Back up while
the service is stopped. Snapshots and their previous values are in `snapshot_audit`;
images/OCR text are not saved. Backups should be encrypted and private. Existing
legacy database tables are left untouched but are not read by the current app.

If Connect screen sharing stalls, use a separate Connect Remote shell:

```sh
systemctl --user restart rpi-connect-wayvnc.service
rpi-connect doctor
```

Screen sharing is not needed for daily access from Windows or Pixel.

## Fresh Pi installation / release bundle alternative

Install `python3-venv python3-pip ca-certificates tesseract-ocr tesseract-ocr-eng`,
clone this repository, and run `sudo bash deploy/install-rpi.sh` in the checkout.
Configure Tailscale Serve to forward privately to `http://127.0.0.1:8765`; set
`SMARTMONEY_PUBLIC_URL` to that HTTPS origin in `/etc/smartmoney/app.conf`, then
restart the service. Do not expose port 8765 publicly or disable authentication.

Alternatively build `dist/smartmoney-rpi.tar.gz` using `python tools/package_pi.py`
on Windows. The existing `tools/serve_pi_package.py --host LAPTOP_IP` helper serves
only the bundle on port 8876 for 30 minutes. Download through Connect's shell using
`curl --fail http://LAPTOP_IP:8876/smartmoney-rpi.tar.gz -o ~/smartmoney-rpi.tar.gz`,
check its SHA256 against `dist/smartmoney-rpi.sha256`, and extract into a **new**
directory before installing. Never paste archive contents into the shell.

Dependencies are installed from `requirements.txt` for the Pi's Python/ARM platform.
`requirements-lock.txt` records Windows package versions, not a verified ARM lock.
