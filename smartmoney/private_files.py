"""Small file helpers for local secrets; no secret values in exceptions."""
import os
import stat
from pathlib import Path


def read_private(path: Path) -> bytes:
    # O_NOFOLLOW prevents an unexpected symlink replacing a configured secret.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError('Secret storage must use a regular file.')
        if os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise RuntimeError('Secret files must belong to the service user and have no group/other permissions (chmod 600).')
        value = stream.read(4_000_001)
        if len(value) > 4_000_000:
            raise RuntimeError('Secret storage exceeded its size limit.')
        return value


def create_private(path: Path, value: bytes):
    """Create once, never truncate an existing key."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
