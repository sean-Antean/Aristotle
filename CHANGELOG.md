# Capital Flywheel Changelog

## Version History & Corrections

**Last Updated:** 2026-06-05  
**Status:** ACTIVE — v3.0 Three-Universe Structure (Build Guide Updated)  
**Master Document:** `CAPITAL_FLYWHEEL_PLAN.txt` (v3.0)

---

## CRITICAL: Script Version Control

### Active Scripts (USE THESE)

| Script | Version | Status | Purpose |
|--------|---------|--------|---------|
| `daily_scan_v3.py` | v3.0 | ✅ **ACTIVE** | Daily market scan with three-universe structure |
| `schwab_bridge.py` | v1.2 | ✅ **ACTIVE** | Schwab API data fetching |
| `token_refresh.py` | v1.0 | ✅ **ACTIVE** | OAuth token management |

### Deprecated Scripts (DO NOT USE)

| Script | Version | Status | Reason |
|--------|---------|--------|--------|
| `daily_scan_v1_DEPRECATED.py` | v1.0 | ❌ **DEPRECATED** | Hard $100 price cap, generic diagnostics |

---

## Version History

### 2026-06-05 — v3.0 Complete Build Guide Update

**Major Changes (from Build Guide):**
1. **Three-Universes Confirmed:**
   - Primary Capital Flywheel Leveraged Universe (9 tickers)
   - Expanded Leveraged Sandbox Universe (19 tickers)
   - Core / Conservative Universe (26 tickers)

2. **Entry Criteria Expanded (8 criteria):**
   - Weekly EMA Cloud (2/3 or 3/3 bullish)
   - Down Day (-1% to -7%, ideal -2% to -5%)
   - IV Valid and Available
   - Option Liquidity (Spread <=10%, OI >=25, Vol >=10)
   - Earnings Not Before Expiration
   - Portfolio Within Tier Limits
   - Cash Reserve 50% Minimum
   - Market Regime MARKET_OPEN

3. **Classification Labels (v3.0 prefix system):**
   - Leveraged: `LEVERAGED_TRADE_REVIEW`, `LEVERAGED_WATCH_ONLY`, `LEVERAGED_MANUAL_VERIFY_REQUIRED`, `LEVERAGED_OVERSIZED_ANALYSIS_ONLY`, `LEVERAGED_REJECT`
   - Core: `CORE_TRADE_REVIEW`, `CORE_WATCH_ONLY`, `CORE_MANUAL_VERIFY_REQUIRED`, `CORE_OVERSIZED_ANALYSIS_ONLY`, `CORE_REJECT`

4. **Position Sizing ($150,000):**
   - Core: STANDARD <=$15K (10%), HIGH-CONVICTION <=$30K (20%), OVERSIZED <=$37.5K (25%)
   - Leveraged: STANDARD <=$15K (10%), AGGRESSIVE <=$22.5K (15%), OVERSIZED <=$37.5K (25%)
   - Max total collateral: 50% ($75,000)
   - Min cash reserve: 50% ($75,000)
   - Max total leveraged: 25% ($37,500)
   - Max single leveraged: 15% ($22,500)

5. **Exit Strategy Defined:**
   - Primary: GTC buy-to-close at 50% profit
   - Secondary: Close at 21 DTE regardless
   - Tertiary: Roll or take assignment if down >15%

6. **Stop Trading Triggers Added:**
   - 3 consecutive losses
   - Portfolio down >10% from peak
   - All clouds bearish (market downtrend)
   - Emotional/stress trading detected

7. **Report Format: Six Sections**
   - SECTION 1: SUMMARY
   - SECTION 2: PRIMARY CAPITAL FLYWHEEL LEVERAGED UNIVERSE RESULTS
   - SECTION 3: EXPANDED LEVERAGED SANDBOX RESULTS
   - SECTION 4: CORE / CONSERVATIVE UNIVERSE RESULTS
   - SECTION 5: REJECTED TICKERS (grouped by reason)
   - SECTION 6: ACTION REQUIRED

8. **Files Updated:**
   - `SKILL.md` — v3.0 skill definition
   - `CAPITAL_FLYWHEEL_PLAN.txt` — Complete trading plan
   - `daily_scan_v3.py` — Scanner with v3.0 position sizing and labels
   - `CHANGELOG.md` — Version history

**Previous:** 2026-05-28 — v3.0 Three-Universe Structure Initial

---

### 2026-05-27 — v2.2 Cron Job + Encoding Fixes

**Changes:**
- Scheduled Aristotle 9:45 AM ET daily scan cron job
- Fixed UTF-8 encoding for Windows console output
- Updated report language to analysis-only

**Commits:**
- `3ba15a0` — Schedule Aristotle analysis-only 9:45 AM ET cron job
- `57c31aa` — Fix UTF-8 encoding and update analysis-only report language

---

### 2026-05-26 — v2.1 Post-Rollback Restoration

**Issue:** After gateway restart/rollback, old `daily_scan.py` was being used instead of corrected `daily_scan_v3.py`

**Root Cause:**
- Two versions existed: `daily_scan.py` (buggy) and `daily_scan_v3.py` (corrected)
- Session starter didn't specify which script to run
- No deprecation mechanism prevented accidental use of old script

**Fixes Applied:**
1. ✅ Renamed `daily_scan.py` → `daily_scan_v1_DEPRECATED.py`
2. ✅ Added prominent DEPRECATED warning to old script
3. ✅ Updated session starter to specify `daily_scan_v3.py`
4. ✅ Fixed option-chain diagnostics (deterministic blocking reasons)
5. ✅ Fixed cloud score display (Bull/Bear labels)

**Commits:**
- `b6edaf7` — Restore Capital Flywheel post-rollback corrections
- `b402c3a` — Fix option-chain diagnostics
- `82fd664` — Deprecate daily_scan.py

---

### 2026-05-24 — v2.0 Sections 26-27 Corrections Applied

**Original Issue:** `daily_scan.py` had fundamental flaws

**Corrections (from Capital Flywheel Paper Trading Guide):**

#### Section 26.1 — No Hard Price Cap
- **Before:** Rejected tickers with price > $100
- **After:** Affordability determined at option strike level
- **Formula:** `collateral = strike_price × 100 × contracts`

#### Section 26.2 — Strike-Level Collateral Filtering
- **Before:** Quote-level price check
- **After:** Evaluate each put strike against tier-based limits
- **Rule:** Reject only if NO strike satisfies tier requirements

#### Section 26.3 — Deterministic Diagnostics
- **Before:** "Unknown blocking factor — manual review needed"
- **After:** Specific blocking reasons in priority order

#### Section 26.6 — Ticker Validation
- **Before:** Generic regex flagged words like "TOP", "FROM", "GTC"
- **After:** Only validate against approved universe or API responses

#### Section 27.3 — Persistent Corrections Verification
- Added startup check that verifies all corrections loaded
- Fails fast if any correction is missing

**Commit:** `8db9d99` — Capital Flywheel v2.0: Apply Sections 26-27 corrections

---

## Rollback Recovery Notes

### If Rollback Occurs in Future

1. **Check script versions** — Ensure `daily_scan_v3.py` exists and is being used
2. **Verify corrections loaded** — Look for startup verification message
3. **Check git history** — Corrections are in commits `5020faa`, `8db9d99`, `b402c3a`, `82fd664`
4. **Do NOT use `daily_scan_v1_DEPRECATED.py`** — It has known bugs (use `daily_scan_v3.py`)

### Files to Preserve During Rollback

**CRITICAL (must keep latest version):**
- `daily_scan_v3.py` — Contains all v3.0 corrections
- `schwab_bridge.py` — EMA cloud calculation
- `ARISTOTLE_INSTRUCTIONS.md` — Master document v3.0
- `SKILL.md` — Skill definition v3.0
- `CAPITAL_FLYWHEEL_PLAN.txt` — Trading plan v3.0

**SAFE to restore from backup:**
- `schwab_tokens.json` — Will refresh automatically
- `reports/` — Historical data, can regenerate

---

## Testing Checklist

Before scheduling cron job or going live:

- [ ] Run `daily_scan_v3.py` (not v1)
- [ ] Verify startup corrections check passes
- [ ] Confirm three-universe structure active
- [ ] Verify leveraged products NOT auto-rejected
- [ ] Confirm LEVERAGED_* / CORE_* classification labels
- [ ] Check six-section report format
- [ ] Verify strike-level collateral filtering
- [ ] Check EMA cloud scores display correctly (Bull/Bear)
- [ ] Confirm deterministic diagnostics (not "Unknown blocking factor")
- [ ] Validate full rejected list with reasons
- [ ] Check timestamp shows ET
- [ ] Confirm read-only mode active
- [ ] Test during market hours (9:30 AM - 4:00 PM ET)
- [ ] Verify down-day detection works with live data
- [ ] Confirm IV validation (no -999.0% displayed as real)
- [ ] Verify no generic PASS labels

---

## Known Limitations

1. **Earnings checking** — Currently MANUAL_VERIFY only. Needs API integration.
2. **Market hours** — After-hours scans may not detect down days correctly.
3. **EMA cloud** — Requires sufficient weekly historical data (100+ candles).
4. **Leveraged ETFs** — Higher volatility, gap risk, decay. Paper testing only.
5. **IV data** — Schwab API occasionally returns -999.0% for IV. Script handles this as INVALID.

---

## Active Model Summary (v3.0)

### Three Universes
- **Primary Leveraged:** SOXL, TNA, TQQQ, GGLL, AMZU, MSFU, NVDL, TSLL, BITX
- **Expanded Leveraged:** QLD, UPRO, SSO, URTY, UDOW, TECL, FAS, DPST, LABU, NAIL, ERX, CURE, WEBL, BITU, CONL, AAPU, METU, AMDL, NVDU
- **Core Conservative:** NVDA, AMD, AMZN, GOOGL, MSFT, META, AAPL, ORCL, JPM, COST, LLY, UNH, SPY, QQQ, IWM, SMH, XLK, XLE, XLF, XLV, XLP, XLI, XLU, XLY, XBI, ARKK

### Classification Labels
- **LEVERAGED_TRADE_REVIEW** / **CORE_TRADE_REVIEW**: All hard filters pass
- **LEVERAGED_WATCH_ONLY** / **CORE_WATCH_ONLY**: Opportunities exist but not trade-ready
- **LEVERAGED_MANUAL_VERIFY_REQUIRED** / **CORE_MANUAL_VERIFY_REQUIRED**: Needs human confirmation
- **LEVERAGED_REJECT** / **CORE_REJECT**: Fails hard filters

### Position Sizing ($150,000)
- **Core:** STANDARD <=$15K, HIGH-CONVICTION <=$30K, OVERSIZED <=$37.5K
- **Leveraged:** STANDARD <=$15K, AGGRESSIVE <=$22.5K, OVERSIZED <=$37.5K

### Key Rules
- Weekly EMA cloud is THE core hard filter (score >= 2 required)
- Strike-level collateral filtering (never price-based)
- Read-only mode (never place trades)
- Human confirmation required
- Leveraged products require explicit risk note

---

## Contact

For issues or questions about corrections:
- Review `ARISTOTLE_INSTRUCTIONS.md` (v3.0)
- Check git log: `git log --oneline -- skills/aristotle-capital-flywheel/`
- Master document: Capital Flywheel Paper Trading Guide
