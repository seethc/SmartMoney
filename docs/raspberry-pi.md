# SmartMoney on your Raspberry Pi: what to do next

## Your current position

- The package was downloaded to the Pi and its checksum matched.
- You ran the installer and confirmed **SmartMoney is active (running)**.
- Raspberry Pi Connect **Remote shell and screen sharing are now working**.
- You confirmed the dashboard opens in the Pi’s browser.
- Direct access from your Windows laptop and Pixel, and a real bank sync, are still to be confirmed.

**Continue at step 2 below to connect your Windows laptop and Pixel. Step 1 is already complete. You do not need to download or reinstall SmartMoney.** The installation commands are kept at the end for future reference. This guide is updated in the Windows project; an older copy already installed on the Pi is not automatically updated.

SmartMoney's Python backend and database are on the Pi. Raspberry Pi Connect lets you control that Pi. Your Windows laptop and Pixel will both open the same Pi-hosted SmartMoney directly through one private HTTPS address. Neither device needs its own Python backend or copy of the financial database.

## 1. Dashboard on the Pi — already confirmed

1. Keep your working Connect Remote shell available. Retrieve your generated **SmartMoney app password**:

```sh
sudo cat /etc/smartmoney/access.password
```

2. Keep the password private and store it in your password manager. This is an app password, not a bank password; do not paste it into chat.
3. In **Connect → Screen sharing**, open Chromium **inside the Pi's desktop**. Type this in that browser's address bar:

```text
http://127.0.0.1:8765
```

4. At the browser's login prompt, enter username **smartmoney** and the password from step 1.
5. Confirm the dashboard opens. You can explore **Demo workspace**, whose balances are fictional. **My real data** should be empty until you add or connect accounts; that is expected.

The browser must be running on the Pi for this address to reach the Pi. Typing the same address into your Windows or Pixel browser would reach that device instead.

If the dashboard does not load, use Connect Remote shell to check:

```sh
sudo systemctl status smartmoney --no-pager
sudo journalctl -u smartmoney -n 30 --no-pager
```

Report the browser's message and relevant errors, without passwords. Do not rerun the installer merely because a browser cannot connect.

## 2. Set up access from BOTH Windows and your Pixel

Do this after confirming the dashboard opens. Set up the final HTTPS address **before registering the bank application**, so you can register one callback that works from either your laptop or phone from the start. If you already registered a localhost callback, update the existing application's redirect settings and verify it again in SmartMoney.

1. Install and connect Tailscale on **all three devices**. Sign into the same personal Tailscale account/network on each:

| Device | Setup | Its role |
| --- | --- | --- |
| Raspberry Pi | Follow the [Linux installation instructions](https://tailscale.com/docs/install/linux), using Connect Remote shell for Pi commands. | Runs SmartMoney and stores the database. |
| Windows laptop | Download and install Tailscale using the [Windows instructions](https://tailscale.com/docs/install/windows). Open Tailscale from the system tray, sign in, and ensure it is connected. | Opens SmartMoney in your normal Windows Edge or Chrome browser. |
| Google Pixel | Install and sign into Tailscale using the [Android instructions](https://tailscale.com/docs/install/android), then connect it. | Opens SmartMoney in Chrome or the installed web app. |

Confirm all three devices appear in your Tailscale network. Restrict access to the intended user/devices. Being on the same home Wi-Fi alone is not enough for this private HTTPS setup: Tailscale must also be connected on the device you are using.

2. In Connect Remote shell on the Pi, run:

```sh
sudo tailscale serve --bg http://127.0.0.1:8765
```

The first run may print a setup/approval link beginning with `https://login.tailscale.com/f/serve?...`. Open that link and complete the HTTPS/Serve enablement prompt. **That link is not your SmartMoney address and must not be put in `SMARTMONEY_PUBLIC_URL`.** Use **Serve**, which is private to your Tailscale network; do not enable the public Funnel feature. [Tailscale Serve documentation](https://tailscale.com/docs/features/tailscale-serve)

Return to the Pi's Remote shell and retrieve the actual service address:

```sh
sudo tailscale serve status
```

Look for an address shaped like `https://raspberrypi.YOUR-TAILNET.ts.net`, forwarding to `http://127.0.0.1:8765`. Copy the actual HTTPS address from your output, not this example. If status reports no Serve configuration, finish the approval page, rerun `sudo tailscale serve --bg http://127.0.0.1:8765`, and check status again. [Serve status reference](https://tailscale.com/docs/reference/tailscale-cli/serve#get-the-status)

3. Edit the app configuration on the Pi:

```sh
sudo nano /etc/smartmoney/app.conf
```

Replace the existing `SMARTMONEY_PUBLIC_URL` line with your real HTTPS origin. The following is a placeholder, not an address to copy unchanged:

```text
SMARTMONEY_PUBLIC_URL=https://YOUR-PI.YOUR-TAILNET.ts.net
```

Use no path such as `/connections.html` or `/openbanking-callback`, and no `login.tailscale.com` setup link. If you already entered the setup link, replace that line with the actual HTTPS address from `tailscale serve status`. Keep other settings unchanged. In nano, save with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**.

4. Restart SmartMoney and check it is running:

```sh
sudo systemctl restart smartmoney
sudo systemctl status smartmoney --no-pager
```

5. **Test on your Windows laptop first.** Keep Tailscale connected on Windows and the Pi. Open **Edge or Chrome on Windows itself**, outside Raspberry Pi Connect, and enter the exact HTTPS address printed by Serve. Sign in with username **smartmoney** and your app password. Bookmark this address. Confirm the dashboard opens and select the intended workspace, such as **My real data**.
6. **Test on your Pixel.** Keep Tailscale connected on the phone and Pi. Open **Chrome on the Pixel**, enter the **same HTTPS address**, and sign in with the **same SmartMoney username/password**. Select the same workspace and transaction month when comparing the two devices.

Both devices now read the **same database on the Pi**. You do not need a separate bank connection for each device. After a sync or edit on one device, refresh the other to see the latest records. The Windows laptop and Pixel can be used independently; either can be off while you use the other. The Pi must stay running.

### Which address belongs in which browser?

| Where the browser is running | Address to use |
| --- | --- |
| On the Pi desktop through Connect screen sharing | `http://127.0.0.1:8765` for the local dashboard check; use the configured HTTPS address for bank consent after step 2. |
| On your Windows laptop | The Pi's **actual private HTTPS address**, with Tailscale connected. |
| On your Pixel | The **same private HTTPS address**, with Tailscale connected. |

Do not use `127.0.0.1:8765` in Windows or on the phone for this setup. It means that device itself. The example `YOUR-PI.YOUR-TAILNET.ts.net` is a placeholder, so replace it with the real address Serve reports. Do not use the old laptop package-download address on port 8876; that temporary server was only for transferring the installer.

If the address works on the Pi but not on Windows or the Pixel, first check that the affected device's Tailscale app is connected to the same network, the Pi is online, and you copied the exact HTTPS address. On the Pi, `sudo tailscale serve status` shows the current Serve configuration. Record any browser error rather than changing the backend to listen publicly.

The backend remains bound to Pi loopback. Serve supplies HTTPS and forwards requests locally; the app also requires its password. No router port forwarding, public website, SSH tunnel or Connect screen-sharing session is needed for everyday access from your laptop and phone. Connect remains available for administering the Pi.

## 3. Connect and test one real bank

An active SmartMoney service does not mean a bank is connected. Provider registration, the availability of your specific accounts, bank consent and a successful sync still need verification.

### Registration fields for your Pi

The privacy and terms pages were added after the first Pi installation. Copy the updated `frontend/privacy.html`, `frontend/terms.html` and `frontend/connections.html` into `/opt/smartmoney/frontend/` on the Pi before submitting these fields. This is a static-page update; do not rerun the full installer or regenerate your bank certificate. The pages retain the same app login/private-network protection as the dashboard. Read them and make sure they describe your intended personal use.

| Enable Banking field | Value for this installation |
| --- | --- |
| Allowed redirect URLs | `https://YOUR-PI.YOUR-TAILNET.ts.net/openbanking-callback` |
| Privacy policy URL | `https://YOUR-PI.YOUR-TAILNET.ts.net/privacy.html` |
| Terms of service URL | `https://YOUR-PI.YOUR-TAILNET.ts.net/terms.html` |
| Data protection email | Your own monitored email address, entered directly in the provider form. |
| Application description | `Private, self-hosted dashboard for my own bank accounts. Read-only balances, spending analysis and cash-flow planning; no payment initiation.` |

Use the exact callback above, with no wildcard or trailing slash, and confirm it matches SmartMoney's Bank connections page. Upload the existing public certificate downloaded from the Pi-backed app; do not have the provider generate a replacement private key.

Enable Banking requires these details for production. Its FAQ says the policy links and contact email are not checked for restricted activation by linking your own accounts; unrestricted activation includes validation. This does not mean the fields should contain invented or unrelated URLs. These notices cover this private personal installation, not a public service. Do not use Enable Banking's own privacy/terms URLs as if they were SmartMoney's policies. [Provider requirements and restricted-mode exception](https://enablebanking.com/docs/faq/#why-are-a-data-protection-email-and-links-to-app-terms-and-privacy-required-in-production)

Keep the notice URLs private for this own-account setup. If the provider rejects them or you later seek unrestricted access, retain the message and resolve the notice-hosting requirement separately; do not expose financial endpoints publicly. Confirm both pages open while logged in before submitting registration.

### Complete registration and consent

1. Open **Bank connections** from the final private HTTPS address. You can do this from Windows Edge/Chrome or Pixel Chrome. Start and finish each consent attempt on the same device and browser; do not begin on the laptop and open the callback on the phone. If your bank requests approval in its mobile app, approve there and return to the original browser to finish. Use the browser before testing an installed web-app window.
2. Choose **Prepare connection**, then **Download public certificate**. This prepares the Pi's bank-connection key, separate from the vault encryption key created by the installer. Do not upload the old Windows certificate.
3. Follow the page's link to the **Enable Banking control panel**, sign up, and register a **PRODUCTION / Account Information (AIS)** application. Upload the public certificate downloaded from this Pi-backed app and register the exact callback shown in SmartMoney. It should now begin with your private HTTPS address.
4. Complete the provider's required own-account linking/activation. Accept agreements and approve bank access yourself. SmartMoney requests account information and cannot execute payments.
5. Paste the application UUID into SmartMoney and choose **Verify application**, then **Load available banks**. Bank/account coverage is determined by that actual list and the bank's consent screen.
6. Choose one bank, select **Continue to bank consent**, approve access in the bank's website/app and return to SmartMoney in the original browser. If the provider rejects registration or the callback, retain the error for diagnosis; do not publicly expose the server as a workaround.
7. Choose **Sync now**. Confirm real balances and booked transactions appear in **My real data**. Review imported transaction categories and mark transfers between your own accounts as **transfer** so they are excluded from spending/income.
8. Configure each account's purpose, safety buffer and daily spending allowance, and enter planned bills/income before using the cash-flow suggestions. Make any actual transfers manually in your banking apps.

The first connector supports eligible GBP current/savings accounts. Unsupported currencies/account types and entries without stable IDs are reported as skipped. Bank sync is manual. Use the connection page to check its last successful sync and consent expiry.

## 4. Optional app installation on your Pixel and Windows laptop

**Pixel:** once it opens correctly in Chrome at the private HTTPS address:

1. Open Chrome's menu and choose **Install and create shortcut → Install** (wording varies by Chrome version).
2. Launch SmartMoney from its new home-screen icon and confirm it can load your dashboard. If it asks again, use the same app username/password.
3. Keep the Pi awake and connected, and Tailscale connected on your Pixel. Your Windows laptop can be off.

**Windows laptop:** you can continue using your bookmarked HTTPS address in Edge or Chrome. If you prefer a separate app window, use the browser’s install-app option while viewing that address. Keep Tailscale connected when opening either the browser or installed app. Do not launch the old Windows Python server to access the Pi-hosted app.

Both installed apps are frontends for the same Pi backend. This installs the existing web app in its own window; it does not install Python on your phone or laptop. Financial data is not cached for offline viewing. [Google's Android installation instructions](https://support.google.com/chrome/answer/9658361?co=GENIE.Platform%3DAndroid&hl=en)

## If Connect screen sharing stalls again

Keep or open a separate **Connect → Remote shell** session. Close the stuck screen-sharing browser tab, then run the commands that restored screen sharing in this session:

```sh
systemctl --user restart rpi-connect-wayvnc.service
rpi-connect doctor
```

Retry screen sharing in a fresh tab. This restarts the screen-sharing component, not SmartMoney or the Pi. If it fails, retain the diagnostic output. Do not repeat the old large clipboard transfer. [Raspberry Pi Connect troubleshooting](https://www.raspberrypi.com/documentation/services/connect.html#troubleshooting)

Screen sharing is not required once you can open SmartMoney through its private HTTPS address. Connect remains useful for administering the Pi.

## Storage, backups and Windows migration

- `/var/lib/smartmoney/personal.sqlite3`: financial records (not encrypted by the app).
- `/var/lib/smartmoney/demo.sqlite3`: separate fictional demo records.
- `/var/lib/smartmoney/openbanking.fernet`: authenticated encrypted bank private key and consent/session metadata.
- `/etc/smartmoney/vault.key`: encryption key, root-only on disk. systemd passes a read-only credential copy to the service user.
- `/etc/smartmoney/access.password`: random app-login password, passed the same way.
- `/etc/smartmoney/app.conf`: non-secret origin configuration.

The service uses `UMask=0077` and a private state directory. Linux secret files must be owned by the reading user and must not grant group/other access; symlinked secrets are rejected. The key is separate from the database directory, so a copy of the encrypted vault alone does not expose bank secrets. Someone with root access or both the key and vault can decrypt them. This is not full-disk encryption. [Fernet documentation](https://cryptography.io/en/stable/fernet/), [systemd credentials](https://systemd.io/CREDENTIALS/)

Stop the service before backing up SQLite. Back up `/var/lib/smartmoney` and `/etc/smartmoney` to private encrypted backup storage, preserving ownership and permissions, then restart. Restore both the vault and its matching key together. A missing/wrong key or damaged ciphertext produces an error; SmartMoney does not silently create a replacement or clear the old vault.

**Do not copy `openbanking.dpapi` from Windows to the Pi.** Windows DPAPI is tied to the original Windows user. Keep the Windows installation intact and reconnect banks using a freshly prepared Pi certificate/application. If needed, you can transfer `personal.sqlite3` separately while both servers are stopped; make the Pi copy owned by `smartmoney` with mode 600. Existing account identity links can deduplicate reconnected bank accounts, but do not import overlapping CSV history. There is no automatic Windows-secret migration.

## Operations and verification

```sh
sudo systemctl status smartmoney --no-pager
sudo journalctl -u smartmoney -n 50 --no-pager
sudo systemctl restart smartmoney
sudo systemctl stop smartmoney
```

The service is enabled at boot and restarts after a failure. Provider requests need outbound HTTPS and an accurate Pi clock. Access logs are disabled to avoid recording bank callback codes. Review logs locally before sharing anything from them.

For tests, use the unpacked source as your regular Pi user in Connect’s Remote shell, with temporary test databases:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

These tests include Linux vault permissions when run on Linux. Tests use simulated provider responses; they do not connect real banks. Check the app first in the Pi’s browser through Connect screen sharing (if available), then on the Pixel over private HTTPS, then complete one real bank consent/sync. Reboot the Pi and verify the service starts again before relying on unattended operation.

For a foreground development run without systemd, `sh start.sh` creates a virtual environment and local encryption key, then starts the loopback server. Its default data directory is `./data`, and the Linux key defaults to `~/.config/smartmoney/vault.key`. The service installation uses the separate paths above. Do not mix those stores or run both servers on the same port.

## Reference only: installation on a fresh Pi

**Already completed on your current Pi; skip this section for normal use.** Target: 64-bit Raspberry Pi OS with Python 3.11+ and systemd.

You can do this entirely through **Raspberry Pi Connect → Remote shell**. You do not need to open Windows PowerShell, run SSH, or start from a particular folder on your computer. Connect's Remote shell is a terminal running on the Pi. [Official Connect documentation](https://www.raspberrypi.com/documentation/services/connect.html)

The application package initially exists on your Windows laptop. Transfer it as a normal download over your home network. **Do not paste the old large transfer file into a terminal**; that method has been retired after a remote-terminal stall.

1. On the laptop, start the temporary package server (Codex can do this). For a manual start, run the following in Windows PowerShell, replacing `LAPTOP_IP` with the laptop's Wi-Fi IPv4 address from `ipconfig`:

```powershell
& 'C:\SmartRoom\smartmoney\.venv\Scripts\python.exe' 'C:\SmartRoom\smartmoney\tools\serve_pi_package.py' --host LAPTOP_IP
```

The helper serves **only** `smartmoney-rpi.tar.gz`, with no directory listing or access to databases/keys, and stops after 30 minutes. Keep the laptop awake. If Windows Firewall blocks the Pi's download, use a narrowly scoped temporary rule for TCP 8876 from the Pi/home subnet; do not disable the firewall.

2. In **Connect → Remote shell**, run this small command, replacing `LAPTOP_IP` with the address printed by the helper:

```sh
curl --fail --show-error --connect-timeout 10 --max-time 60 http://LAPTOP_IP:8876/smartmoney-rpi.tar.gz -o ~/smartmoney-rpi.tar.gz
sha256sum ~/smartmoney-rpi.tar.gz
```

Compare the hash with the one shown by the helper or `dist/smartmoney-rpi.sha256` on your laptop. Continue only when it matches. Connect is the remote terminal; the download itself goes directly from Pi to laptop across your home network. No SSH command from Windows is needed. If the command times out, do not repeatedly retry: check the server is still running, both devices are on the same non-guest network, and the Windows firewall rule.

3. After the package has downloaded and its checksum matches, run these commands **inside Connect's Remote shell**:

```sh
uname -m
python3 --version
sudo apt update
sudo apt install python3-venv python3-pip ca-certificates
mkdir -p ~/smartmoney-install
cd ~/smartmoney-install
tar -xzf ~/smartmoney-rpi.tar.gz
cd smartmoney
sudo bash deploy/install-rpi.sh
```

The package contains code/assets only, not bank credentials or financial records. Keep passwords and encryption keys out of chat. To rebuild the archive and checksum after changing code, run `python tools/package_pi.py` on the development computer. The download replaces only a previous `~/smartmoney-rpi.tar.gz` package, not installed app data.

`uname -m` must report `aarch64` (or `arm64`). The installer deliberately declines 32-bit OS images. It creates a dedicated `smartmoney` service user, installs code in `/opt/smartmoney`, creates a Python virtual environment, generates new Pi-local secrets, and starts the service at boot. Existing secrets, configuration and financial data are preserved on reruns. An upgrade stops an existing service while replacing code; check its status if an upgrade fails.

The archive contains application code, UI, tests, scripts and documentation. It excludes personal/demo databases, Windows credentials, logs and the Windows virtual environment. Pi dependencies are resolved from `requirements.txt` for its Python/ARM platform; `requirements-lock.txt` records the Windows development environment and is not claimed as a verified ARM lockfile.

Raspberry Pi OS requires Python packages to be installed in a virtual environment on Bookworm and later; the installer follows that approach. [Raspberry Pi documentation](https://www.raspberrypi.com/documentation/computers/os.html#python-on-raspberry-pi)


## Reference only: optional SSH tunnel

This is only for people who choose to use direct SSH instead of Connect. Stop any Windows SmartMoney server using port 8765, then run the following in Windows PowerShell, replacing the username and hostname/IP:

```powershell
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_USER@YOUR_PI
```

Keep that terminal open and browse to `http://127.0.0.1:8765` on Windows. The tunnel forwards it to the Pi. The backend remains bound to Pi loopback; do not open port 8765 to the LAN or internet.

