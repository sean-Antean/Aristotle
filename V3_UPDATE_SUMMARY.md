# Capital Flywheel v3.0 Update Summary
# Date: June 6, 2026
# Updated by: Danu

## Overview
Updated all Capital Flywheel files to v3.0 per the June 5, 2026 Complete Build Guide.

## Files Updated

### 1. SKILL.md
- Updated version metadata to v3.0 (date: 2026-06-05)
- Added expanded entry criteria (8 criteria including cash reserve and market regime)
- Added EMA Cloud Calculation section with scoring rules
- Added Exit Strategy section (Primary/Secondary/Tertiary)
- Added Stop Trading Triggers
- Updated position sizing to match build guide exactly
- Added LEVERAGED_* / CORE_* classification label definitions

### 2. CAPITAL_FLYWHEEL_PLAN.txt
- Updated date to June 5, 2026
- Added Three-Universe Structure section with complete ticker lists
- Added all 8 entry criteria with checkboxes
- Added Exit Strategy section (Primary/Secondary/Tertiary)
- Added Stop Trading Triggers
- Updated position sizing tables for both Core and Leveraged universes
- Added total exposure limits (max total collateral, min cash reserve, max leveraged exposure)
- Restructured report format to six sections
- Added version history entry for v3.0

### 3. daily_scan_v3.py (renamed from daily_scan_v2.py)
- Updated CAPITAL FLYWHEEL RISK MODEL comment to v3.0
- Renamed PORTFOLIO_VALUE to PORTFOLIO_EQUITY (v3.0 naming)
- Added v3.0 position sizing constants:
  - CORE_STANDARD_MAX = $15,000 (10%)
  - CORE_HIGH_CONVICTION_MAX = $30,000 (20%)
  - CORE_OVERSIZED_MAX = $37,500 (25%)
  - LEVERAGED_STANDARD_MAX = $15,000 (10%)
  - LEVERAGED_AGGRESSIVE_MAX = $22,500 (15%)
  - LEVERAGED_OVERSIZED_MAX = $37,500 (25%)
- Added portfolio-wide limits:
  - MAX_SINGLE_LEVERAGED = $22,500 (15%)
  - MAX_TOTAL_LEVERAGED = $37,500 (25%)
- Updated COLLATERAL_LIMITS to use new constants
- Completely rewrote get_candidate_tier() with separate Core vs Leveraged logic
- Updated classify_candidate() to return universe-prefixed labels (LEVERAGED_*/CORE_*)
- Rewrote generate_report() to produce six-section v3.0 format:
  - SECTION 1: SUMMARY
  - SECTION 2: PRIMARY CAPITAL FLYWHEEL LEVERAGED UNIVERSE RESULTS
  - SECTION 3: EXPANDED LEVERAGED SANDBOX RESULTS
  - SECTION 4: CORE / CONSERVATIVE UNIVERSE RESULTS
  - SECTION 5: REJECTED TICKERS
  - SECTION 6: ACTION REQUIRED
- Added _report_candidate_details() helper function

### 4. CHANGELOG.md
- Updated last updated date to 2026-06-05
- Added v3.0 Complete Build Guide Update section with all changes
- Documented 8 entry criteria
- Documented exit strategy
- Documented stop trading triggers
- Documented six-section report format

### 5. HEARTBEAT.md
- Updated Aristotle cron job description to reference v3.0
- Updated to mention LEVERAGED_* and CORE_* classifications
- Updated to reference 8 entry criteria

## Key Changes from Previous Version

### Position Sizing Updated
- Core STANDARD: $15,000 (was $25,000)
- Core HIGH-CONVICTION: $30,000 (was $50,000)
- Core OVERSIZED: $37,500 (was $62,500)
- Leveraged AGGRESSIVE: $22,500 (new tier)
- Leveraged OVERSIZED: $37,500 (was $25,000 max)

### New Classification Labels
All classifications now prefixed with universe:
- LEVERAGED_TRADE_REVIEW (was TRADE_CANDIDATE)
- LEVERAGED_WATCH_ONLY
- LEVERAGED_MANUAL_VERIFY_REQUIRED
- LEVERAGED_OVERSIZED_ANALYSIS_ONLY
- LEVERAGED_REJECT
- CORE_TRADE_REVIEW
- CORE_WATCH_ONLY
- CORE_MANUAL_VERIFY_REQUIRED
- CORE_OVERSIZED_ANALYSIS_ONLY
- CORE_REJECT

### New Entry Criteria
Added to the existing 6:
7. Cash Reserve: 50% minimum maintained
8. Market Regime: MARKET_OPEN for trade review

### Exit Strategy Defined
- Primary: GTC buy-to-close at 50% profit
- Secondary: Close at 21 DTE regardless
- Tertiary: Roll or take assignment if down >15%

### Stop Trading Triggers
- 3 consecutive losses
- Portfolio down >10% from peak
- All clouds bearish (market downtrend)
- Emotional/stress trading detected

## Verification
- All Python files compile without syntax errors
- daily_scan_v3.py: py_compile passed
- schwab_bridge.py: py_compile passed
- schwab_auth.py: py_compile passed
- token_refresh.py: py_compile passed

## Next Steps
1. Test daily_scan_v3.py during market hours
2. Verify report generates with six sections
3. Confirm classification labels are correct
4. Test with sample tickers from each universe
