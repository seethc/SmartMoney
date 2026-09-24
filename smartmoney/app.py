import csv
import io
import re
import base64
import binascii
import hmac
from urllib.parse import urlsplit
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import store, config
from .engine import forecast
from . import screenshots

ROOT = Path(__file__).resolve().parent.parent
Dataset = Literal['demo', 'personal']
Kind = Literal['expense', 'income', 'transfer', 'adjustment']


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield


app = FastAPI(title='SmartMoney local API', lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    settings = config.settings
    host = request.headers.get('host', '').lower()
    allowed = {'127.0.0.1', '127.0.0.1:8765', 'localhost', 'localhost:8765', 'testserver',
               urlsplit(settings.public_url).netloc.lower()}
    if host not in allowed:
        return JSONResponse({'detail': 'Invalid host.'}, status_code=400)
    # A proxy must terminate TLS and forward the scheme. run.py trusts loopback only.
    if settings.remote and host == urlsplit(settings.public_url).netloc.lower() and request.url.scheme != 'https':
        return JSONResponse({'detail': 'Use the configured HTTPS address.'}, status_code=400)
    if settings.password is not None:
        authorized = False
        try:
            scheme, token = request.headers.get('authorization', '').split(' ', 1)
            raw = base64.b64decode(token, validate=True) if scheme.lower() == 'basic' else b''
            username, password = raw.split(b':', 1)
            authorized = hmac.compare_digest(username, b'smartmoney') & hmac.compare_digest(password, settings.password)
        except (ValueError, binascii.Error):
            pass
        if not authorized:
            return JSONResponse({'detail': 'Sign in with your SmartMoney app password.'}, status_code=401,
                                headers={'WWW-Authenticate':'Basic realm="SmartMoney", charset="UTF-8"', 'Cache-Control':'no-store'})
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if request.headers.get('x-smartmoney') != 'local' or (origin and origin != str(request.base_url).rstrip('/')):
            return JSONResponse({'detail': 'Only same-origin app requests are accepted.'}, status_code=403)
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': 'Invalid content length.'}, status_code=400)
        limit = screenshots.MAX_BYTES if request.url.path == '/api/screenshots/preview' else 2_000_000
        if length > limit:
            return JSONResponse({'detail': f'Upload is limited to {limit // 1_000_000} MB.'}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse({'detail': f'Upload is limited to {limit // 1_000_000} MB.'}, status_code=413)
            body.extend(chunk)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api') else 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.get('/api/runtime')
def runtime():
    return {'public_url':config.settings.public_url,
            'remote':config.settings.remote}


def pence(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) > 1_000_000_000 or number != number.quantize(Decimal('.01')):
            raise ValueError()
        return int(number * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, 'Use a valid amount with at most two decimal places.')


def existing(db, table, key):
    assert table in ('accounts','transactions','schedules')
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (key,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Record not found in this workspace.')
    return dict(row)


class Account(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    institution: str = Field(min_length=1, max_length=80)
    kind: Literal['current','savings','credit','investment'] = 'current'
    role: str = Field(default='', max_length=100)
    balance: str
    buffer: str = '0'
    daily_allowance: str = '0'
    balance_as_of: date
    can_fund: bool = False


class Schedule(BaseModel):
    account_id: int
    name: str = Field(min_length=1,max_length=100)
    amount: str
    next_due: date
    frequency: Literal['once','monthly'] = 'monthly'
    kind: Literal['expense','income','transfer'] = 'expense'
    target_account_id: int | None = None


class Import(BaseModel):
    account_id: int
    csv_text: str = Field(max_length=1_500_000)


class Classification(BaseModel):
    category: str = Field(min_length=1, max_length=60)
    kind: Kind


@app.get('/api/dashboard')
def dashboard(dataset: Dataset = 'demo', month: str | None = None, days: int = 30):
    if not 1 <= days <= 90:
        raise HTTPException(422, 'Choose a forecast from 1 to 90 days.')
    month = month or date.today().strftime('%Y-%m')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise HTTPException(422, 'Use YYYY-MM for the month.')
    with store.connection(dataset) as db:
        accounts, transactions, schedules = (store.records(db,t) for t in ('accounts','transactions','schedules'))
    selected = [t for t in transactions if t['date'].startswith(month)]
    categories = defaultdict(int)
    for t in selected:
        if t['kind'] == 'expense' and not t['needs_review']:
            categories[t['category']] -= t['amount_pence']
    income = sum(t['amount_pence'] for t in selected if t['kind'] == 'income' and not t['needs_review'])
    spending = sum(categories.values())
    months = sorted({t['date'][:7] for t in transactions} | {month}, reverse=True)
    history = []
    for m in sorted(months) [-6:]:
        rows = [t for t in transactions if t['date'].startswith(m) and not t['needs_review']]
        history.append({'month': m, 'income': sum(t['amount_pence'] for t in rows if t['kind']=='income'),
                        'spending': -sum(t['amount_pence'] for t in rows if t['kind']=='expense')})
    return {'dataset':dataset, 'today':date.today().isoformat(), 'month':month, 'months':months,
        'accounts':accounts, 'transactions':sorted(selected,key=lambda t:(t['date'],t['id']),reverse=True),
        'unreviewed_count':sum(bool(t['needs_review']) for t in transactions),
        'unreviewed_months':sorted({t['date'][:7] for t in transactions if t['needs_review']},reverse=True),
        'schedules':schedules, 'categories':dict(sorted(categories.items(),key=lambda x:-x[1])),
        'income_pence':income, 'spending_pence':spending, 'net_cashflow_pence':income-spending,
        'net_worth_pence':sum(a['balance_pence'] for a in accounts),
        'cash_pence':sum(a['balance_pence'] for a in accounts if a['kind'] in ('current','savings')),
        'history':history, 'forecast':forecast(accounts,schedules,date.today(),days)}


def account_values(item):
    balance, buffer, allowance = pence(item.balance), pence(item.buffer), pence(item.daily_allowance)
    if not item.name.strip() or not item.institution.strip():
        raise HTTPException(422, 'Account and institution names cannot be blank.')
    if buffer < 0 or allowance < 0 or item.balance_as_of > date.today():
        raise HTTPException(422, 'Buffers and allowances must be nonnegative; balance dates cannot be in the future.')
    if item.can_fund and item.kind != 'current':
        raise HTTPException(422, 'Only current accounts can fund suggestions.')
    if item.kind == 'credit' and balance > 0:
        raise HTTPException(422, 'Enter credit-card debt as a negative balance (or zero).')
    return (item.name.strip(),item.institution.strip(),item.kind,item.role,balance,buffer,allowance,item.balance_as_of.isoformat(),int(item.can_fund))


@app.post('/api/accounts')
def add_account(item: Account, dataset: Dataset = 'personal'):
    values = account_values(item)
    with store.connection(dataset) as db:
        cursor = db.execute('INSERT INTO accounts VALUES(NULL,?,?,?,?,?,?,?,?,?)',values)
        return {'id':cursor.lastrowid}


@app.put('/api/accounts/{key}')
def update_account(key: int, item: Account, dataset: Dataset = 'personal'):
    values = account_values(item)
    with store.connection(dataset) as db:
        existing(db,'accounts',key)
        db.execute('UPDATE accounts SET name=?,institution=?,kind=?,role=?,balance_pence=?,buffer_pence=?,daily_allowance_pence=?,balance_as_of=?,can_fund=? WHERE id=?',(*values,key))
    return {'saved':True}


@app.post('/api/schedules')
def add_schedule(item: Schedule, dataset: Dataset = 'personal'):
    amount = pence(item.amount)
    if amount == 0 or (item.kind in ('expense','transfer') and amount > 0) or (item.kind == 'income' and amount < 0):
        raise HTTPException(422,'Use a negative amount for bills/transfers and a positive amount for income.')
    if item.next_due < date.today():
        raise HTTPException(422,'Next due must be today or later.')
    if (item.kind == 'transfer') != bool(item.target_account_id) or item.target_account_id == item.account_id:
        raise HTTPException(422,'A transfer needs a different destination account; other entries must have none.')
    with store.connection(dataset) as db:
        existing(db,'accounts',item.account_id)
        if item.target_account_id:
            existing(db,'accounts',item.target_account_id)
        cur = db.execute('INSERT INTO schedules VALUES(NULL,?,?,?,?,?,?,?,?)',
            (item.account_id,item.name,amount,item.next_due.isoformat(),item.frequency,item.next_due.day,item.kind,item.target_account_id))
        return {'id':cur.lastrowid}


@app.delete('/api/schedules/{key}')
def remove_schedule(key: int, dataset: Dataset = 'personal'):
    with store.connection(dataset) as db:
        existing(db,'schedules',key)
        db.execute('DELETE FROM schedules WHERE id=?',(key,))
    return {'saved':True}


def parse_import(db, item):
    existing(db,'accounts',item.account_id)
    reader = csv.DictReader(io.StringIO(item.csv_text.lstrip('\ufeff')))
    required = {'external_id','date','description','amount','category','kind'}
    if not reader.fieldnames or set(reader.fieldnames) != required:
        raise HTTPException(422,'CSV columns must be external_id,date,description,amount,category,kind.')
    rows, seen, duplicates = [], set(), 0
    for line, row in enumerate(reader, start=2):
        if line > 10001:
            raise HTTPException(422,'Import at most 10,000 rows at once.')
        try:
            if any(value is None for value in row.values()) or None in row:
                raise ValueError('wrong number of columns')
            row = {k:v.strip() for k,v in row.items()}
            if not row['external_id'] or row['external_id'] in seen or len(row['external_id']) > 160:
                raise ValueError('external_id must be unique and nonempty')
            seen.add(row['external_id'])
            d = date.fromisoformat(row['date'])
            if d > date.today():
                raise ValueError('future transactions belong in planned payments')
            if row['kind'] not in ('expense','income','transfer','adjustment'):
                raise ValueError('unknown kind')
            if not row['description'] or len(row['description']) > 300 or not row['category'] or len(row['category']) > 60:
                raise ValueError('description or category is missing or too long')
            record = {'account_id':item.account_id, 'external_id':row['external_id'], 'date':d.isoformat(),
                      'description':row['description'], 'amount_pence':pence(row['amount']), 'category':row['category'],'kind':row['kind']}
            old = db.execute('SELECT * FROM transactions WHERE account_id=? AND external_id=?',(item.account_id,row['external_id'])).fetchone()
            if old:
                if any(old[k] != record[k] for k in ('date','description','amount_pence')):
                    raise ValueError('external_id already exists with different transaction details')
                duplicates += 1
            else:
                rows.append(record)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422,f'Row {line}: {exc}')
    if not seen:
        raise HTTPException(422,'CSV contains no transactions.')
    return rows, duplicates


@app.post('/api/import/preview')
def preview(item: Import, dataset: Dataset = 'personal'):
    with store.connection(dataset) as db:
        rows, duplicates = parse_import(db,item)
    return {'rows':rows[:20], 'new_count':len(rows),'duplicates':duplicates}


@app.post('/api/import/commit')
def commit(item: Import, dataset: Dataset = 'personal'):
    with store.connection(dataset) as db:
        db.execute('BEGIN IMMEDIATE')
        rows, duplicates = parse_import(db,item)
        for r in rows:
            db.execute('INSERT INTO transactions(account_id,external_id,date,description,amount_pence,category,kind) VALUES(?,?,?,?,?,?,?)',tuple(r.values()))
    return {'imported':len(rows),'duplicates':duplicates}


@app.patch('/api/transactions/{key}')
def classify(key: int, item: Classification, dataset: Dataset = 'personal'):
    with store.connection(dataset) as db:
        existing(db,'transactions',key)
        db.execute('UPDATE transactions SET category=?,kind=?,needs_review=0 WHERE id=?',(item.category,item.kind,key))
    return {'saved':True}


@app.get('/')
def index():
    return FileResponse(ROOT / 'frontend' / 'index.html')


@app.get('/api/screenshots/status')
def screenshot_status():
    return {'ocr_available': bool(screenshots.executable()), 'max_bytes': screenshots.MAX_BYTES}


@app.post('/api/screenshots/preview')
async def screenshot_preview(request: Request):
    raw = await request.body()
    try:
        lines = await run_in_threadpool(screenshots.read_lines, raw)
        return screenshots.interpret(lines)
    except screenshots.ScreenshotError as exc:
        raise HTTPException(exc.status, str(exc)) from None


class SnapshotRow(BaseModel):
    account_id: int | None = None
    name: str = Field(default='', max_length=80)
    institution: str = Field(default='', max_length=80)
    kind: Literal['current', 'savings', 'credit', 'investment'] = 'current'
    balance: str = Field(max_length=30)
    balance_as_of: date
    expected_balance_pence: int | None = None
    expected_balance_as_of: date | None = None


class SnapshotImport(BaseModel):
    confirmed: Literal[True]
    rows: list[SnapshotRow] = Field(min_length=1, max_length=60)


@app.post('/api/screenshots/commit')
def commit_snapshots(item: SnapshotImport, dataset: Dataset = 'personal'):
    updated, created, unchanged, seen = 0, 0, 0, set()
    with store.connection(dataset) as db:
        db.execute('BEGIN IMMEDIATE')
        for row in item.rows:
            balance = pence(row.balance)
            if row.balance_as_of > date.today():
                raise HTTPException(422, 'Balance dates cannot be in the future.')
            previous = None
            if row.account_id is not None:
                if row.account_id in seen:
                    raise HTTPException(422, 'Each account can be updated only once per import. Remove overlapping screenshot rows.')
                previous = existing(db, 'accounts', row.account_id)
                seen.add(row.account_id)
                if (row.expected_balance_pence != previous['balance_pence'] or
                        row.expected_balance_as_of is None or row.expected_balance_as_of.isoformat() != previous['balance_as_of']):
                    raise HTTPException(409, 'An account changed since this page loaded. Reload the page and review the screenshot again.')
                if row.balance_as_of.isoformat() < previous['balance_as_of']:
                    raise HTTPException(409, 'An older screenshot cannot replace a newer account snapshot.')
                if previous['kind'] == 'credit' and balance > 0:
                    raise HTTPException(422, 'Enter credit-card debt as a negative balance.')
                if previous['balance_pence'] == balance and previous['balance_as_of'] == row.balance_as_of.isoformat():
                    unchanged += 1
                    continue
                db.execute('UPDATE accounts SET balance_pence=?,balance_as_of=? WHERE id=?',
                           (balance, row.balance_as_of.isoformat(), row.account_id))
                key = row.account_id
                updated += 1
            else:
                if not row.name.strip() or not row.institution.strip():
                    raise HTTPException(422, 'New accounts need an account name and institution.')
                values = account_values(Account(name=row.name, institution=row.institution, kind=row.kind,
                                                 balance=row.balance, balance_as_of=row.balance_as_of))
                if db.execute('SELECT 1 FROM accounts WHERE lower(name)=lower(?) AND lower(institution)=lower(?)', values[:2]).fetchone():
                    raise HTTPException(409, 'That account already exists. Select the existing account instead of creating another.')
                key = db.execute('INSERT INTO accounts VALUES(NULL,?,?,?,?,?,?,?,?,?)', values).lastrowid
                created += 1
            db.execute('INSERT INTO snapshot_audit(account_id,previous_balance_pence,previous_as_of,balance_pence,balance_as_of) VALUES(?,?,?,?,?)',
                       (key, previous['balance_pence'] if previous else None, previous['balance_as_of'] if previous else None,
                        balance, row.balance_as_of.isoformat()))
    return {'updated': updated, 'created': created, 'unchanged': unchanged}


app.mount('/',StaticFiles(directory=ROOT / 'frontend'),name='frontend')
