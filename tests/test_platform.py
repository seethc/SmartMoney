import ast
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from smartmoney import config, store, vault
from smartmoney.app import app
from smartmoney.private_files import create_private


@pytest.fixture
def linux_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, 'USE_DPAPI', False)
    monkeypatch.setattr(store, 'DATA', tmp_path / 'data')
    monkeypatch.setenv('SMARTMONEY_VAULT_KEY_FILE', str(tmp_path / 'keys' / 'vault.key'))
    vault.initialize_key()
    return vault.key_path()


def test_fernet_persists_and_rejects_tampering_without_overwriting(linux_vault):
    value={'private_key':'test secret','sessions':[{'session_id':'test consent'}]}
    vault.write(value)
    assert vault.read()==value
    original=vault.vault_path().read_bytes()
    assert b'test secret' not in original and b'test consent' not in original
    tampered=original[:20]+b'!'+original[21:]
    vault.vault_path().write_bytes(tampered)
    with pytest.raises(RuntimeError,match='unlocked'):
        vault.read()
    with pytest.raises(RuntimeError):
        vault.write({'replacement':True})
    assert vault.vault_path().read_bytes()==tampered


def test_missing_key_never_silently_resets_existing_vault(linux_vault):
    vault.write({'secret':'retained'})
    original=vault.vault_path().read_bytes()
    linux_vault.unlink()
    with pytest.raises(RuntimeError,match='original key'):
        vault.initialize_key()
    with pytest.raises(RuntimeError,match='key is missing'):
        vault.read()
    assert not linux_vault.exists() and vault.vault_path().read_bytes()==original


def test_wrong_key_cannot_replace_existing_vault(linux_vault):
    vault.write({'secret':'retained'})
    original=vault.vault_path().read_bytes()
    linux_vault.write_bytes(Fernet.generate_key())
    with pytest.raises(RuntimeError,match='unlocked'):
        vault.write({'new':'data'})
    assert vault.vault_path().read_bytes()==original


def test_initialization_is_idempotent_and_windows_migration_is_explicit(linux_vault):
    original=linux_vault.read_bytes()
    vault.initialize_key()
    assert linux_vault.read_bytes()==original
    store.DATA.mkdir()
    (store.DATA/'openbanking.dpapi').write_bytes(b'windows ciphertext')
    with pytest.raises(RuntimeError,match='another operating system'):
        vault.read()
    with pytest.raises(RuntimeError):
        vault.write({})
    assert not vault.vault_path().exists()


@pytest.mark.skipif(os.name!='posix',reason='Requires actual POSIX file permissions')
def test_linux_secret_permissions_and_symlinks(linux_vault):
    vault.write({'secret':'test'})
    assert vault.vault_path().stat().st_mode & 0o777 == 0o600
    assert linux_vault.stat().st_mode & 0o777 == 0o600
    linux_vault.chmod(0o644)
    with pytest.raises(RuntimeError,match='permissions'):
        vault.read()
    linux_vault.chmod(0o600)
    target=linux_vault.with_name('actual.key')
    linux_vault.rename(target)
    linux_vault.symlink_to(target)
    with pytest.raises(RuntimeError):
        vault.read()


@pytest.mark.parametrize('url', ['http://pi.local','https://pi.local/path','https://u:p@pi.local',
                              'https://pi.local?query=1','https://*.example.com','https://pi.local:bad'])
def test_invalid_remote_origins_fail_closed(monkeypatch,url):
    monkeypatch.setenv('SMARTMONEY_PUBLIC_URL',url)
    monkeypatch.delenv('SMARTMONEY_ACCESS_PASSWORD_FILE',raising=False)
    with pytest.raises(RuntimeError):
        config.from_environment()


def test_remote_configuration_requires_private_password_file(tmp_path,monkeypatch):
    monkeypatch.setenv('SMARTMONEY_PUBLIC_URL','https://pi.test.ts.net')
    monkeypatch.delenv('SMARTMONEY_ACCESS_PASSWORD_FILE',raising=False)
    with pytest.raises(RuntimeError,match='PASSWORD_FILE'):
        config.from_environment()
    password=tmp_path/'access.password'
    create_private(password,b'a-test-only-password-of-at-least-24-characters')
    monkeypatch.setenv('SMARTMONEY_ACCESS_PASSWORD_FILE',str(password))
    settings=config.from_environment()
    assert settings.remote and settings.callback_url=='https://pi.test.ts.net/openbanking-callback'
    assert 'test-only-password' not in repr(settings)


def test_https_auth_host_and_origin_boundary(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    password='a-test-only-password-of-at-least-24-characters'
    monkeypatch.setattr(config,'settings',config.Settings('https://pi.test.ts.net',password.encode()))
    with TestClient(app,base_url='https://pi.test.ts.net') as client:
        for route in ('/','/api/dashboard','/api/openbanking/certificate','/api/runtime'):
            response=client.get(route)
            assert response.status_code==401
            assert response.headers['cache-control']=='no-store'
        assert client.get('/api/dashboard',auth=('smartmoney','wrong')).status_code==401
        client.auth=('smartmoney',password)
        assert client.get('/api/runtime').json()['public_url']=='https://pi.test.ts.net'
        assert client.get('/api/dashboard',headers={'Host':'evil.example'}).status_code==400
        headers={'X-SmartMoney':'local','Origin':'https://evil.example'}
        assert client.post('/api/accounts',headers=headers,json={}).status_code==403
        headers['Origin']='https://pi.test.ts.net'
        assert client.post('/api/accounts',headers=headers,json={}).status_code==422  # Validation reached.
        assert client.get('http://pi.test.ts.net/api/dashboard').status_code==400


def test_python_311_syntax_compatibility():
    root=Path(__file__).resolve().parent.parent
    for path in [root/'run.py', *sorted((root/'smartmoney').glob('*.py'))]:
        ast.parse(path.read_text(encoding='utf-8'),feature_version=(3,11))
