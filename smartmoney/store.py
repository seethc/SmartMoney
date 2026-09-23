import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

DATA = Path(os.environ.get('SMARTMONEY_DATA_DIR', Path(__file__).resolve().parent.parent / 'data'))


@contextmanager
def connection(dataset):
    if dataset not in ('demo', 'personal'):
        raise ValueError('Unknown workspace')
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / f'{dataset}.sqlite3')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    for dataset in ('demo', 'personal'):
        with connection(dataset) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, institution TEXT NOT NULL,
                kind TEXT NOT NULL, role TEXT NOT NULL, balance_pence INTEGER NOT NULL,
                buffer_pence INTEGER NOT NULL, daily_allowance_pence INTEGER NOT NULL DEFAULT 0,
                balance_as_of TEXT NOT NULL, can_fund INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
                external_id TEXT NOT NULL, date TEXT NOT NULL, description TEXT NOT NULL,
                amount_pence INTEGER NOT NULL, category TEXT NOT NULL, kind TEXT NOT NULL,
                UNIQUE(account_id, external_id));
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id),
                name TEXT NOT NULL, amount_pence INTEGER NOT NULL, next_due TEXT NOT NULL,
                frequency TEXT NOT NULL, month_day INTEGER NOT NULL, kind TEXT NOT NULL,
                target_account_id INTEGER REFERENCES accounts(id));
            CREATE TABLE IF NOT EXISTS bank_links (
                account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
                identity_hash TEXT NOT NULL UNIQUE, bank TEXT NOT NULL,
                planning_balance_pence INTEGER, balance_type TEXT NOT NULL,
                last_sync TEXT NOT NULL);
            ''')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(transactions)')}
            if 'needs_review' not in columns:
                db.execute('ALTER TABLE transactions ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0')
            if dataset == 'demo' and db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0:
                seed(db)


def seed(db):
    today = date.today()
    accounts = [
        ('Barclays', 'Barclays', 'current', 'Salary & everyday', 284000, 25000, 1800, 1),
        ('Santander', 'Santander', 'current', 'Rent & bills', 84000, 10000, 0, 0),
        ('Revolut', 'Revolut', 'current', 'International spending', 14000, 0, 0, 0),
        ('Chase', 'Chase', 'current', 'Travel & everyday', 31000, 0, 0, 0),
        ('Ulster savings', 'Ulster Bank', 'savings', 'Emergency fund', 840000, 0, 0, 0),
    ]
    for name, bank, kind, role, balance, buffer, allowance, fund in accounts:
        db.execute('INSERT INTO accounts VALUES(NULL,?,?,?,?,?,?,?,?,?)',
                   (name, bank, kind, role, balance, buffer, allowance, today.isoformat(), fund))
    for account, name, amount, offset, frequency, kind in [
        (2,'Rent',-80000,8,'monthly','expense'), (2,'Energy',-9500,10,'monthly','expense'),
        (2,'Broadband',-2800,11,'monthly','expense'), (2,'Council tax',-14000,12,'monthly','expense'),
        (1,'Salary',320000,14,'monthly','income'), (1,'Mobile',-1800,6,'monthly','expense'),
        (1,'Gym',-2500,4,'monthly','expense')]:
        due = today + timedelta(days=offset)
        db.execute('INSERT INTO schedules VALUES(NULL,?,?,?,?,?,?,?,NULL)',
                   (account,name,amount,due.isoformat(),frequency,due.day,kind))
    rows = [(1,'Salary',320000,'Income','income'),(2,'Rent',-80000,'Housing','expense'),
            (2,'Council tax',-14000,'Bills','expense'),(1,'Tesco',-6420,'Groceries','expense'),
            (1,'Transport for London',-1870,'Transport','expense'),(1,'Dishoom',-4850,'Eating out','expense'),
            (1,'Sainsbury’s',-3860,'Groceries','expense'),(1,'Spotify',-1199,'Subscriptions','expense'),
            (3,'Weekend train',-3250,'Travel','expense'),(1,'Coffee & friends',-1450,'Eating out','expense'),
            (1,'Uniqlo',-6990,'Shopping','expense'),(1,'To Santander',-110000,'Transfers','transfer'),
            (2,'From Barclays',110000,'Transfers','transfer'),(1,'To Ulster savings',-50000,'Transfers','transfer'),
            (5,'From Barclays',50000,'Transfers','transfer')]
    for month_offset in range(3):
        anchor = today.replace(day=1)
        for _ in range(month_offset):
            anchor = (anchor-timedelta(days=1)).replace(day=1)
        for index, (account, desc, amount, category, kind) in enumerate(rows):
            day = anchor.replace(day=min(1+index, today.day if month_offset == 0 else 25))
            db.execute('INSERT INTO transactions(account_id,external_id,date,description,amount_pence,category,kind) VALUES(?,?,?,?,?,?,?)',
                       (account,f'demo-{month_offset}-{index}',day.isoformat(),desc,amount,category,kind))


def records(db, table):
    assert table in ('accounts','transactions','schedules')
    return [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
