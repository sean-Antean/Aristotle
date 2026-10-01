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
        if dt.year != 2026 or dt.month != 8:
            continue
        
        net = t.get('netAmount', 0)
        for item in t.get('transferItems', []):
            inst = item.get('instrument', {})
            if inst.get('assetType') == 'OPTION':
                effect = item.get('positionEffect', '')
                symbol = inst.get('symbol', '')
                all_trades.append({
                    'account': account,
                    'date': dt.strftime('%Y-%m-%d'),
                    'symbol': symbol,
                    'effect': effect,
                    'net': net,
                    'price': item.get('price', 0),
                    'amount': item.get('amount', 0),
                    'cost': item.get('cost', 0)
                })
                break

by_symbol = defaultdict(list)
for t in all_trades:
    key = f"{t['account']} {t['symbol']}"
    by_symbol[key].append(t)

print('=== AUGUST 2026 REALIZED P&L ===\n')
total_realized = 0
for key, trades in sorted(by_symbol.items()):
    opens = [t for t in trades if t['effect'] == 'OPENING']
    closes = [t for t in trades if t['effect'] == 'CLOSING']
    
    if closes:
        open_credit = sum(t['net'] for t in opens)
        close_debit = sum(t['net'] for t in closes)
        realized = open_credit + close_debit
        total_realized += realized
        
        print(f'{key}:')
        for t in opens:
            print(f'  OPEN  {t["date"]} net=+${t["net"]:.2f}')
        for t in closes:
            print(f'  CLOSE {t["date"]} net=${t["net"]:.2f}')
        print(f'  REALIZED P&L: ${realized:.2f}\n')

print(f'=== TOTAL REALIZED P&L: ${total_realized:.2f} ===')

print('\n=== ALL PREMIUMS COLLECTED (OPENING) ===')
total_premiums = 0
for key, trades in sorted(by_symbol.items()):
    opens = [t for t in trades if t['effect'] == 'OPENING']
    if opens:
        credit = sum(t['net'] for t in opens)
        total_premiums += credit
        print(f'{key}: ${credit:.2f}')
print(f'Total premiums collected: ${total_premiums:.2f}')
