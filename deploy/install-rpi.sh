#!/bin/bash
# Run on the Pi from an unpacked release: sudo bash deploy/install-rpi.sh
set -euo pipefail
umask 077
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run this installer with sudo.' >&2
    exit 1
fi
case "$(uname -m)" in
    aarch64|arm64) ;;
    *) echo 'This installer targets 64-bit Raspberry Pi OS (aarch64).' >&2; exit 1 ;;
esac
command -v tesseract >/dev/null || { echo 'Install tesseract-ocr and tesseract-ocr-eng with apt first.' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
source_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ "$source_dir" = /opt/smartmoney ]; then
    echo 'Run this from the unpacked release directory, not /opt/smartmoney.' >&2
    exit 1
fi
for path in /opt/smartmoney /etc/smartmoney /var/lib/smartmoney; do
    if [ -L "$path" ]; then
        echo "Refusing a symbolic link at $path" >&2
        exit 1
    fi
done
if ! id smartmoney >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir /var/lib/smartmoney --shell /usr/sbin/nologin smartmoney
fi
if systemctl is-active --quiet smartmoney.service; then
    systemctl stop smartmoney.service
fi
install -d -m 0755 /opt/smartmoney
# Remove only the explicitly retired code files on upgrade. Financial records
# and old credential files are preserved, but the new service never loads them.
for retired in smartmoney/bankfeed.py smartmoney/openbanking.py smartmoney/providers.py smartmoney/vault.py frontend/connections.html frontend/connections.js frontend/bank-callback.html frontend/bank-callback.js tests/test_openbanking.py; do
    rm -f -- "/opt/smartmoney/$retired"
done
for directory in smartmoney frontend deploy docs tests; do
    install -d -m 0755 "/opt/smartmoney/$directory"
    cp -R "$source_dir/$directory/." "/opt/smartmoney/$directory/"
done
for file in run.py requirements.txt requirements-lock.txt pyproject.toml README.md start.sh; do
    install -m 0644 "$source_dir/$file" "/opt/smartmoney/$file"
done
# Root owns code; the service user can write only its state directory.
chown -R root:root /opt/smartmoney
find /opt/smartmoney/smartmoney /opt/smartmoney/frontend -type d -exec chmod 0755 {} +
find /opt/smartmoney/smartmoney /opt/smartmoney/frontend -type f -exec chmod 0644 {} +
umask 022
python3 -m venv /opt/smartmoney/.venv
/opt/smartmoney/.venv/bin/python -m pip install -r /opt/smartmoney/requirements.txt
chmod -R a+rX /opt/smartmoney/.venv
umask 077
install -d -m 0700 /etc/smartmoney
install -d -m 0700 -o smartmoney -g smartmoney /var/lib/smartmoney
cd /opt/smartmoney
SMARTMONEY_DATA_DIR=/var/lib/smartmoney \
SMARTMONEY_ACCESS_PASSWORD_FILE=/etc/smartmoney/access.password \
    .venv/bin/python -m smartmoney.init_secrets
if [ ! -e /etc/smartmoney/app.conf ]; then
    install -m 0600 deploy/app.conf.example /etc/smartmoney/app.conf
fi
install -m 0644 deploy/smartmoney.service /etc/systemd/system/smartmoney.service
systemctl daemon-reload
systemctl enable --now smartmoney.service
systemctl --no-pager --full status smartmoney.service
echo 'Installed. See docs/raspberry-pi.md for the private access from your laptop and phone.'
