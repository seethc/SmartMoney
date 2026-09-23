"""Local setup and consent orchestration for a real Enable Banking AIS feed."""
import hmac
import secrets
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import store, vault, config as app_config
from .bankfeed import (EnableBanking, FeedError, balances, digest, make_keys,
                       minimal_session, normalise_transaction, utcnow)

router = APIRouter()


def local_only(dataset):
    if dataset != 'personal':
        raise HTTPException(422, 'Bank connections are available only in My real data. Demo data stays separate.')


def load():
    try:
        return vault.read()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


def public_status(config):
    return {'prepared':bool(config.get('certificate')), 'configured':bool(config.get('app_id')),
            'app_id':config.get('app_id'), 'callback_url':app_config.settings.callback_url,
            'public_url':app_config.settings.public_url,
            'storage':'Windows user protection' if vault.USE_DPAPI else 'Encrypted server vault',
            'environment':config.get('environment'),
            'active':config.get('active',False), 'verified_at':config.get('verified_at'),
            'connections':[{'index':i,'bank':s['bank'],'accounts':len(s['accounts']),
                'valid_until':s['valid_until'],'last_sync':s.get('last_sync'),'active':s.get('active',True),
                'expired':not consent_current(s)}
                for i,s in enumerate(config.get('sessions',[]))]}


def consent_current(session):
    try:
        expiry = datetime.fromisoformat(session['valid_until'].replace('Z','+00:00'))
        return expiry.tzinfo is not None and expiry > utcnow()
    except (KeyError, AttributeError, ValueError, TypeError):
        return False


@router.get('/api/openbanking/status')
def status(dataset: Literal['demo','personal']='personal'):
    if dataset == 'demo':
        return {'demo':True}
    with vault.LOCK:
        return public_status(load())


@router.post('/api/openbanking/prepare')
def prepare(dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config = load()
        if not config.get('certificate'):
            config.update(make_keys())
            try:
                vault.write(config)
            except RuntimeError as exc:
                raise HTTPException(503,str(exc)) from None
        return public_status(config)


@router.get('/api/openbanking/certificate')
def certificate(dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config=load()
        if not config.get('certificate'):
            raise HTTPException(404,'Prepare your local application certificate first.')
        return Response(config['certificate'],media_type='application/x-pem-file',
                        headers={'Content-Disposition':'attachment; filename="smartmoney-public.crt"'})


class Configure(BaseModel):
    app_id: UUID


@router.post('/api/openbanking/configure')
def configure(item: Configure, dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config = load()
        if config.get('app_id') and config['app_id'] != str(item.app_id):
            raise HTTPException(409,'This local certificate is already associated with a different application. Keep using its application ID.')
        proposed = {**config,'app_id':str(item.app_id)}
        try:
            app = EnableBanking(proposed).application()
        except FeedError as exc:
            raise HTTPException(422,str(exc)) from None
        proposed.update(environment=app['environment'],active=app['active'],verified_at=utcnow().isoformat())
        vault.write(proposed)
        return public_status(proposed)


@router.post('/api/openbanking/banks')
def list_banks(dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        client=EnableBanking(load())
        try:
            app=client.application()
            rows=client.banks()
        except FeedError as exc:
            raise HTTPException(422,str(exc)) from None
        return {'active':app['active'],'banks':[{'name':b['name'],'country':b['country'],'beta':b.get('beta',False)} for b in rows]}


class StartConsent(BaseModel):
    bank: str = Field(min_length=1,max_length=160)


@router.post('/api/openbanking/connect')
def connect(item: StartConsent, response: Response, dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config=load()
        client=EnableBanking(config)
        try:
            app=client.application()
            if not app['active']:
                raise FeedError('Activate restricted production access by linking your own account in the Enable Banking control panel first.')
            bank=next((b for b in client.banks() if b['name']==item.bank),None)
            if bank is None:
                raise FeedError('Choose an available UK personal bank from the provider list.')
            validity=min(int(bank['maximum_consent_validity']),90*86400)
            if validity<=60:
                raise FeedError('The bank is not offering a usable consent period.')
            state,cookie=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
            body={'aspsp':{'name':bank['name'],'country':'GB'},'psu_type':'personal','state':state,
                  'redirect_url':app_config.settings.callback_url,'access':{'balances':True,'transactions':True,
                  'valid_until':(utcnow()+timedelta(seconds=validity-60)).isoformat()}}
            methods=bank.get('auth_methods',[])
            if methods:
                method=next((m for m in methods if m.get('approach')=='REDIRECT' and m.get('psu_type')=='personal' and not m.get('hidden_method')),None)
                if method is None:
                    raise FeedError('This bank has no supported redirect authentication method. SmartMoney never collects bank login credentials.')
                body['auth_method']=method['name']
            result=client.request('POST','/auth',json=body)
            url=result.get('url','')
            parsed=urlparse(url)
            if parsed.scheme!='https' or parsed.netloc!='auth.enablebanking.com' or not parsed.path.startswith('/ais/'):
                raise FeedError('The provider returned an unexpected consent URL.')
        except (FeedError, KeyError, ValueError) as exc:
            raise HTTPException(422,str(exc) if isinstance(exc,FeedError) else 'The provider returned incomplete bank metadata.') from None
        config['pending']={'state':digest(state),'cookie':digest(cookie),'expires':time.time()+900,'bank':bank['name'],
                           'origin':app_config.settings.public_url}
        vault.write(config)
        response.set_cookie('smartmoney_consent',cookie,httponly=True,samesite='lax',max_age=900,
                            secure=app_config.settings.remote,path='/api/openbanking')
        return {'url':url}


@router.get('/openbanking-callback')
def callback():
    return FileResponse(Path(__file__).resolve().parent.parent/'frontend'/'bank-callback.html')


class CompleteConsent(BaseModel):
    code: str = Field(default='',max_length=4096)
    state: str = Field(min_length=1,max_length=256)
    error: str = Field(default='',max_length=120)


@router.post('/api/openbanking/complete')
def complete(item: CompleteConsent, request: Request, response: Response, dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config=load()
        pending=config.get('pending',{})
        cookie=request.cookies.get('smartmoney_consent','')
        if (pending.get('expires',0)<time.time() or not cookie or
            pending.get('origin') != app_config.settings.public_url or
            not hmac.compare_digest(pending.get('state',''),digest(item.state)) or
            not hmac.compare_digest(pending.get('cookie',''),digest(cookie))):
            raise HTTPException(403,'This bank connection attempt expired or belongs to a different browser/address. Start again from the configured SmartMoney address.')
        del config['pending']
        vault.write(config)  # consume state before exchanging code; never replay a code
        response.delete_cookie('smartmoney_consent',path='/api/openbanking')
        if item.error or not item.code:
            raise HTTPException(400,'Bank consent was cancelled or not completed. No account data has been imported.')
        try:
            raw=EnableBanking(config).request('POST','/sessions',json={'code':item.code})
            session=minimal_session(raw)
            if session['bank'] != pending['bank']:
                raise FeedError('The authorised bank did not match the selected bank. Start again.')
        except FeedError as exc:
            raise HTTPException(422,str(exc)) from None
        config.setdefault('sessions',[]).append(session)
        vault.write(config)
        return {'connected':True,'bank':session['bank'],'accounts':len(session['accounts'])}


def fetch_sync(config):
    client=EnableBanking(config)
    staged, skipped, identities = [], Counter(), set()
    sessions=[]
    for session in reversed(config.get('sessions',[])):
        if not session.get('active',True):
            continue
        if not consent_current(session):
            skipped['expired_consents']+=1
            continue
        sessions.append(session)
        for account in session['accounts']:
            if account['currency']!='GBP':
                skipped['non_gbp_accounts']+=1
                continue
            if account['type'] not in ('CACC','SVGS'):
                skipped['unsupported_account_types']+=1
                continue
            identity=account['identity']
            if not identity:
                skipped['accounts_without_stable_id']+=1
                continue
            if identity in identities:
                continue
            identities.add(identity)
            value,planning,as_of,balance_type=balances(client.request('GET',f"/accounts/{account['uid']}/balances"))
            transactions=[]
            for row in client.transactions(account['uid']):
                record,reason=normalise_transaction(row)
                if record:
                    transactions.append(record)
                else:
                    skipped['transactions_'+reason]+=1
            staged.append({'account':account,'bank':session['bank'],'balance':value,'planning':planning,
                           'as_of':as_of,'balance_type':balance_type,'transactions':transactions})
    if not sessions:
        if skipped['expired_consents']:
            raise FeedError('Bank consent expired. Choose your bank and approve access again before syncing.')
        raise FeedError('Connect a bank before syncing.')
    return staged,dict(skipped),sessions


def commit_sync(staged):
    inserted, updated, stamp = 0, 0, utcnow().isoformat()
    with store.connection('personal') as db:
        db.execute('BEGIN IMMEDIATE')
        for entry in staged:
            a=entry['account']
            link=db.execute('SELECT * FROM bank_links WHERE identity_hash=?',(a['identity'],)).fetchone()
            if link:
                key=link['account_id']
                db.execute('UPDATE accounts SET balance_pence=?,balance_as_of=? WHERE id=?',(entry['balance'],entry['as_of'],key))
            else:
                name=entry['bank']+' · '+a['label']
                key=db.execute('INSERT INTO accounts VALUES(NULL,?,?,?,?,?,?,?,?,?)',
                    (name[:80],entry['bank'][:80],'savings' if a['type']=='SVGS' else 'current',
                     'Bank feed · configure your forecast',entry['balance'],0,0,entry['as_of'],0)).lastrowid
            db.execute('INSERT INTO bank_links VALUES(?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET planning_balance_pence=excluded.planning_balance_pence,balance_type=excluded.balance_type,last_sync=excluded.last_sync',
                       (key,a['identity'],entry['bank'],entry['planning'],entry['balance_type'],stamp))
            for row in entry['transactions']:
                old=db.execute('SELECT * FROM transactions WHERE account_id=? AND external_id=?',(key,row['external_id'])).fetchone()
                if old:
                    if any(old[field]!=row[field] for field in ('date','description','amount_pence')):
                        db.execute('UPDATE transactions SET date=?,description=?,amount_pence=?,needs_review=1 WHERE id=?',
                                   (row['date'],row['description'],row['amount_pence'],old['id']))
                        updated+=1
                else:
                    db.execute('INSERT INTO transactions(account_id,external_id,date,description,amount_pence,category,kind,needs_review) VALUES(?,?,?,?,?,?,?,1)',
                               (key,row['external_id'],row['date'],row['description'],row['amount_pence'],row['category'],row['kind']))
                    inserted+=1
    return {'accounts_updated':len(staged),'imported':inserted,'changed':updated,'last_sync':stamp}


@router.post('/api/openbanking/sync')
def sync(dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config=load()
        try:
            staged,skipped,sessions=fetch_sync(config)
        except FeedError as exc:
            raise HTTPException(422,str(exc)) from None
        result=commit_sync(staged)
        for session in sessions:
            session['last_sync']=result['last_sync']
        config['last_sync_result']={**result,'skipped':skipped}
        vault.write(config)
        return config['last_sync_result']


@router.post('/api/openbanking/disconnect/{index}')
def disconnect(index: int,dataset: str='personal'):
    local_only(dataset)
    with vault.LOCK:
        config=load()
        if not 0<=index<len(config.get('sessions',[])):
            raise HTTPException(404,'Connection not found.')
        session=config['sessions'][index]
        if session.get('active',True):
            try:
                EnableBanking(config).request('DELETE','/sessions/'+session['session_id'])
            except FeedError as exc:
                raise HTTPException(422,str(exc)+' You can also revoke consent at your bank or Enable Banking.') from None
        session['active']=False
        vault.write(config)
        return {'disconnected':True,'history_retained':True}
