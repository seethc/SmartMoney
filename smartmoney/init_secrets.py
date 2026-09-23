"""Initialize server-local secrets. Run on the Pi, never send keys through chat."""
import os
import secrets
from pathlib import Path

from . import vault
from .private_files import create_private, read_private


def main():
    vault.initialize_key()
    target = os.environ.get('SMARTMONEY_ACCESS_PASSWORD_FILE')
    if target:
        path = Path(target).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            create_private(path, secrets.token_urlsafe(32).encode() + b'\n')
        except FileExistsError:
            pass
        if len(read_private(path).strip()) < 24:
            raise RuntimeError('Existing app password is too short. It has not been overwritten.')
    print('Secrets initialized. Existing files were preserved; no secret values are printed.')


if __name__ == '__main__':
    main()
