from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from smartmoney import store, vault, config
from smartmoney.app import app
from smartmoney.bankfeed import CALLBACK, EnableBanking, FeedError, balances, normalise_transaction, utcnow

HEADERS={'X-SmartMoney':'local'}
APP_ID='f079ca9c-87c8-47dd-b5ac-ce96fa95a321'
UID='d795a7cd-b38e-4c96-97de-96e33408a001'
SESSION='f079ca9c-87c8-47dd-b5ac-ce96fa95a322'


def transaction(reference='bank-id-1',amount='12.34'):
    return {'entry_reference':reference,'status':'BOOK','credit_debit_indicator':'DBIT',
            'booking_date':date.today().isoformat(),'transaction_amount':{'currency':'GBP','amount':amount},
            'remittance_information':['Coffee'],'creditor':{'name':'Cafe'}}


def balance_payload():
    return {'balances':[
        {'balance_type':'ITBD','balance_amount':{'currency':'GBP','amount':'1000.00'},'reference_date':date.today().isoformat()},
        {'balance_type':'ITAV','balance_amount':{'currency':'GBP','amount':'950.00'},'reference_date':date.today().isoformat()}]}


@pytest.fixture(params=['native', 'fernet'])
def feed(tmp_path,monkeypatch,request):
    monkeypatch.setattr(store,'DATA',tmp_path)
    if request.param == 'fernet':
        monkeypatch.setattr(vault,'USE_DPAPI',False)
    monkeypatch.setenv('SMARTMONEY_VAULT_KEY_FILE',str(tmp_path/'keys'/'vault.key'))
    vault.initialize_key()
    observed={'calls':[],'transactions':[transaction(),transaction('bank-id-2')],'active':True,'environment':'PRODUCTION','fail':False}
    def fake(self,method,path,**kwargs):
        observed['calls'].append((method,path,kwargs))
        if path=='/application':
            return {'environment':observed['environment'],'services':['AIS'],'active':observed['active'],'redirect_urls':[config.settings.callback_url]}
        if path=='/aspsps':
            return {'aspsps':[{'name':'Barclays','country':'GB','psu_types':['personal'],
                'maximum_consent_validity':90*86400,'auth_methods':[{'name':'redirect','psu_type':'personal','approach':'REDIRECT'}]}]}
        if path=='/auth':
            observed['state']=kwargs['json']['state']
            return {'url':'https://auth.enablebanking.com/ais/start?sessionid=test'}
        if path=='/sessions':
            return {'session_id':SESSION,'aspsp':{'name':'Barclays'},
                'access':{'valid_until':(utcnow()+timedelta(days=30)).isoformat()},
                'accounts':[{'uid':UID,'identification_hash':'stable-identity','currency':'GBP','cash_account_type':'CACC','product':'Current account',
                             'account_id':{'iban':'DO-NOT-RETAIN'},'postal_address':{'street_name':'DO-NOT-RETAIN'}}]}
        if path.endswith('/balances'):
            return balance_payload()
        if path.endswith('/transactions'):
            if observed['fail']:
                raise FeedError('Simulated provider failure')
            return {'transactions':observed['transactions']}
        if method=='DELETE' and path=='/sessions/'+SESSION:
            return {}
        raise AssertionError((method,path))
    monkeypatch.setattr(EnableBanking,'request',fake)
    with TestClient(app) as client:
        yield client,observed


def setup(client):
    assert client.post('/api/openbanking/prepare',headers=HEADERS,json={}).status_code==200
    response=client.post('/api/openbanking/configure',headers=HEADERS,json={'app_id':APP_ID})
    assert response.status_code==200,response.text


def connect(client,observed):
    setup(client)
    response=client.post('/api/openbanking/connect',headers=HEADERS,json={'bank':'Barclays'})
    assert response.status_code==200,response.text
    response=client.post('/api/openbanking/complete',headers=HEADERS,json={'state':observed['state'],'code':'test-code'})
    assert response.status_code==200,response.text


def test_private_key_is_protected_and_public_routes_never_leak_secrets(feed):
    client,_=feed
    setup(client)
    ciphertext=vault.vault_path().read_bytes()
    assert b'PRIVATE KEY' not in ciphertext
    assert b'private_key' not in ciphertext
    assert 'PRIVATE KEY' in vault.read()['private_key']
    assert 'PRIVATE KEY' not in client.get('/api/openbanking/status').text
    cert=client.get('/api/openbanking/certificate')
    assert cert.status_code==200
    assert 'BEGIN CERTIFICATE' in cert.text and 'PRIVATE' not in cert.text


def test_only_production_application_is_accepted(feed):
    client,observed=feed
    client.post('/api/openbanking/prepare',headers=HEADERS,json={})
    observed['environment']='SANDBOX'
    response=client.post('/api/openbanking/configure',headers=HEADERS,json={'app_id':APP_ID})
    assert response.status_code==422 and 'PRODUCTION' in response.json()['detail']
    assert not client.get('/api/openbanking/status').json()['configured']


def test_pending_application_does_not_start_consent(feed):
    client,observed=feed
    observed['active']=False
    setup(client)
    assert client.post('/api/openbanking/connect',headers=HEADERS,json={'bank':'Barclays'}).status_code==422
    assert all(path!='/auth' for _,path,_ in observed['calls'])


def test_callback_requires_bound_cookie_and_one_use_state(feed):
    client,observed=feed
    setup(client)
    client.post('/api/openbanking/connect',headers=HEADERS,json={'bank':'Barclays'})
    assert client.post('/api/openbanking/complete',headers=HEADERS,json={'state':'wrong','code':'x'}).status_code==403
    cookie=client.cookies.get('smartmoney_consent')
    client.cookies.clear()
    assert client.post('/api/openbanking/complete',headers=HEADERS,json={'state':observed['state'],'code':'x'}).status_code==403
    client.cookies.set('smartmoney_consent',cookie)
    payload={'state':observed['state'],'code':'x'}
    assert client.post('/api/openbanking/complete',headers=HEADERS,json=payload).status_code==200
    assert client.post('/api/openbanking/complete',headers=HEADERS,json=payload).status_code==403
    assert 'DO-NOT-RETAIN' not in str(vault.read())
    assert 'test-code' not in str(vault.read())


def test_sync_is_idempotent_and_requires_classification_review(feed):
    client,observed=feed
    connect(client,observed)
    first=client.post('/api/openbanking/sync',headers=HEADERS,json={})
    assert first.status_code==200,first.text
    assert first.json()['imported']==2
    second=client.post('/api/openbanking/sync',headers=HEADERS,json={})
    assert second.json()['imported']==0
    data=client.get('/api/dashboard?dataset=personal').json()
    assert len(data['accounts'])==1 and len(data['transactions'])==2
    assert data['accounts'][0]['balance_pence']==100000
    assert data['accounts'][0]['forecast_balance_pence']==95000
    assert data['forecast']['minima']['1']==95000
    assert data['unreviewed_count']==2 and data['spending_pence']==0
    key=data['transactions'][0]['id']
    client.patch(f'/api/transactions/{key}',headers=HEADERS,json={'category':'Eating out','kind':'expense'})
    client.post('/api/openbanking/sync',headers=HEADERS,json={})
    data=client.get('/api/dashboard?dataset=personal').json()
    assert data['unreviewed_count']==1 and data['spending_pence']==1234
    assert 'Eating out' in data['categories']
    assert len(client.get('/api/dashboard?dataset=demo').json()['accounts'])==5


def test_bank_failure_does_not_partially_update_accounts(feed):
    client,observed=feed
    connect(client,observed)
    observed['fail']=True
    assert client.post('/api/openbanking/sync',headers=HEADERS,json={}).status_code==422
    assert client.get('/api/dashboard?dataset=personal').json()['accounts']==[]
    assert client.get('/api/openbanking/status').json()['connections'][0]['last_sync'] is None


def test_reconnect_deduplicates_and_disconnect_keeps_history(feed):
    client,observed=feed
    connect(client,observed)
    client.post('/api/openbanking/sync',headers=HEADERS,json={})
    connect(client,observed)
    result=client.post('/api/openbanking/sync',headers=HEADERS,json={})
    assert result.json()['imported']==0 and result.json()['accounts_updated']==1
    assert client.post('/api/openbanking/disconnect/1',headers=HEADERS,json={}).status_code==200
    assert len(client.get('/api/dashboard?dataset=personal').json()['transactions'])==2


def test_changed_bank_amount_returns_to_review(feed):
    client,observed=feed
    connect(client,observed)
    client.post('/api/openbanking/sync',headers=HEADERS,json={})
    rows=client.get('/api/dashboard?dataset=personal').json()['transactions']
    for row in rows:
        client.patch(f"/api/transactions/{row['id']}",headers=HEADERS,json={'category':'Food','kind':'expense'})
    observed['transactions'][0]['transaction_amount']['amount']='15.00'
    result=client.post('/api/openbanking/sync',headers=HEADERS,json={})
    assert result.json()['changed']==1
    assert client.get('/api/dashboard?dataset=personal').json()['unreviewed_count']==1


def test_demo_has_no_external_connection_side_effects(feed):
    client,observed=feed
    for path in ('prepare','banks','sync'):
        assert client.post('/api/openbanking/'+path+'?dataset=demo',headers=HEADERS,json={}).status_code==422
    assert observed['calls']==[]


def test_payment_endpoint_is_impossible():
    with pytest.raises(FeedError,match='account-information'):
        EnableBanking({}).request('POST','/payments',json={})


def test_unstable_id_pending_and_foreign_transactions_are_skipped():
    row=transaction()
    del row['entry_reference']
    assert normalise_transaction(row)==(None,'missing_id')
    row=transaction();row['status']='PDNG'
    assert normalise_transaction(row)==(None,'pending')
    row=transaction();row['transaction_amount']['currency']='EUR'
    assert normalise_transaction(row)==(None,'currency')


def test_available_balance_cannot_inflate_cash_with_overdraft_credit():
    payload=balance_payload()
    payload['balances'][1]['balance_amount']['amount']='2000'
    booked,planning,_,_=balances(payload)
    assert booked==planning==100000
    payload['balances']=payload['balances'][1:]
    with pytest.raises(FeedError,match='booked balance'):
        balances(payload)


def test_transaction_pagination_detects_loops(monkeypatch):
    monkeypatch.setattr(EnableBanking,'request',lambda *a,**k:{'transactions':[],'continuation_key':'same'})
    with pytest.raises(FeedError,match='repeated'):
        EnableBanking({}).transactions(UID)


def test_expired_consent_does_not_block_a_renewed_connection(feed):
    client,observed=feed
    connect(client,observed)
    config=vault.read()
    config['sessions'][0]['valid_until']=(utcnow()-timedelta(days=1)).isoformat()
    vault.write(config)
    assert client.get('/api/openbanking/status').json()['connections'][0]['expired']
    assert client.post('/api/openbanking/sync',headers=HEADERS,json={}).status_code==422
    connect(client,observed)
    result=client.post('/api/openbanking/sync',headers=HEADERS,json={})
    assert result.status_code==200,result.text
    assert result.json()['accounts_updated']==1
    assert result.json()['skipped']['expired_consents']==1


def test_https_consent_uses_configured_callback_and_secure_cookie(feed,monkeypatch):
    client,observed=feed
    password=b'a-test-only-app-password-at-least-24-chars'
    monkeypatch.setattr(config,'settings',config.Settings('https://pi.test.ts.net',password))
    client.base_url='https://pi.test.ts.net'
    client.auth=('smartmoney',password.decode())
    setup(client)
    status=client.get('/api/openbanking/status').json()
    assert status['callback_url']=='https://pi.test.ts.net/openbanking-callback'
    response=client.post('/api/openbanking/connect',headers={**HEADERS,'Origin':'https://pi.test.ts.net'},json={'bank':'Barclays'})
    assert response.status_code==200,response.text
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    body=next(kwargs['json'] for _,path,kwargs in observed['calls'] if path=='/auth')
    assert body['redirect_url']==status['callback_url']
    result=client.post('/api/openbanking/complete',headers=HEADERS,json={'state':observed['state'],'code':'test'})
    assert result.status_code==200,result.text


def test_real_transport_signs_jwt_and_does_not_follow_redirects(monkeypatch):
    import httpx
    import jwt
    from cryptography import x509
    from smartmoney.bankfeed import make_keys
    config={**make_keys(),'app_id':APP_ID}
    public_key=x509.load_pem_x509_certificate(config['certificate'].encode()).public_key()
    observed=[]
    def respond(request):
        token=request.headers['Authorization'].removeprefix('Bearer ')
        claims=jwt.decode(token,public_key,algorithms=['RS256'],audience='api.enablebanking.com',issuer='enablebanking.com')
        assert claims['exp']-claims['iat']==300
        assert jwt.get_unverified_header(token)['kid']==APP_ID
        assert request.url.host=='api.enablebanking.com'
        observed.append(request)
        return httpx.Response(302,headers={'Location':'https://example.com/untrusted'})
    real_client=httpx.Client
    def transport_client(**kwargs):
        assert kwargs['follow_redirects'] is False
        return real_client(transport=httpx.MockTransport(respond),**kwargs)
    monkeypatch.setattr(httpx,'Client',transport_client)
    with pytest.raises(FeedError,match='HTTP 302'):
        EnableBanking(config).request('GET','/application')
    assert len(observed)==1
