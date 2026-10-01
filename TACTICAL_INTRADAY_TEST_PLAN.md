# TACTICAL_INTRADAY Test Plan
**Date:** 2026-08-13  
**Purpose:** Validate the new intraday pullback mode before going LIVE

---

## Pre-Test Checklist

- [ ] Market is OPEN (9:30 AM - 4:00 PM ET)
- [ ] Schwab API authenticated and reachable
- [ ] Target ticker is GREEN on the day (> 0% change)
- [ ] Target ticker has completed 60m or 30m RED candle
- [ ] Cash reserve ≥ 50%

---

## Test Cases

### Test 1: Green Day + Red 60m Candle (Expected: TACTICAL_INTRADAY-60m)
```bash
python flash_check.py TQQQ
```
**Expected Output:**
- Verdict: TRADE
- Setup: TACTICAL_INTRADAY-60m
- Session high displayed
- Pullback % ≥ 1%
- Collateral capped at 5%
- Single tranche only

### Test 2: Green Day + Red 30m Candle (Expected: TACTICAL_INTRADAY-30m)
```bash
python flash_check.py SOXL
```
**Expected Output:**
- Verdict: TRADE
- Setup: TACTICAL_INTRADAY-30m
- Fallback from 60m to 30m confirmed

### Test 3: Green Day + No Red Candle (Expected: REJECT)
```bash
python flash_check.py QQQ
```
**Expected Output:**
- Verdict: REJECT
- Reason: green day, intraday override failed

### Test 4: Non-Core Ticker (Expected: REJECT)
```bash
python flash_check.py AMZU
```
**Expected Output:**
- Verdict: REJECT
- Reason: AMZU not in core_tickers_only for intraday mode

### Test 5: Cash < 50% (Expected: REJECT)
```bash
# Verify cash state first
python reconcile.py
# Then test
python flash_check.py TQQQ
```
**Expected Output:**
- Verdict: REJECT
- Reason: intraday mode blocked (cash state: aggressively deployed)

### Test 6: Hard Gate Failure (Expected: REJECT, no intraday attempt)
```bash
# Test when QQQ clouds < 2/3 or weekly trend < 2/3
python flash_check.py TQQQ
```
**Expected Output:**
- Verdict: REJECT
- Reason: hard gate failure (QQQ or trend)
- No intraday override attempted

---

## Post-Test Validation

- [ ] All test cases produce expected results
- [ ] Output format is clear and actionable
- [ ] Intraday override details display correctly
- [ ] Sizing cap at 5% enforced
- [ ] Single tranche enforced
- [ ] No regressions in standard A+/A/B logic

---

## Sign-Off

| Role | Name | Status | Date |
|------|------|--------|------|
| Implementation | Buddy | ⏳ Pending | |
| Review | Quinn | ⏳ Pending | |
| Security | Jasmine | N/A (no auth/crypto changes) | |
| Approval | Young Grasshoppa | ⏳ Pending | |
