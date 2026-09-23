"""Deterministic cash planning. All calculations use integer pence."""
from calendar import monthrange
from datetime import date, timedelta


def next_month(day, anchor):
    year, month = day.year + (day.month == 12), day.month % 12 + 1
    return date(year, month, min(anchor, monthrange(year, month)[1]))


def occurrences(schedule, today, end):
    due = date.fromisoformat(schedule['next_due'])
    anchor = schedule.get('month_day') or due.day
    while due < today and schedule['frequency'] == 'monthly':
        due = next_month(due, anchor)
    while today <= due <= end:
        yield due
        if schedule['frequency'] != 'monthly':
            break
        due = next_month(due, anchor)


def forecast(accounts, schedules, today, days):
    end = today + timedelta(days=days - 1)
    events = []
    for schedule in schedules:
        for due in occurrences(schedule, today, end):
            events.append({**schedule, 'date': due.isoformat()})
    # Expenses precede income on the same day: no assumption about bank posting order.
    events.sort(key=lambda e: (e['date'], e['amount_pence'], e['id']))
    balances = {a['id']: a.get('forecast_balance_pence', a['balance_pence']) for a in accounts}
    minima = balances.copy()
    breach = {a['id']: today.isoformat() for a in accounts if balances[a['id']] < a['buffer_pence']}
    buffers = {a['id']: a['buffer_pence'] for a in accounts}
    points = [{'date': today.isoformat(), 'balances': balances.copy(), 'label': 'Starting snapshot'}]
    for offset in range(days):
        day = today + timedelta(days=offset)
        effects = [(a['id'], -a['daily_allowance_pence']) for a in accounts]
        for e in (e for e in events if e['date'] == day.isoformat()):
            effects.append((e['account_id'], e['amount_pence']))
            if e.get('target_account_id'):
                effects.append((e['target_account_id'], -e['amount_pence']))
        # Split transfer legs so incoming transfers cannot hide earlier bills.
        # Include the daily spending allowance among outgoings before any income.
        for key, amount in sorted(effects, key=lambda effect: effect[1]):
            balances[key] += amount
            minima[key] = min(minima[key], balances[key])
            if balances[key] < buffers[key]:
                breach.setdefault(key, day.isoformat())
        points.append({'date': day.isoformat(), 'balances': balances.copy(), 'label': 'End of day'})
    available = {a['id']: max(0, minima[a['id']] - a['buffer_pence']) for a in accounts
                 if a['kind'] == 'current' and a['can_fund'] and a['balance_as_of'] == today.isoformat()}
    recommendations = []
    for a in sorted(accounts, key=lambda a: breach.get(a['id'], '9999')):
        if a['kind'] != 'current' or a['id'] not in breach:
            continue
        gap = a['buffer_pence'] - minima[a['id']]
        allocations = []
        if a['balance_as_of'] == today.isoformat():
            for source in accounts:
                capacity = available.get(source['id'], 0) if source['id'] != a['id'] else 0
                amount = min(capacity, gap - sum(x['amount_pence'] for x in allocations))
                if amount > 0:
                    allocations.append({'account_id': source['id'], 'name': source['name'], 'amount_pence': amount})
                    available[source['id']] -= amount
        funded = sum(x['amount_pence'] for x in allocations)
        due = max(today, date.fromisoformat(breach[a['id']]) - timedelta(days=1))
        recommendations.append({'account_id': a['id'], 'name': a['name'], 'needed_pence': gap,
            'minimum_pence': minima[a['id']], 'buffer_pence': a['buffer_pence'],
            'breach_date': breach[a['id']], 'by_date': due.isoformat(), 'sources': allocations,
            'unfunded_pence': gap-funded, 'stale': a['balance_as_of'] != today.isoformat()})
    current = [a for a in accounts if a['kind'] == 'current']
    # Conservative sum of individual minima, including deficits in underfunded accounts.
    headroom = max(0, sum(minima[a['id']] - a['buffer_pence'] for a in current))
    return {'points': points, 'events': events, 'minima': minima, 'recommendations': recommendations,
            'headroom_pence': headroom, 'end': end.isoformat(),
            'stale': any(a['balance_as_of'] != today.isoformat() for a in accounts)}
