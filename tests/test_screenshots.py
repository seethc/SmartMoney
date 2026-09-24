import io
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont, ImageOps

from smartmoney import screenshots, store
from smartmoney.app import app

HEADERS = {'X-SmartMoney': 'local'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    with TestClient(app) as client:
        yield client


def account(client, **changes):
    body = {'name': 'Everyday', 'institution': 'Test Bank', 'balance': '1000',
            'balance_as_of': date.today().isoformat(), 'buffer': '100',
            'daily_allowance': '12', 'can_fund': True}
    body.update(changes)
    result = client.post('/api/accounts', headers=HEADERS, json=body)
    assert result.status_code == 200, result.text
    return result.json()['id']


def row(key, **changes):
    value = {'account_id': key, 'balance': '1234.56', 'balance_as_of': date.today().isoformat(),
             'expected_balance_pence': 100000, 'expected_balance_as_of': date.today().isoformat()}
    value.update(changes)
    return value


def save(client, rows, **changes):
    body = {'confirmed': True, 'rows': rows}
    body.update(changes)
    return client.post('/api/screenshots/commit', json=body, headers=HEADERS)


def records(client):
    return client.get('/api/dashboard?dataset=personal').json()


def test_commit_preserves_preferences_and_history_and_audits_previous_value(client):
    key = account(client)
    result = save(client, [row(key)])
    assert result.json() == {'updated': 1, 'created': 0, 'unchanged': 0}
    data = records(client)
    assert data['accounts'][0]['balance_pence'] == 123456
    assert data['accounts'][0]['buffer_pence'] == 10000
    assert data['accounts'][0]['daily_allowance_pence'] == 1200
    assert data['accounts'][0]['can_fund'] == 1
    assert data['transactions'] == []
    with store.connection('personal') as db:
        audit = dict(db.execute('SELECT * FROM snapshot_audit').fetchone())
        assert audit['previous_balance_pence'] == 100000
        assert audit['balance_pence'] == 123456
    again = save(client, [row(key, expected_balance_pence=123456)])
    assert again.json()['unchanged'] == 1
    with store.connection('personal') as db:
        assert db.execute('SELECT count(*) FROM snapshot_audit').fetchone()[0] == 1


def test_new_account_and_retry_never_duplicate(client):
    fresh = {'name': 'Holiday', 'institution': 'Test', 'kind': 'savings', 'balance': '25.10', 'balance_as_of': date.today().isoformat()}
    assert save(client, [fresh]).json()['created'] == 1
    assert save(client, [fresh]).status_code == 409
    saved = records(client)['accounts']
    assert len(saved) == 1 and saved[0]['can_fund'] == 0


def test_batch_conflict_and_duplicate_are_atomic(client):
    key = account(client)
    for rows in ([row(key), row(999)], [row(key), row(key)], [row(key), {'name': '', 'balance': '0', 'balance_as_of': date.today().isoformat()}]):
        assert save(client, rows).status_code in (404, 422)
        assert records(client)['accounts'][0]['balance_pence'] == 100000
        with store.connection('personal') as db:
            assert db.execute('SELECT count(*) FROM snapshot_audit').fetchone()[0] == 0


def test_stale_preview_older_date_future_and_precision_are_rejected(client):
    key = account(client)
    for change, status in [({'expected_balance_pence': 1}, 409),
                           ({'balance_as_of': (date.today()-timedelta(days=1)).isoformat()}, 409),
                           ({'balance_as_of': (date.today()+timedelta(days=1)).isoformat()}, 422),
                           ({'balance': 'NaN'}, 422), ({'balance': '1.001'}, 422)]:
        assert save(client, [row(key, **change)]).status_code == status
    assert save(client, [row(key)], confirmed=False).status_code == 422


def test_credit_debt_and_workspace_isolation(client):
    key = account(client, kind='credit', can_fund=False, balance='-1000')
    assert save(client, [row(key, expected_balance_pence=-100000)]).status_code == 422
    assert save(client, [row(key, balance='-307.10', expected_balance_pence=-100000)]).status_code == 200
    assert len(client.get('/api/dashboard?dataset=demo').json()['accounts']) == 5


def line(text, x, y, width=None, height=24):
    # Keep tokens separate exactly as Tesseract TSV does.
    words=[]
    for token in text.split():
        size=len(token)*12
        words.append({'text':token,'left':x,'width':size})
        x+=size+8
    return {'text':text,'words':words,'left':words[0]['left'],'width':width or x-words[0]['left'],
            'top':y,'height':height,'confidence':92}


def test_snoop_carousel_labels_below_and_summary_rejection():
    lines=[line('Your Money',10,20),line('£2,560.72',10,100),line('£1,280.56',220,100),line('-£307.10',450,100),
           line('Net worth',10,140),line('My Main',220,140),line('Barclaycard',445,140),line('Account',220,175),
           line('£237.20',10,300),line('March spending',10,340)]
    result=screenshots.interpret(lines)
    assert [(r['label'],r['balance']) for r in result['candidates']]==[('My Main Account','1280.56'),('Barclaycard','-307.10')]


def test_horizontal_list_labels_and_non_gbp():
    lines=[line('Chase £42.50',10,10),line('Revolut £-3.20',10,120),line('Euro €99.00',10,240)]
    result=screenshots.interpret(lines)
    assert [(r['label'],r['balance']) for r in result['candidates']]==[('Chase','42.50'),('Revolut','-3.20')]
    assert any('Non-GBP' in n for n in result['notices'])


def test_clipped_card_still_separates_neighbouring_labels():
    lines=[line('-£307.10',10,100),line('£51',220,100),line('£112.89',440,100),
           line('Barclaycard',10,140),line('Mo',220,140),line('Holiday',440,140),
           line('>',440,170),line('Jo',220,180),line('Account',440,195)]
    result=screenshots.interpret(lines)
    assert [(r['label'],r['balance']) for r in result['candidates']]==[('Barclaycard','-307.10'),('Holiday Account','112.89')]
    assert any('incomplete' in n for n in result['notices'])


def test_update_legacy_database_does_not_load_bank_links(client):
    key=account(client)
    with store.connection('personal') as db:
        db.execute('CREATE TABLE bank_links(account_id INTEGER, planning_balance_pence INTEGER)')
        db.execute('INSERT INTO bank_links VALUES(?,1)',(key,))
    store.initialize()
    assert 'forecast_balance_pence' not in records(client)['accounts'][0]
    assert save(client,[row(key)]).status_code==200


def image_bytes(size=(300,300), fmt='PNG'):
    image=Image.new('RGB',size,'white'); data=io.BytesIO();image.save(data,format=fmt);return data.getvalue()


def test_invalid_images_busy_and_body_limits(client, monkeypatch):
    assert client.post('/api/screenshots/preview',content=b'not an image',headers=HEADERS).status_code==422
    assert client.post('/api/screenshots/preview',content=image_bytes((99,300)),headers=HEADERS).status_code==422
    assert client.post('/api/screenshots/preview',content=image_bytes(fmt='GIF'),headers=HEADERS).status_code==422
    assert client.post('/api/screenshots/preview',content=b'x'*8_000_001,headers=HEADERS).status_code==413
    screenshots.LOCK.acquire()
    try:
        assert client.post('/api/screenshots/preview',content=image_bytes(),headers=HEADERS).status_code==503
    finally:
        screenshots.LOCK.release()
    monkeypatch.setattr(screenshots,'executable',lambda:None)
    assert client.post('/api/screenshots/preview',content=image_bytes(),headers=HEADERS).status_code==503
    assert screenshots.LOCK.acquire(blocking=False)
    screenshots.LOCK.release()


def test_preview_does_not_write_records_and_old_routes_are_gone(client, monkeypatch):
    monkeypatch.setattr(screenshots,'read_lines',lambda raw:[line('Chase £23.00',10,10)])
    result=client.post('/api/screenshots/preview',content=image_bytes(),headers=HEADERS)
    assert result.status_code==200
    assert result.json()['candidates'][0]['balance']=='23.00'
    assert records(client)['accounts']==[]
    for route in ('/connections.html','/bank-callback.html','/api/openbanking/status','/openbanking-callback'):
        assert client.get(route).status_code==404


def test_timeout_releases_worker(client,monkeypatch):
    monkeypatch.setattr(screenshots,'executable',lambda:'tesseract')
    def timeout(*args,**kwargs):
        assert kwargs['env']['OMP_THREAD_LIMIT']=='1'
        raise subprocess.TimeoutExpired('tesseract',45)
    monkeypatch.setattr(screenshots.subprocess,'run',timeout)
    assert client.post('/api/screenshots/preview',content=image_bytes(),headers=HEADERS).status_code==422
    assert screenshots.LOCK.acquire(blocking=False)
    screenshots.LOCK.release()


def synthetic_carousel(dark=False):
    # Synthetic account cards based on the public Snoop layout; no user data.
    font_path=next((str(p) for p in [Path('C:/Windows/Fonts/arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()),None)
    if not font_path:
        pytest.skip('A scalable system font is required for the OCR integration fixture')
    font=ImageFont.truetype(font_path,32)
    img=Image.new('RGB',(1100,650),'white'); draw=ImageDraw.Draw(img)
    for text,x,y in [('Your Money',30,30),('Updated today, 09:01',30,85),('£2,560.72',40,200),('£1,280.56',390,200),('-£307.10',770,200),
                     ('Net worth',40,255),('My Main',390,255),('Account',390,297),('Barclaycard',745,255),('£237.20',40,450),('March spending',40,505)]:
        draw.text((x,y),text,font=font,fill='black')
    if dark:img=ImageOps.invert(img)
    buffer=io.BytesIO();img.save(buffer,format='PNG');return buffer.getvalue()


@pytest.mark.parametrize('dark',[False,True])
def test_real_offline_ocr_carousel(client,dark,monkeypatch):
    if not screenshots.executable():
        pytest.skip('Tesseract is not installed')
    # A real OCR request with Python network connections prohibited.
    import socket
    def no_network(*args,**kwargs):raise AssertionError('OCR attempted a network connection')
    monkeypatch.setattr(socket.socket,'connect',no_network)
    result=client.post('/api/screenshots/preview',content=synthetic_carousel(dark),headers=HEADERS)
    assert result.status_code==200,result.text
    rows=result.json()['candidates']
    assert [(r['label'],r['balance']) for r in rows]==[('My Main Account','1280.56'),('Barclaycard','-307.10')],result.json()
    assert records(client)['accounts']==[]
