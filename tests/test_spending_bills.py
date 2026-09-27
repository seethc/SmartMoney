"""Invented values only; user screenshots must never be committed."""
from datetime import date, timedelta
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from smartmoney import screenshots, store
from smartmoney.engine import occurrences
from test_screenshots import client, account, line, HEADERS


def report(**changes):
    today = date.today()
    body = dict(confirmed=True, start_date=today.replace(day=1).isoformat(), end_date=today.isoformat(),
                scope='Test accounts', total='110.25', rows=[
                    dict(label='Shopping', amount='125.25', kind='expense', count=4),
                    dict(label='Home & Family', amount='-15.00', kind='expense', count=2),
                    dict(label='Income', amount='950.00', kind='income', count=1),
                    dict(label='Internal Transfers', amount='30.00', kind='transfer', count=2)])
    return body | changes


def test_summary_is_separate_and_replacement_is_explicit(client):
    key = account(client)
    before = client.get('/api/dashboard?dataset=personal').json()
    body = report()
    assert client.post('/api/spending-summaries', json=body, headers=HEADERS).status_code == 200
    after = client.get('/api/dashboard?dataset=personal').json()
    for field in ('accounts', 'transactions', 'categories', 'spending_pence', 'income_pence', 'forecast'):
        assert after[field] == before[field]
    assert after['snoop_summary']['total_pence'] == 11025
    assert client.get('/api/dashboard?dataset=demo').json()['snoop_summary'] is None
    assert client.post('/api/spending-summaries', json=body, headers=HEADERS).status_code == 409
    body.update(expected_revision=1)
    assert client.post('/api/spending-summaries', json=body, headers=HEADERS).status_code == 409
    body.update(replace_existing=True)
    assert client.post('/api/spending-summaries', json=body, headers=HEADERS).status_code == 200
    assert client.post('/api/spending-summaries', json=body, headers=HEADERS).status_code == 409


@pytest.mark.parametrize('change', [dict(total='99'), dict(total='NaN'), dict(scope=' '), dict(confirmed=False),
                                   dict(end_date='2099-01-01'), dict(start_date='2020-01-01'),
                                   dict(rows=[dict(label='X', amount='110.25', kind='income')])])
def test_summary_invalid_input_is_not_saved(client, change):
    assert client.post('/api/spending-summaries', json=report(**change), headers=HEADERS).status_code == 422
    assert client.get('/api/dashboard?dataset=personal').json()['snoop_summary'] is None


def test_spending_geometry_excludes_comparisons_and_retains_unreadable_rows():
    rows = [line('September spend',20,20), line('£110.25',20,60), line('£999.99 vs August',20,110), line('Categories',20,170),
            line('Shopping',50,240), line('£125.25',450,240), line('4 Transactions',50,270), line('£800.00',450,270),
            line('Home & Family',50,340), line('+£15.00',450,340), line('2 Transactions',50,370), line('£90.00',450,370),
            line('Unreadable',50,430), line('3 Transactions',50,460),
            line('Excluded from your spend analysis',20,520), line('Income',50,580), line('+£950.00',450,580),
            line('Internal Transfers',50,680), line('£30.00',450,680)]
    result = screenshots.interpret(rows)
    assert result['type'] == 'spending' and result['candidates'] == []
    assert result['total'] == '110.25' and result['month_hint'] == 'September'
    assert [(r['label'],r['amount'],r['kind']) for r in result['rows']] == [
        ('Shopping','125.25','expense'),('Home & Family','-15.00','expense'),('Unreadable','','expense'),
        ('Income','950.00','income'),('Internal Transfers','30.00','transfer')]


def synthetic_spending():
    font_path=next((str(p) for p in [Path('C:/Windows/Fonts/arial.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.exists()),None)
    if not font_path: pytest.skip('System font required')
    image=Image.new('RGB',(690,1600),'white'); draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(font_path,24)
    for text,x,y in [('September spend',40,70),('£110.25',40,115),('Categories',140,230),
                     ('Shopping',110,340),('£125.25',520,340),('4 Transactions',110,382),('£800.00',520,382),
                     ('Home & Family',110,450),('+£15.00',520,450),('2 Transactions',110,492),('£90.00',520,492),
                     ('Excluded from your spend analysis',40,630),('Income',110,720),('+£950.00',500,720),
                     ('1 Transaction',110,762),('Internal Transfers',110,830),('£30.00',530,830),('2 Transactions',110,872),
                     ('Customise your analysis',40,1000)]:
        draw.text((x,y),text,font=font,fill='#263c34')
    image=image.resize((345,800),Image.Resampling.LANCZOS)
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


def test_real_small_spending_ocr_without_network(client, monkeypatch):
    if not screenshots.executable():pytest.skip('Tesseract required')
    import socket
    def blocked(*args,**kwargs):raise AssertionError('Network call during OCR')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    result=client.post('/api/screenshots/preview',content=synthetic_spending(),headers=HEADERS)
    assert result.status_code==200
    draft=result.json()
    assert draft['type']=='spending' and draft['total']=='110.25'
    assert [(r['label'],r['amount']) for r in draft['rows']]==[('Shopping','125.25'),('Home & Family','-15.00'),('Income','950.00'),('Internal Transfers','30.00')],draft


@pytest.mark.parametrize('frequency,expected', [('weekly',['2024-01-31','2024-02-07','2024-02-14']),
    ('fortnightly',['2024-01-31','2024-02-14']),('monthly',['2024-01-31','2024-02-29','2024-03-31']),
    ('quarterly',['2024-01-31','2024-04-30','2024-07-31']),('yearly',['2024-02-29','2025-02-28','2026-02-28','2027-02-28','2028-02-29'])])
def test_bill_recurrence(frequency, expected):
    schedule={'next_due':expected[0],'month_day':int(expected[0][-2:]),'frequency':frequency}
    assert [d.isoformat() for d in occurrences(schedule,date.fromisoformat(expected[0]),date.fromisoformat(expected[-1]))]==expected
    assert [d.isoformat() for d in occurrences(schedule,date.fromisoformat(expected[0])+timedelta(days=1),date.fromisoformat(expected[-1]))]==expected[1:]


def test_bills_create_reassign_edit_delete_affect_only_forecast(client):
    first=account(client);second=account(client,name='Bills')
    body=dict(account_id=first,name='Internet',amount='-25.00',next_due=date.today().isoformat(),frequency='weekly',kind='expense')
    result=client.post('/api/schedules',json=body,headers=HEADERS);assert result.status_code==200
    key=result.json()['id']
    data=client.get('/api/dashboard?dataset=personal&days=14').json()
    assert len(data['forecast']['events'])==2
    assert data['forecast']['minima'][str(first)]==78200 # allowance plus two bills
    body.update(account_id=second,amount='-30.00',frequency='monthly')
    assert client.put(f'/api/schedules/{key}',json=body,headers=HEADERS).status_code==200
    data=client.get('/api/dashboard?dataset=personal&days=14').json()
    assert data['schedules'][0]['account_id']==second and len(data['forecast']['events'])==1
    assert data['transactions']==[] and all(a['balance_pence']==100000 for a in data['accounts'])
    assert client.put(f'/api/schedules/{key}?dataset=demo',json=body|{'account_id':99999},headers=HEADERS).status_code==404
    assert client.delete(f'/api/schedules/{key}',headers=HEADERS).status_code==200
    assert client.get('/api/dashboard?dataset=personal').json()['schedules']==[]


def test_editing_clamped_month_preserves_original_day(client, monkeypatch):
    import importlib
    api = importlib.import_module('smartmoney.app')
    class FixedDate(date):
        @classmethod
        def today(cls):return cls(2027,2,1)
    key=account(client)
    with store.connection('personal') as db:
        bill=db.execute("INSERT INTO schedules VALUES(NULL,?,'End of month',-1000,'2027-01-31','monthly',31,'expense',NULL)", (key,)).lastrowid
    monkeypatch.setattr(api,'date',FixedDate)
    body=dict(account_id=key,name='End of month',amount='-20',next_due='2027-02-28',frequency='monthly',kind='expense')
    assert client.put(f'/api/schedules/{bill}',json=body,headers=HEADERS).status_code==200
    with store.connection('personal') as db:
        saved=dict(db.execute('SELECT * FROM schedules WHERE id=?',(bill,)).fetchone())
    assert saved['month_day']==31
    assert list(occurrences(saved,date(2027,2,1),date(2027,3,31)))==[date(2027,2,28),date(2027,3,31)]
