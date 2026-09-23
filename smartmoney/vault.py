"""Windows DPAPI or authenticated encryption with a separate Linux key file."""
import ctypes
import json
import os
from ctypes import wintypes
from threading import RLock
from pathlib import Path
import tempfile

from cryptography.fernet import Fernet, InvalidToken

from . import store
from .private_files import read_private, create_private

LOCK = RLock()
USE_DPAPI = os.name == 'nt'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data: bytes, decrypt=False) -> bytes:
    if not USE_DPAPI:
        try:
            cipher = Fernet(read_private(key_path()).strip())
            return cipher.decrypt(data) if decrypt else cipher.encrypt(data)
        except FileNotFoundError:
            raise RuntimeError('Bank vault key is missing. Run python -m smartmoney.init_secrets on the server. Never replace a lost key for an existing vault; restore its original key.') from None
        except (ValueError, InvalidToken):
            raise RuntimeError('Bank vault could not be unlocked. Check the original key and restore a known-good backup if needed.') from None
        except OSError:
            raise RuntimeError('Cannot read the bank vault key. Check its path and service-user permissions.') from None
    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypto = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    fn = crypto.CryptUnprotectData if decrypt else crypto.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError('Windows could not unlock the local bank connection. Use the original Windows user profile.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def key_path():
    configured = os.environ.get('SMARTMONEY_VAULT_KEY_FILE')
    if configured:
        return Path(configured).expanduser()
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'smartmoney' / 'vault.key'


def vault_path():
    return store.DATA / ('openbanking.dpapi' if USE_DPAPI else 'openbanking.fernet')


def initialize_key():
    """Explicit first-run operation; never silently recover by generating a new key."""
    if USE_DPAPI:
        return
    path = key_path()
    if path.exists():
        protect(b'key validation')
        return
    if vault_path().exists() or (store.DATA / 'openbanking.dpapi').exists():
        raise RuntimeError('An existing bank vault needs its original key. Do not initialize a replacement; restore or reconnect in a fresh data directory.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        create_private(path, Fernet.generate_key() + b'\n')
    except FileExistsError:
        pass  # A concurrent initialization won. Validate its key.
    protect(b'key validation')


def read():
    with LOCK:
        path = vault_path()
        if not path.exists():
            other = store.DATA / ('openbanking.fernet' if USE_DPAPI else 'openbanking.dpapi')
            if other.exists():
                raise RuntimeError('This bank vault belongs to another operating system. Keep the original safe and set up bank consent again in a fresh data directory.')
            return {}
        try:
            result = json.loads(protect(read_private(path), decrypt=True))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeError, OSError):
            raise RuntimeError('Cannot read the bank vault. Check file permissions or restore a known-good backup.') from None


def write(value):
    with LOCK:
        # Verify existing ciphertext before writing, including platform/key mismatch.
        read()
        encrypted = protect(json.dumps(value).encode())
        store.DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = vault_path()
        fd, name = tempfile.mkstemp(prefix='.bank-vault-', dir=store.DATA)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
