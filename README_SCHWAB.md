# Aristotle Capital Flywheel - Schwab API Integration

## Overview
This integration provides real-time market data from Schwab's API to feed Aristotle's analysis engine, while you continue to execute trades manually in thinkorswim paperMoney.

## Architecture
```
Schwab API (live data)
    ↓
schwab_bridge.py (Python)
    ↓
aristotle_schwab.py (interface)
    ↓
Aristotle (analysis & recommendations)
    ↓
You (decision & execution in thinkorswim paperMoney)
```

## Files

| File | Purpose |
|------|---------|
| `schwab_bridge.py` | Core API client - fetches quotes, option chains |
| `schwab_auth.py` | OAuth authentication - one-time setup |
| `aristotle_schwab.py` | Simple interface for Aristotle to call |
| `setup.bat` | Windows setup script |
| `tracker.md` | Position tracking template |

## Setup Instructions

### Step 1: Configure API Credentials

```bash
python schwab_bridge.py --setup
```

Enter when prompted:
- **Client ID**: From your Schwab Developer Portal app
- **Client Secret**: From your Schwab Developer Portal app  
- **Account Number**: Last 4 digits of your Schwab account

### Step 2: OAuth Authentication

```bash
python schwab_auth.py
```

This will:
1. Start a local web server on port 3000
2. Open your browser to Schwab login
3. You log in and authorize "Aristotle Trading Agent"
4. Tokens are saved locally (never sent to anyone)

### Step 3: Test Connection

```bash
# Test quotes
python schwab_bridge.py --quotes TSLL,NVDL,TQQQ,SOXL,AMZN

# Test option chain
python schwab_bridge.py --chains TSLL --days 30

# Full CSP analysis
python schwab_bridge.py --analyze TSLL
```

## Usage for Aristotle

### Get Watchlist Data
```python
from aristotle_schwab import get_watchlist_data

data = get_watchlist_data()
print(data)
# Output:
# TSLL: $45.23
#   Change: -4.2%
# NVDL: $89.45
#   Change: +1.3%
# ...
```

### Find Down-Day Candidates
```python
from aristotle_schwab import get_down_day_candidates

candidates = get_down_day_candidates(threshold=-3.0)
# Returns: [{'symbol': 'TSLL', 'change': -4.2}, ...]
```

### Analyze CSP Opportunity
```python
from aristotle_schwab import analyze_opportunities

analysis = analyze_opportunities('TSLL')
print(analysis)
# Output:
# 📊 Analysis: TSLL
# Current Price: $45.23
# Change: -4.2%
# 
# Top CSP Opportunities:
# 1. Strike: $43.00
#    Premium: $2.15
#    Return: 5.0%
#    Distance OTM: 4.9%
#    Breakeven: $40.85
#    Collateral: $4,300.00
#    Expiration: 2026-06-20 (28 DTE)
#    IV: 62.5%
```

## Security

- ✅ Tokens stored locally with 0600 permissions
- ✅ Client Secret never transmitted after setup
- ✅ OAuth flow happens on your machine only
- ✅ Read-only access to market data (no trading via API)

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| Quotes | 120/minute |
| Option Chains | 120/minute |
| Account Info | 120/minute |

## Troubleshooting

### "No tokens found"
Run `python schwab_auth.py` to authenticate

### "Token expired"
The bridge auto-refreshes tokens. If it fails, re-run `python schwab_auth.py`

### "API Error 401"
- Check that your app is "Production" (not Sandbox)
- Verify Client ID and Secret are correct
- Re-authenticate if tokens are corrupted

### "Cannot connect to localhost:3000"
- Port 3000 may be in use
- Change REDIRECT_PORT in schwab_auth.py
- Update callback URL in Schwab Developer Portal

## Next Steps

1. ✅ Complete OAuth setup
2. ✅ Test data feeds
3. ⬜ Integrate into Aristotle's morning scan
4. ⬜ Automate daily data pulls
5. ⬜ Build position tracking from API data

## Notes

- This is **read-only** — no orders can be placed via API
- All trades still happen manually in thinkorswim paperMoney
- You maintain full control over execution
- API provides faster, more accurate data than screenshots
