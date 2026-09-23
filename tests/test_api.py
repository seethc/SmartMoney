from datetime import date

import pytest
from fastapi.testclient import TestClient

from smartmoney import store
from smartmoney.app import app

HEADERS={'X-SmartMoney':'local'}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    with TestClient(app) as client:
        yield client


def add_account(client,kind='current'):
    response=client.post('/api/accounts?dataset=personal',headers=HEADERS,json={
        'name':'Test','institution':'Test bank','kind':kind,'balance':'-100' if kind=='credit' else '1000',
        'balance_as_of':date.today().isoformat()})
    assert response.status_code==200,response.text
    return response.json()['id']


def payload(key,rows):
    return {'account_id':key,'csv_text':'external_id,date,description,amount,category,kind\n'+rows}


def test_import_is_idempotent_preserves_identical_purchases_and_snapshot(client):
    key=add_account(client)
    body=payload(key,'a,2026-01-01,Coffee,-3.20,Food,expense\nb,2026-01-01,Coffee,-3.20,Food,expense')
    preview=client.post('/api/import/preview',json=body,headers=HEADERS)
    assert preview.json()['new_count']==2
    assert client.get('/api/dashboard?dataset=personal&month=2026-01').json()['transactions']==[]
    first=client.post('/api/import/commit',json=body,headers=HEADERS)
    assert first.json()['imported']==2
    second=client.post('/api/import/commit',json=body,headers=HEADERS)
    assert second.json()=={'imported':0,'duplicates':2}
    data=client.get('/api/dashboard?dataset=personal&month=2026-01').json()
    assert data['spending_pence']==640
    assert data['accounts'][0]['balance_pence']==100000


def test_invalid_import_is_atomic(client):
    key=add_account(client)
    body=payload(key,'a,2026-01-01,Coffee,-3.20,Food,expense\nb,2026-01-02,Bad,NaN,Food,expense')
    assert client.post('/api/import/commit',json=body,headers=HEADERS).status_code==422
    assert client.get('/api/dashboard?dataset=personal&month=2026-01').json()['transactions']==[]


def test_changed_duplicate_id_rejected(client):
    key=add_account(client)
    body=payload(key,'a,2026-01-01,Coffee,-3.20,Food,expense')
    client.post('/api/import/commit',json=body,headers=HEADERS)
    body['csv_text']=body['csv_text'].replace('-3.20','-4.20')
    assert client.post('/api/import/commit',json=body,headers=HEADERS).status_code==422


def test_transfers_card_repayments_refunds_and_adjustments(client):
    key=add_account(client,'credit')
    body=payload(key,'a,2026-01-01,Purchase,-100.00,Shopping,expense\nb,2026-01-02,Repayment,100.00,Transfers,transfer\nc,2026-01-03,Refund,25.00,Shopping,expense\nd,2026-01-04,Value change,300,Valuation,adjustment')
    assert client.post('/api/import/commit',json=body,headers=HEADERS).status_code==200
    data=client.get('/api/dashboard?dataset=personal&month=2026-01').json()
    assert data['spending_pence']==7500
    assert data['income_pence']==0
    assert data['net_cashflow_pence']==-7500


def test_classification_changes_analytics_not_balances(client):
    key=add_account(client)
    client.post('/api/import/commit',json=payload(key,'a,2026-01-01,Transfer,-100,Other,expense'),headers=HEADERS)
    before=client.get('/api/dashboard?dataset=personal&month=2026-01').json()
    row=before['transactions'][0]
    response=client.patch(f"/api/transactions/{row['id']}",json={'category':'Transfers','kind':'transfer'},headers=HEADERS)
    assert response.status_code==200
    after=client.get('/api/dashboard?dataset=personal&month=2026-01').json()
    assert after['spending_pence']==0
    assert after['net_worth_pence']==before['net_worth_pence']


def test_local_boundary_and_personal_demo_isolation(client):
    assert client.get('/api/dashboard?dataset=personal').json()['accounts']==[]
    assert len(client.get('/api/dashboard?dataset=demo').json()['accounts'])==5
    assert client.post('/api/accounts',json={}).status_code==403
    assert client.post('/api/accounts',json={},headers={**HEADERS,'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/dashboard',headers={'Host':'evil.example'}).status_code==400
    response=client.get('/api/dashboard')
    assert response.headers['cache-control']=='no-store'
    assert 'frame-ancestors' in response.headers['content-security-policy']


def test_money_precision_and_dates(client):
    for value in ('NaN','Infinity','1.001'):
        assert client.post('/api/accounts',headers=HEADERS,json={'name':'a','institution':'b','balance':value,'balance_as_of':date.today().isoformat()}).status_code==422
    assert client.get('/api/dashboard?month=oops').status_code==422
    assert client.get('/api/dashboard?days=0').status_code==422


def test_planned_payment_validation_and_removal(client):
    key=add_account(client)
    entry={'account_id':key,'name':'Bill','amount':'-20','next_due':date.today().isoformat(),'frequency':'monthly','kind':'expense'}
    result=client.post('/api/schedules',headers=HEADERS,json=entry)
    assert result.status_code==200,result.text
    data=client.get('/api/dashboard?dataset=personal').json()
    assert data['forecast']['minima'][str(key)]<=98000
    key2=result.json()['id']
    assert client.delete(f'/api/schedules/{key2}',headers=HEADERS).status_code==200
    assert client.get('/api/dashboard?dataset=personal').json()['schedules']==[]
