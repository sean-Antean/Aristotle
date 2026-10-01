"""
Aristotle Schwab Integration
Simple interface for Aristotle to fetch market data

Usage (from Aristotle):
    from aristotle_schwab import get_watchlist_data, analyze_opportunities
    
    # Get quotes for all watchlist tickers
    data = get_watchlist_data()
    
    # Analyze specific ticker for CSP opportunity
    analysis = analyze_opportunities('TSLL')
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

CONFIG_DIR = Path(__file__).parent
WATCHLIST = ['TSLL', 'NVDL', 'TQQQ', 'SOXL', 'AMZN']


def run_bridge_command(*args):
    """Run schwab_bridge.py with arguments"""
    bridge_script = CONFIG_DIR / "schwab_bridge.py"
    
    cmd = ['python', str(bridge_script)] + list(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        return f"Error running command: {e}"


def get_watchlist_data():
    """
    Fetch real-time data for all watchlist tickers
    Returns formatted string for Aristotle to parse
    """
    symbols = ','.join(WATCHLIST)
    output = run_bridge_command('--quotes', symbols)
    
    # Parse and format for Aristotle
    lines = output.split('\n')
    formatted = []
    
    current_symbol = None
    for line in lines:
        if line.strip().endswith(':'):
            current_symbol = line.strip().rstrip(':')
        elif 'Price:' in line and current_symbol:
            price = line.split('$')[1].strip() if '$' in line else 'N/A'
            formatted.append(f"{current_symbol}: ${price}")
        elif 'Change:' in line and current_symbol:
            change = line.split(':')[1].strip()
            formatted.append(f"  Change: {change}")
    
    return '\n'.join(formatted)


def analyze_opportunities(symbol):
    """
    Analyze a specific ticker for CSP opportunities
    Returns structured data for Aristotle
    """
    output = run_bridge_command('--analyze', symbol)
    
    # The bridge saves analysis to JSON file
    # Find the most recent analysis file
    analysis_dir = CONFIG_DIR / "analysis"
    
    if not analysis_dir.exists():
        return f"No analysis data available for {symbol}"
    
    # Get most recent file for this symbol
    files = sorted(
        analysis_dir.glob(f"{symbol}_*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not files:
        return f"No analysis file found for {symbol}"
    
    with open(files[0]) as f:
        data = json.load(f)
    
    # Format for Aristotle
    quote = data.get('quote', {})
    opportunities = data.get('opportunities', [])
    
    result = []
    result.append(f"📊 Analysis: {symbol}")
    result.append(f"Current Price: ${quote.get('price', 'N/A')}")
    result.append(f"Change: {quote.get('change_percent', 'N/A')}%")
    result.append("")
    
    if opportunities:
        result.append("Top CSP Opportunities:")
        for i, opp in enumerate(opportunities[:3], 1):
            result.append(f"\n{i}. Strike: ${opp['strike']:.2f}")
            result.append(f"   Premium: ${opp['premium']:.2f}")
            result.append(f"   Return: {opp['return_pct']:.2f}%")
            result.append(f"   Distance OTM: {opp['distance_pct']:.2f}%")
            result.append(f"   Breakeven: ${opp['breakeven']:.2f}")
            result.append(f"   Collateral: ${opp['collateral']:,.2f}")
            result.append(f"   Expiration: {opp['expiration']} ({opp['days_to_expiry']} DTE)")
            result.append(f"   IV: {opp['iv']:.1f}%" if opp.get('iv') else "   IV: N/A")
    else:
        result.append("No suitable CSP opportunities found.")
    
    return '\n'.join(result)


def get_down_day_candidates(threshold=-3.0):
    """
    Identify tickers down more than threshold%
    Returns list of candidates for Aristotle
    """
    symbols = ','.join(WATCHLIST)
    output = run_bridge_command('--quotes', symbols)
    
    candidates = []
    lines = output.split('\n')
    
    current_symbol = None
    current_change = None
    
    for line in lines:
        if line.strip().endswith(':'):
            current_symbol = line.strip().rstrip(':')
        elif 'Change:' in line and current_symbol:
            # Parse change percentage
            try:
                change_str = line.split('(')[1].rstrip('%)')
                change = float(change_str)
                
                if change <= threshold:
                    candidates.append({
                        'symbol': current_symbol,
                        'change': change
                    })
            except:
                pass
    
    # Sort by most negative (biggest down day)
    candidates.sort(key=lambda x: x['change'])
    
    return candidates


if __name__ == '__main__':
    # Test functions
    print("Testing Aristotle Schwab Integration...")
    print("\n1. Watchlist Data:")
    print(get_watchlist_data())
    
    print("\n2. Down Day Candidates (threshold -3%):")
    candidates = get_down_day_candidates()
    for c in candidates:
        print(f"   {c['symbol']}: {c['change']:.2f}%")
    
    print("\n3. Sample Analysis (TSLL):")
    print(analyze_opportunities('TSLL'))
