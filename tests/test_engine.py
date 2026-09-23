from datetime import date

from smartmoney.engine import forecast, occurrences

TODAY = date(2026,9,19)


def account(key, balance, buffer=10000, fund=False, kind='current', allowance=0):
    return {'id':key,'name':f'Account {key}','kind':kind,'balance_pence':balance,
            'buffer_pence':buffer,'can_fund':fund,'daily_allowance_pence':allowance,
            'balance_as_of':TODAY.isoformat()}


def payment(key, account_id, amount, due='2026-09-20', frequency='once', target=None):
    return {'id':key,'account_id':account_id,'amount_pence':amount,'next_due':due,
            'frequency':frequency,'name':'Payment','month_day':date.fromisoformat(due).day,
            'target_account_id':target}


def test_funding_shortfall_matches_buffer_and_preserves_source():
    result=forecast([account(1,284000,25000,True,allowance=1800),account(2,84000)],
                    [payment(1,2,-101500)],TODAY,30)
    r=result['recommendations'][0]
    assert r['needed_pence']==27500
    assert r['sources']==[{'account_id':1,'name':'Account 1','amount_pence':27500}]
    assert result['minima'][1]==230000  # exactly thirty daily allowances
    assert result['minima'][2]==-17500  # recommendation never applied


def test_source_capacity_cannot_be_allocated_twice():
    result=forecast([account(1,20000,10000,True),account(2,0),account(3,0)],[],TODAY,2)
    assert sum(s['amount_pence'] for r in result['recommendations'] for s in r['sources'])==10000
    assert sum(r['unfunded_pence'] for r in result['recommendations'])==10000


def test_same_day_income_does_not_hide_intraday_overdraft():
    result=forecast([account(1,0,0)],[payment(1,1,50000),payment(2,1,-30000)],TODAY,2)
    assert result['minima'][1]==-30000
    assert result['points'][-1]['balances'][1]==20000


def test_savings_and_stale_accounts_never_fund_suggestions():
    stale=account(1,100000,0,True)
    stale['balance_as_of']='2026-09-18'
    result=forecast([stale,account(2,100000,0,True,'savings'),account(3,0)],[],TODAY,1)
    assert result['recommendations'][0]['sources']==[]
    assert result['stale']


def test_stale_target_suppresses_transfer_amount_allocation():
    target=account(2,0)
    target['balance_as_of']='2026-09-18'
    result=forecast([account(1,100000,0,True),target],[],TODAY,1)
    assert result['recommendations'][0]['sources']==[]


def test_monthly_schedule_retains_day_after_short_month():
    s=payment(1,1,-100,'2027-01-31','monthly')
    assert list(occurrences(s,date(2027,1,1),date(2027,4,30)))==[
        date(2027,1,31),date(2027,2,28),date(2027,3,31),date(2027,4,30)]


def test_planned_internal_transfer_conserves_balance():
    result=forecast([account(1,50000,0),account(2,10000,0)],
                    [payment(1,1,-12000,target=2)],TODAY,2)
    assert result['points'][-1]['balances']=={1:38000,2:22000}
    assert sum(result['points'][-1]['balances'].values())==60000


def test_future_salary_does_not_create_current_headroom():
    result=forecast([account(1,0,0)],[payment(1,1,300000)],TODAY,10)
    assert result['headroom_pence']==0


def test_daily_spending_precedes_same_day_salary():
    result=forecast([account(1,0,0,allowance=1000)],
                    [payment(1,1,300000,due=TODAY.isoformat())],TODAY,1)
    assert result['minima'][1]==-1000


def test_transfer_credit_does_not_conceal_same_day_bill():
    result=forecast([account(1,200000,0),account(2,0,0)],
                    [payment(1,1,-100000,target=2),payment(2,2,-80000)],TODAY,2)
    assert result['minima'][2]==-80000
    assert result['points'][-1]['balances'][2]==20000
