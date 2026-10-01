import json, sys
from datetime import datetime
from collections import defaultdict

raw = sys.stdin.read()
parts = raw.split('=== Transactions')

all_trades = []
for part in parts[1:]:
    lines = part.split('\n')
    account = lines[0].split('(')[0].strip()
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith('['):
            json_start = i
            break
    if json_start is None:
        continue
    json_str = '\n'.join(lines[json_start:])
    try:
        trades = json.loads(json_str)
    except:
        continue
    
    for t in trades:
        if t.get('type') != 'TRADE':
            continue
        dt = datetime.fromisoformat(t['time'].replace('+0000', ''))
        if dt.year != 2026:
            continue
        
        net = t.get('netAmount', 0)
        for item in t.get('transferItems', []):
            inst = item.get('instrument', {})
            if inst.get('assetType') == 'OPTION':
                effect = item.get('positionEffect', '')
                symbol = inst.get('symbol', '')
                all_trades.append({
                    'account': account,
                    'date': dt,
                    'symbol': symbol,
                    'effect': effect,
                    'net': net,
                    'price': item.get('price', 0),
                    'amount': item.get('amount', 0),
                    'cost': item.get('cost', 0)
                })
                break

# Pair opens and closes
by_symbol = defaultdict(list)
for t in all_trades:
    key = f"{t['account']} {t['symbol']}"
    by_symbol[key].append(t)

# Calculate stats
wins = 0
losses = 0
total_realized = 0
win_amounts = []
loss_amounts = []
hold_days = []
premiums = []

for key, trades in by_symbol.items():
    opens = [t for t in trades if t['effect'] == 'OPENING']
    closes = [t for t in trades if t['effect'] == 'CLOSING']
    
    if closes:
        open_credit = sum(t['net'] for t in opens)
        close_debit = sum(t['net'] for t in closes)
        realized = open_credit + close_debit
        total_realized += realized
        
        if realized > 0:
            wins += 1
            win_amounts.append(realized)
        else:
            losses += 1
            loss_amounts.append(realized)
        
        if opens and closes:
            first_open = min(t['date'] for t in opens)
            last_close = max(t['date'] for t in closes)
            hold = (last_close - first_open).days
            hold_days.append(hold)
    
    for t in opens:
        premiums.append(t['net'])

print('=== ARISTOTLE PERFORMANCE ANALYSIS ===\n')
print(f'Total Trades (closed): {wins + losses}')
print(f'Wins: {wins}')
print(f'Losses: {losses}')
print(f'Win Rate: {wins/(wins+losses)*100:.1f}%')
print(f'\nAvg Win: ${sum(win_amounts)/len(win_amounts):.2f}' if win_amounts else 'No wins')
print(f'Avg Loss: ${sum(loss_amounts)/len(loss_amounts):.2f}' if loss_amounts else 'No losses')
print(f'Largest Win: ${max(win_amounts):.2f}' if win_amounts else 'N/A')
print(f'Largest Loss: ${min(loss_amounts):.2f}' if loss_amounts else 'N/A')
print(f'\nAvg Hold Time: {sum(hold_days)/len(hold_days):.1f} days' if hold_days else 'N/A')
print(f'Total Realized P&L: ${total_realized:.2f}')
print(f'Avg Premium per Trade: ${sum(premiums)/len(premiums):.2f}' if premiums else 'N/A')
print(f'Total Premiums Collected: ${sum(premiums):.2f}')
