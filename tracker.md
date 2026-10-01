# Aristotle Capital Flywheel — Position Tracker
# ⚠️ DEPRECATED (v3 paperMoney template). Live positions now come from
#    `python reconcile.py` (reads both Schwab IRAs). Kept for reference only.
# Updated: [AUTO]
# Account: $250,000 paperMoney (OBSOLETE — live is ~$194.7K across IRA *159 + Roth *472)

## API INTEGRATION

### Schwab API Status
- [ ] App created and approved
- [ ] OAuth authentication completed
- [ ] Test quotes endpoint
- [ ] Test option chains endpoint
- [ ] Live data feed active

### Data Sources
| Source | Status | Use |
|--------|--------|-----|
| Schwab API (live quotes) | ⬜ Setup | Real-time watchlist data |
| Schwab API (option chains) | ⬜ Setup | IV, strikes, premiums |
| thinkorswim screenshots | ✅ Active | Execution confirmation |
| TradingView charts | ✅ Active | Trend confirmation |

## CURRENT POSITIONS

| # | Ticker | Type | Strike | Exp | Contracts | Entry Premium | GTC Exit | Status | P&L | Days |
|---|--------|------|--------|-----|-----------|---------------|----------|--------|-----|------|
|   |        |      |        |     |           |               |          |        |     |      |

## CASH SUMMARY

- Total Account: $250,000
- Cash Reserved (Collateral): $0
- Buying Power: $250,000
- Cash Reserve (20%): $50,000
- Available for Trades: $200,000

## TRADE HISTORY

| Date | Ticker | Action | Strike | Exp | Premium | Result | Notes |
|------|--------|--------|--------|-----|---------|--------|-------|
|      |        |        |        |     |         |        |       |

## WATCHLIST STATUS

| Ticker | Last Price | % Change | IV | Cloud Status | Grade | Action |
|--------|-----------|----------|-----|--------------|-------|--------|
| TSLL   |           |          |     |              |       |        |
| NVDL   |           |          |     |              |       |        |
| TQQQ   |           |          |     |              |       |        |
| SOXL   |           |          |     |              |       |        |
| AMZN   |           |          |     |              |       |        |

## MONTHLY PERFORMANCE

| Month | # Trades | Win Rate | Premium Collected | Assignments | Net P&L |
|-------|----------|----------|-------------------|-------------|---------|
|       |          |          |                   |             |         |

## NOTES

- Strategy: Capital Flywheel (CSP → Wheel)
- Target: 5% monthly per position
- Exit: 50% of premium
- Max position: 25% ($62,500)
- Max concurrent: 3-4 positions
