import ast
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smartmoney import config, store
from smartmoney.app import app
from smartmoney.private_files import create_private


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
    assert settings.remote and settings.public_url=='https://pi.test.ts.net'
    assert 'test-only-password' not in repr(settings)


def test_https_auth_host_and_origin_boundary(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    password='a-test-only-password-of-at-least-24-characters'
    monkeypatch.setattr(config,'settings',config.Settings('https://pi.test.ts.net',password.encode()))
    with TestClient(app,base_url='https://pi.test.ts.net') as client:
        for route in ('/','/api/dashboard','/api/screenshots/status','/api/runtime'):
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
