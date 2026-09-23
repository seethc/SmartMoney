#!/bin/sh
set -eu
umask 077
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m smartmoney.init_secrets
exec .venv/bin/python run.py
