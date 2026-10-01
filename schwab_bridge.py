"""
Schwab API Data Bridge for Aristotle Capital Flywheel
Fetches real-time quotes and option chains from Schwab API
Stores data locally for Aristotle analysis

Usage:
    python schwab_bridge.py --quotes TSLL,NVDL,TQQQ,SOXL,AMZN
    python schwab_bridge.py --chains TSLL --days 30
    python schwab_bridge.py --account
"""

import os
import json
import base64
import urllib.parse
import urllib.request
import ssl
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
CONFIG_DIR = Path(__file__).parent
TOKENS_FILE = CONFIG_DIR / "schwab_tokens.json"
CONFIG_FILE = CONFIG_DIR / "schwab_config.json"

# API Endpoints
BASE_URL = "https://api.schwabapi.com"
MARKET_DATA_URL = f"{BASE_URL}/marketdata/v1"
TRADER_API_URL = f"{BASE_URL}/trader/v1"


def get_ssl_context():
    """SSL context that works even behind antivirus/corporate TLS interception.

    Validates against the OS trust store via `truststore` when available
    (so an AV/proxy-injected root CA is trusted); falls back to the default
    CA bundle otherwise. Never disables verification.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def load_config():
    """Load Schwab API configuration"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def load_tokens():
    """Load OAuth tokens from secure storage"""
    if TOKENS_FILE.exists():
        with open(TOKENS_FILE) as f:
            return json.load(f)
    return {}


def save_tokens(tokens):
    """Save OAuth tokens securely"""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    # Set restrictive permissions
    os.chmod(TOKENS_FILE, 0o600)


def get_access_token():
    """Get valid access token, refresh if needed"""
    tokens = load_tokens()
    
    if not tokens:
        print("[ERROR] No tokens found. Run authentication first.")
        return None
    
    # Check if token is expired
    expires_at = datetime.fromisoformat(tokens.get('expires_at', '2000-01-01'))
    if datetime.now() >= expires_at:
        print("[REFRESH] Token expired, refreshing...")
        return refresh_access_token()
    
    return tokens.get('access_token')


def refresh_access_token():
    """Refresh OAuth access token"""
    config = load_config()
    tokens = load_tokens()
    
    refresh_token = tokens.get('refresh_token')
    if not refresh_token:
        print("[ERROR] No refresh token found.")
        return None
    
    # Build refresh request
    auth_string = base64.b64encode(
        f"{config['client_id']}:{config['client_secret']}".encode()
    ).decode()
    
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }).encode()
    
    req = urllib.request.Request(
        f"{BASE_URL}/v1/oauth/token",
        data=data,
        headers={
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, context=get_ssl_context()) as response:
            new_tokens = json.loads(response.read())
            new_tokens['expires_at'] = (datetime.now() + 
                timedelta(seconds=new_tokens.get('expires_in', 1800))).isoformat()
            save_tokens(new_tokens)
            print("[OK] Token refreshed successfully")
            return new_tokens['access_token']
    except Exception as e:
        print(f"[ERROR] Token refresh failed: {e}")
        return None


def api_request(endpoint, params=None):
    """Make authenticated API request"""
    token = get_access_token()
    if not token:
        return None
    
    url = f"{MARKET_DATA_URL}/{endpoint}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {token}'}
    )
    
    # Create SSL context (OS trust store aware; handles AV/proxy interception)
    ssl_context = get_ssl_context()
    
    try:
        with urllib.request.urlopen(req, context=ssl_context) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"[ERROR] API Error: {e.code} - {e.reason}")
        if e.code == 401:
            print("   Token may be expired. Try refreshing.")
        return None
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        return None


def get_price_history(symbol, period_type='year', period=1, frequency_type='weekly', frequency=1, start_date=None, end_date=None):
    """
    Fetch historical price data for EMA calculation
    
    Args:
        symbol: Stock symbol
        period_type: 'day', 'month', 'year', 'ytd'
        period: Number of periods
        frequency_type: 'minute', 'daily', 'weekly', 'monthly'
        frequency: Number of frequency types per candle
        start_date: Start date as milliseconds since epoch (optional)
        end_date: End date as milliseconds since epoch (optional)
    
    Returns:
        List of candles with open, high, low, close, volume
    """
    params = {
        'periodType': period_type,
        'period': period,
        'frequencyType': frequency_type,
        'frequency': frequency
    }
    if start_date is not None:
        params['startDate'] = start_date
    if end_date is not None:
        params['endDate'] = end_date
    
    data = api_request(f'pricehistory', {'symbol': symbol, **params})
    
    if not data or 'candles' not in data:
        print(f"[X] Could not fetch price history for {symbol}")
        return None
    
    candles = []
    for candle in data['candles']:
        candles.append({
            'datetime': datetime.fromtimestamp(candle['datetime'] / 1000).isoformat(),
            'open': candle.get('open'),
            'high': candle.get('high'),
            'low': candle.get('low'),
            'close': candle.get('close'),
            'volume': candle.get('volume')
        })
    
    return candles


def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    if not prices or len(prices) < period:
        return None
    
    # Standard EMA formula
    multiplier = 2 / (period + 1)
    ema = prices[0]  # Start with first price
    
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def calculate_ema_cloud_score(symbol):
    """
    Calculate Capital Flywheel EMA Cloud Score
    
    Fast cloud: EMA 5 > EMA 12
    Medium cloud: EMA 34 > EMA 50
    Slow cloud: EMA 72 > EMA 89
    
    Returns: {
        'cloud_score': 0-3,
        'fast_bullish': bool,
        'medium_bullish': bool,
        'slow_bullish': bool,
        'candles_used': int,
        'status': 'OK' or 'MANUAL_VERIFY'
    }
    """
    print(f"   Fetching weekly candles for {symbol}...")
    
    # Fetch 2 years of weekly data to ensure enough candles for EMA 89
    candles = get_price_history(symbol, period_type='year', period=2, 
                                frequency_type='weekly', frequency=1)
    
    if not candles or len(candles) < 100:
        print(f"   [WARNING] Insufficient weekly data for {symbol}")
        return {
            'cloud_score': 0,
            'fast_bullish': False,
            'medium_bullish': False,
            'slow_bullish': False,
            'candles_used': len(candles) if candles else 0,
            'status': 'MANUAL_VERIFY'
        }
    
    # Extract closing prices
    closes = [c['close'] for c in candles if c['close'] is not None]
    
    if len(closes) < 100:
        print(f"   [WARNING] Not enough valid closes for {symbol}")
        return {
            'cloud_score': 0,
            'fast_bullish': False,
            'medium_bullish': False,
            'slow_bullish': False,
            'candles_used': len(closes),
            'status': 'MANUAL_VERIFY'
        }
    
    # Calculate EMAs
    # For accurate EMA, we need enough historical data
    # Use available data but note if truncated
    
    ema_5 = calculate_ema(closes[-20:], 5) if len(closes) >= 20 else None
    ema_12 = calculate_ema(closes[-30:], 12) if len(closes) >= 30 else None
    ema_34 = calculate_ema(closes[-60:], 34) if len(closes) >= 60 else None
    ema_50 = calculate_ema(closes[-80:], 50) if len(closes) >= 80 else None
    ema_72 = calculate_ema(closes[-100:], 72) if len(closes) >= 100 else None
    ema_89 = calculate_ema(closes[-100:], 89) if len(closes) >= 100 else None
    
    # Determine cloud states
    fast_bullish = ema_5 > ema_12 if (ema_5 and ema_12) else False
    medium_bullish = ema_34 > ema_50 if (ema_34 and ema_50) else False
    slow_bullish = ema_72 > ema_89 if (ema_72 and ema_89) else False
    
    cloud_score = sum([fast_bullish, medium_bullish, slow_bullish])
    
    status = 'OK' if len(closes) >= 100 else 'MANUAL_VERIFY'
    
    print(f"   EMA Cloud: {cloud_score}/3 (Fast: {'Bull' if fast_bullish else 'Bear'}, "
          f"Medium: {'Bull' if medium_bullish else 'Bear'}, "
          f"Slow: {'Bull' if slow_bullish else 'Bear'})")
    
    return {
        'cloud_score': cloud_score,
        'fast_bullish': fast_bullish,
        'medium_bullish': medium_bullish,
        'slow_bullish': slow_bullish,
        'candles_used': len(closes),
        'status': status,
        'ema_values': {
            'ema_5': ema_5,
            'ema_12': ema_12,
            'ema_34': ema_34,
            'ema_50': ema_50,
            'ema_72': ema_72,
            'ema_89': ema_89
        }
    }


def get_earnings_date(symbol):
    """
    Fetch earnings date for symbol
    Note: Schwab API may not provide this directly
    Returns: earnings_date string or None
    """
    # Schwab's fundamental data endpoint
    data = api_request(f'instruments', {'symbol': symbol, 'projection': 'fundamental'})
    
    if data and symbol in data:
        fundamental = data[symbol].get('fundamental', {})
        # Try to find earnings date in various fields
        earnings_date = fundamental.get('epsChangePercent')  # Placeholder
        # Schwab may not provide exact earnings date in basic API
        return None  # Will need manual verification
    
    return None


def get_quotes(symbols):
    """Fetch real-time quotes for symbols"""
    if isinstance(symbols, list):
        symbols = ','.join(symbols)
    
    data = api_request('quotes', {'symbols': symbols})
    
    if not data:
        return None
    
    results = {}
    for symbol, quote in data.items():
        if 'quote' in quote:
            q = quote['quote']
            results[symbol] = {
                'symbol': symbol,
                'price': q.get('lastPrice'),
                'change': q.get('netChange'),
                'change_percent': q.get('netPercentChange'),
                'bid': q.get('bidPrice'),
                'ask': q.get('askPrice'),
                'volume': q.get('totalVolume'),
                'iv': q.get('volatility'),  # 52-week IV if available
                'timestamp': datetime.now().isoformat()
            }
    
    return results


def get_option_chains(symbol, days_to_expiration=30, strike_count=10):
    """Fetch option chain for symbol"""
    params = {
        'symbol': symbol,
        'contractType': 'PUT',
        'strikeCount': strike_count,
        'includeUnderlyingQuote': 'true',
        'strategy': 'SINGLE',
        'range': 'OTM'  # Out of the money puts
    }
    
    if days_to_expiration:
        params['daysToExpiration'] = days_to_expiration
    
    data = api_request('chains', params)
    
    if not data:
        return None
    
    # Parse option chain
    chain = {
        'symbol': symbol,
        'underlying_price': data.get('underlyingPrice'),
        'underlying_change': data.get('underlyingChange'),
        'expiration_dates': [],
        'strikes': []
    }
    
    if 'callExpDateMap' in data and 'putExpDateMap' in data:
        put_map = data['putExpDateMap']
        
        for exp_date, strikes in put_map.items():
            exp_info = {
                'date': exp_date.split(':')[0],
                'days_to_expiry': int(exp_date.split(':')[1]) if ':' in exp_date else None,
                'strikes': []
            }
            
            for strike, options in strikes.items():
                for opt in options:
                    exp_info['strikes'].append({
                        'strike': float(strike),
                        'bid': opt.get('bid'),
                        'ask': opt.get('ask'),
                        'last': opt.get('last'),
                        'mark': (opt.get('bid', 0) + opt.get('ask', 0)) / 2,
                        'iv': opt.get('volatility'),
                        'delta': opt.get('delta'),
                        'theta': opt.get('theta'),
                        'volume': opt.get('totalVolume'),
                        'open_interest': opt.get('openInterest'),
                        'days_to_expiry': opt.get('daysToExpiration')
                    })
            
            chain['expiration_dates'].append(exp_info)
    
    return chain


def analyze_csp_opportunity(symbol, target_return=0.05, max_dte=35):
    """Analyze Cash-Secured Put opportunity"""
    print(f"\n[ANALYZE] Analyzing {symbol}...")
    
    # Get quotes
    quotes = get_quotes([symbol])
    if not quotes or symbol not in quotes:
        print(f"[X] Could not fetch quote for {symbol}")
        return None
    
    quote = quotes[symbol]
    current_price = quote['price']
    
    if not current_price:
        print(f"[X] No price data for {symbol}")
        return None
    
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Change: {quote['change_percent']:.2f}%")
    
    # Get option chain
    chain = get_option_chains(symbol, days_to_expiration=max_dte, strike_count=15)
    if not chain:
        print(f"[X] Could not fetch option chain for {symbol}")
        return None
    
    opportunities = []
    
    for exp in chain['expiration_dates']:
        for strike_data in exp['strikes']:
            strike = strike_data['strike']
            premium = strike_data['mark']
            iv = strike_data['iv']
            
            if not premium or not strike:
                continue
            
            # Calculate metrics
            collateral = strike * 100  # Per contract
            return_pct = (premium / strike) * 100
            distance_pct = ((current_price - strike) / current_price) * 100
            breakeven = strike - premium
            
            # Check if meets criteria
            if return_pct >= target_return * 100 and distance_pct > 0:
                opportunities.append({
                    'symbol': symbol,
                    'expiration': exp['date'],
                    'days_to_expiry': strike_data['days_to_expiry'],
                    'strike': strike,
                    'premium': premium,
                    'return_pct': return_pct,
                    'distance_pct': distance_pct,
                    'breakeven': breakeven,
                    'iv': iv,
                    'collateral': collateral,
                    'delta': strike_data['delta'],
                    'theta': strike_data['theta']
                })
    
    # Sort by best risk/reward (highest return with reasonable distance)
    opportunities.sort(key=lambda x: (x['return_pct'], x['distance_pct']), reverse=True)
    
    return {
        'quote': quote,
        'opportunities': opportunities[:5],  # Top 5
        'chain': chain
    }


def print_opportunity(opp):
    """Print formatted opportunity"""
    print(f"\n   [$] CSP Opportunity:")
    print(f"      Strike: ${opp['strike']:.2f}")
    print(f"      Premium: ${opp['premium']:.2f} (mark)")
    print(f"      Return: {opp['return_pct']:.2f}%")
    print(f"      Distance OTM: {opp['distance_pct']:.2f}%")
    print(f"      Breakeven: ${opp['breakeven']:.2f}")
    print(f"      Collateral: ${opp['collateral']:,.2f}")
    print(f"      IV: {opp['iv']:.2f}%" if opp['iv'] else "      IV: N/A")
    print(f"      Expiration: {opp['expiration']} ({opp['days_to_expiry']} DTE)")


def save_analysis(symbol, analysis):
    """Save analysis to file for Aristotle"""
    output_dir = CONFIG_DIR / "analysis"
    output_dir.mkdir(exist_ok=True)
    
    filename = output_dir / f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(filename, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"\n[SAVE] Analysis saved to: {filename}")
    return filename


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Schwab API Data Bridge')
    parser.add_argument('--quotes', help='Comma-separated symbols for quotes')
    parser.add_argument('--chains', help='Symbol for option chain')
    parser.add_argument('--days', type=int, default=30, help='Days to expiration')
    parser.add_argument('--analyze', help='Symbol for full CSP analysis')
    parser.add_argument('--setup', action='store_true', help='Setup configuration')
    
    args = parser.parse_args()
    
    if args.setup:
        print("🔧 Schwab API Setup")
        print("=" * 50)
        client_id = input("Enter Client ID: ").strip()
        client_secret = input("Enter Client Secret: ").strip()
        account_number = input("Enter Account Number (last 4 digits): ").strip()
        
        config = {
            'client_id': client_id,
            'client_secret': client_secret,
            'account_number': account_number
        }
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)
        
        print("\n[OK] Configuration saved!")
        print("Next: Run OAuth authentication to get tokens")
        
    elif args.quotes:
        symbols = [s.strip().upper() for s in args.quotes.split(',')]
        quotes = get_quotes(symbols)
        
        if quotes:
            print("\n[CHART] Real-Time Quotes")
            print("=" * 60)
            for sym, q in quotes.items():
                print(f"\n{sym}:")
                print(f"   Price: ${q['price']:.2f}" if q['price'] else "   Price: N/A")
                print(f"   Change: {q['change']:.2f} ({q['change_percent']:.2f}%)")
                print(f"   Bid/Ask: ${q['bid']:.2f} / ${q['ask']:.2f}")
                print(f"   Volume: {q['volume']:,}")
    
    elif args.chains:
        chain = get_option_chains(args.chains, days_to_expiration=args.days)
        if chain:
            print(f"\n[CHAIN] Option Chain: {args.chains}")
            print(f"Underlying: ${chain['underlying_price']:.2f}")
            print(f"\nExpiration Dates:")
            for exp in chain['expiration_dates']:
                print(f"\n  {exp['date']} ({exp['days_to_expiry']} DTE):")
                for strike in exp['strikes'][:5]:  # Show first 5 strikes
                    print(f"    Strike: ${strike['strike']:.2f}, "
                          f"Mark: ${strike['mark']:.2f}, "
                          f"IV: {strike['iv']:.1f}%" if strike['iv'] else "")
    
    elif args.analyze:
        analysis = analyze_csp_opportunity(args.analyze)
        if analysis:
            print("\n" + "=" * 60)
            print(f"[ANALYSIS] CSP Analysis: {args.analyze}")
            print("=" * 60)
            
            for opp in analysis['opportunities']:
                print_opportunity(opp)
            
            save_analysis(args.analyze, analysis)
    
    else:
        parser.print_help()
