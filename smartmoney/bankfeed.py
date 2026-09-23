"""Enable Banking AIS client. No payment endpoints or bank credentials."""
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from . import config

BASE = 'https://api.enablebanking.com'
CALLBACK = config.LOCAL_ORIGIN + '/openbanking-callback'  # Default for local/SSH-tunnel use.


class FeedError(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def make_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SmartMoney local')])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(utcnow() - timedelta(minutes=1))
            .not_valid_after(utcnow() + timedelta(days=365)).sign(key, hashes.SHA256()))
    return {'private_key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()).decode(),
            'certificate': cert.public_bytes(serialization.Encoding.PEM).decode()}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class EnableBanking:
    def __init__(self, config):
        self.config = config

    def request(self, method, path, **kwargs):
        allowed = ((method == 'GET' and (path in ('/application', '/aspsps') or
                    re.fullmatch(r'/accounts/[a-zA-Z0-9-]+/(balances|transactions)', path))) or
                   (method == 'POST' and path in ('/auth', '/sessions')) or
                   (method == 'DELETE' and re.fullmatch(r'/sessions/[a-zA-Z0-9-]+', path)))
        if not allowed:
            raise FeedError('This connector only permits account-information operations.')
        if not self.config.get('app_id') or not self.config.get('private_key'):
            raise FeedError('Set up your Enable Banking application first.')
        now = int(time.time())
        token = jwt.encode({'iss':'enablebanking.com','aud':'api.enablebanking.com','iat':now,'exp':now+300},
                           self.config['private_key'], algorithm='RS256', headers={'kid':self.config['app_id']})
        try:
            with httpx.Client(timeout=45, follow_redirects=False) as client:
                response = client.request(method, BASE+path, headers={'Authorization':'Bearer '+token,
                                           'Accept':'application/json'}, **kwargs)
        except httpx.HTTPError:
            raise FeedError('Enable Banking could not be reached. Check your connection and try again.') from None
        if response.status_code >= 300:
            code = ''
            try:
                raw = response.json().get('error', '')
                if isinstance(raw, str) and re.fullmatch('[A-Z_]{1,80}', raw):
                    code = ' ('+raw+')'
            except (ValueError, AttributeError):
                pass
            raise FeedError(f'Enable Banking returned HTTP {response.status_code}{code}. Check application activation and bank consent in the provider control panel.')
        if response.status_code == 204:
            return {}
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            raise FeedError('The provider returned an unexpected response. Nothing has been imported.') from None

    def application(self):
        app = self.request('GET','/application')
        if app.get('environment') != 'PRODUCTION':
            raise FeedError('This setup is for real accounts. Register a PRODUCTION application, not a sandbox application.')
        if 'AIS' not in app.get('services', []):
            raise FeedError('Enable Account Information (AIS) for this application in the control panel.')
        if config.settings.callback_url not in app.get('redirect_urls', []):
            raise FeedError('Register the exact callback URL shown in SmartMoney with Enable Banking.')
        return app

    def banks(self):
        result = self.request('GET','/aspsps', params={'country':'GB','service':'AIS','psu_type':'personal'})
        return [b for b in result.get('aspsps', []) if b.get('country') == 'GB' and 'personal' in b.get('psu_types', [])]

    def transactions(self, uid):
        rows, seen = [], set()
        params = {'date_from':(date.today()-timedelta(days=90)).isoformat(), 'date_to':date.today().isoformat(),
                  'transaction_status':'BOOK'}
        for _ in range(100):
            result = self.request('GET',f'/accounts/{quote(uid, safe="")}/transactions',params=params)
            rows.extend(result.get('transactions', []))
            if len(rows) > 100000:
                raise FeedError('Transaction history exceeded the sync limit. Nothing has been imported.')
            continuation = result.get('continuation_key')
            if not continuation:
                return rows
            if continuation in seen:
                raise FeedError('Provider repeated a transaction page. Nothing has been imported.')
            seen.add(continuation)
            params = {**params, 'continuation_key':continuation}
        raise FeedError('Too many transaction pages. Nothing has been imported.')


def amount_pence(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount)>1_000_000_000 or amount != amount.quantize(Decimal('.01')):
            raise ValueError()
        return int(amount*100)
    except (InvalidOperation, ValueError, TypeError):
        raise FeedError('The bank returned an unsupported monetary amount. Nothing has been imported.') from None


def balances(result):
    rows = [b for b in result.get('balances', []) if b.get('balance_amount', {}).get('currency') == 'GBP']
    def newest(types):
        eligible = [b for b in rows if b.get('balance_type') in types]
        # Prefer intraday to closing when dates tie; never use future-dated balances.
        eligible = [b for b in eligible if b.get('reference_date', date.today().isoformat()) <= date.today().isoformat()]
        return max(eligible, key=lambda b:(b.get('reference_date',''), b['balance_type'].startswith('IT')),default=None)
    booked, available = newest(('ITBD','CLBD')), newest(('ITAV','CLAV'))
    if booked is None:
        raise FeedError('The bank did not provide a GBP booked balance. An available balance alone may include an overdraft limit, so it was not imported.')
    value = amount_pence(booked['balance_amount']['amount'])
    planning = value
    as_of = booked.get('reference_date') or date.today().isoformat()
    date.fromisoformat(as_of)
    if available:
        planning = min(value, amount_pence(available['balance_amount']['amount']))
        # Do not mark an older available snapshot as current.
        as_of = min(as_of, available.get('reference_date') or as_of)
    return value, planning, as_of, booked['balance_type']


def normalise_transaction(row):
    if row.get('status') != 'BOOK':
        return None, 'pending'
    if row.get('transaction_amount',{}).get('currency') != 'GBP':
        return None, 'currency'
    reference = row.get('entry_reference')
    if not reference:
        return None, 'missing_id'
    indicator = row.get('credit_debit_indicator')
    if indicator not in ('DBIT','CRDT'):
        raise FeedError('The bank did not specify a transaction direction. Nothing has been imported.')
    amount = abs(amount_pence(row['transaction_amount']['amount'])) * (-1 if indicator=='DBIT' else 1)
    booked = row.get('booking_date')
    try:
        booked = date.fromisoformat(booked).isoformat()
    except (ValueError, TypeError):
        raise FeedError('The bank returned a transaction without a valid booking date.') from None
    if booked > date.today().isoformat():
        return None, 'future'
    name = (row.get('creditor') if amount < 0 else row.get('debtor')) or {}
    references = row.get('remittance_information') or []
    description = ' · '.join(filter(None, [name.get('name'), *references])) or row.get('note') or 'Bank transaction'
    return {'external_id':'eb:'+digest(str(reference)), 'date':booked, 'description':description[:300],
            'amount_pence':amount, 'category':'Needs review', 'kind':'expense' if amount<0 else 'income'}, None


def minimal_session(result):
    """Discard names of holders, addresses, full account numbers and other unused data."""
    session_id = result.get('session_id','')
    if not re.fullmatch(r'[a-zA-Z0-9-]{1,100}', session_id):
        raise FeedError('The provider returned an invalid session identifier.')
    accounts = []
    for a in result.get('accounts', []):
        uid, identity = a.get('uid',''), a.get('identification_hash')
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,100}', uid):
            raise FeedError('The provider returned an invalid account identifier.')
        accounts.append({'uid':uid, 'identity':digest(identity) if identity else None,
                         'currency':a.get('currency'), 'type':a.get('cash_account_type'),
                         'label':(a.get('product') or a.get('details') or 'Bank account')[:80]})
    if len(accounts)>30:
        raise FeedError('This personal connector supports up to 30 accounts per consent.')
    return {'session_id':session_id,'accounts':accounts,'bank':result.get('aspsp',{}).get('name','Bank'),
            'valid_until':result.get('access',{}).get('valid_until'), 'last_sync':None,'active':True}
