"""Explicit origin configuration. Backend always binds to loopback."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .private_files import read_private

LOCAL_ORIGIN = 'http://127.0.0.1:8765'


@dataclass(frozen=True)
class Settings:
    public_url: str = LOCAL_ORIGIN
    password: bytes | None = field(default=None, repr=False)

    @property
    def remote(self):
        return self.public_url != LOCAL_ORIGIN


def from_environment():
    value = os.environ.get('SMARTMONEY_PUBLIC_URL', LOCAL_ORIGIN).rstrip('/')
    url = urlsplit(value)
    if (not url.hostname or url.username is not None or url.password is not None or
            url.path or url.query or url.fragment or '*' in value or
            any(char.isspace() for char in value)):
        raise RuntimeError('SMARTMONEY_PUBLIC_URL must be an origin only, such as https://your-pi.example.ts.net.')
    try:
        url.port
    except ValueError:
        raise RuntimeError('SMARTMONEY_PUBLIC_URL has an invalid port.') from None
    if value != LOCAL_ORIGIN and url.scheme != 'https':
        raise RuntimeError('Remote access requires an HTTPS SMARTMONEY_PUBLIC_URL.')
    password = None
    password_file = os.environ.get('SMARTMONEY_ACCESS_PASSWORD_FILE')
    if password_file:
        try:
            password = read_private(Path(password_file)).strip()
        except OSError:
            raise RuntimeError('Cannot read SMARTMONEY_ACCESS_PASSWORD_FILE.') from None
        if len(password) < 24 or len(password) > 256 or any(c < 33 or c > 126 for c in password):
            raise RuntimeError('The app access password must contain 24–256 printable non-space ASCII characters.')
    if value != LOCAL_ORIGIN and password is None:
        raise RuntimeError('Set SMARTMONEY_ACCESS_PASSWORD_FILE before enabling remote access.')
    return Settings(value, password)


settings = from_environment()
