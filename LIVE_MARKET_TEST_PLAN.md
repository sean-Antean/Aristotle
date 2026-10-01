# Capital Flywheel — Live Market Test Plan

**Date:** Tuesday, May 27, 2026 (Markets closed Monday 5/26 for Memorial Day)  
**Time Window:** 9:45–10:15 AM ET  
**Status:** PENDING — Markets closed Monday 5/26  

---

## Pre-Test Checklist

- [ ] Market is open (9:30 AM ET or later)
- [ ] Schwab API tokens are valid (run `token_refresh.py`)
- [ ] ngrok tunnel is running (if remote access needed)
- [ ] Capital Flywheel Paper Trading Guide is accessible in Downloads folder
- [ ] thinkorswim paperMoney is open and ready

---

## Test Procedure

### Step 1: Run Corrected Daily Scan
```powershell
cd C:\Users\Ionai48q\.openclaw-work\workspaces\work\skills\aristotle-capital-flywheel
python daily_scan_v3.py
```

### Step 2: Verify Persistent Corrections
Confirm all 7 checks pass:
- [ ] No hard $100 price cap
- [ ] Strike-level collateral filter active
- [ ] Max Phase 1 collateral: $12,500
- [ ] Rejection reasons required
- [ ] Ticker validator restricted
- [ ] Leveraged ETFs: PAPER TEST ONLY
- [ ] Read-only analysis mode

### Step 3: Review Score Breakdown
For top 5 candidates, verify:
- [ ] Quality score: 0-15 points
- [ ] Cloud score: 0-25 points (currently 0 pending manual verify)
- [ ] Pullback score: 0-15 points
- [ ] IV score: 0-15 points
- [ ] Liquidity score: 0-15 points
- [ ] Earnings score: 0-10 points
- [ ] Portfolio fit: 0-5 points

**Expected:** If cloud score is 0, max possible is 75/100. This is correct until EMA data is available.

### Step 4: Review Rejection Reasons
For each rejected ticker, verify:
- [ ] Exact reason provided (not generic)
- [ ] Reason references specific filter failure
- [ ] No tickers rejected solely for price > $100

### Step 5: Check Paper-Test ETFs
Verify lower-priced ETFs appear in scan:
- [ ] XLF, XLE, XLI, XLV, XLY, XLP, XLU, XBI, ARKK
- [ ] Each marked as "PAPER TEST CANDIDATE ONLY" if mentioned
- [ ] Each must pass all filters to be trade candidate

### Step 6: Validate Output
Run validator:
```powershell
python instruction_validator.py
```
- [ ] No hard rule violations
- [ ] No false positive ticker warnings

### Step 7: Human Review
- [ ] Review daily report
- [ ] Confirm trend on TradingView for any candidates
- [ ] Check earnings dates manually
- [ ] Decide: trade / watch / reject
- [ ] If trading: Enter in thinkorswim paperMoney manually
- [ ] Set 50% profit GTC exit order
- [ ] Screenshot filled order

---

## Success Criteria

### Must Pass (All Required)
1. [ ] No API errors
2. [ ] Persistent corrections verified
3. [ ] Score breakdown displayed for top 5
4. [ ] All rejections have exact reasons
5. [ ] No hard price cap applied
6. [ ] Strike-level collateral filtering works
7. [ ] No false positive ticker warnings
8. [ ] Report saved to `reports/` folder
9. [ ] No trades placed by agent (read-only confirmed)

### Should Pass (Highly Desired)
10. [ ] At least 1 candidate with score ≥ 70
11. [ ] At least 1 candidate with opportunities found
12. [ ] Paper-test ETFs appear in scan results
13. [ ] Diagnostic output for near-eligible tickers

### Nice to Have
14. [ ] At least 1 TRADE CANDIDATE (score ≥ 85)
15. [ ] Multiple expiration dates available
16. [ ] IV data populated for opportunities

---

## Post-Test Actions

### If Test Passes (All Must-Pass criteria met):
1. [ ] Document results in journal
2. [ ] Commit report to git
3. [ ] **Schedule cron job** for 9:45 AM ET daily:
   ```powershell
   # Command to schedule (run as admin if needed)
   schtasks /create /tn "CapitalFlywheel-Scan" /tr "python daily_scan_v3.py" /sc daily /st 09:45
   ```
4. [ ] Update status: READY FOR SCHEDULED OPERATION

### If Test Fails (Any Must-Pass criteria missed):
1. [ ] Document failure reason
2. [ ] Fix issue
3. [ ] Re-run test
4. [ ] Do NOT schedule cron job until clean test

---

## Known Limitations

1. **EMA Cloud Scores**: Currently show 0/25 pending manual TradingView verification. This is expected.
2. **Earnings Data**: Not available via API — manual check required.
3. **Historical Data**: Limited weekly OHLC for EMA calculation — using simplified proxy.
4. **After-Hours**: Test must occur during market hours (9:30 AM - 4:00 PM ET) for valid data.

---

## Rollback Plan

If issues arise:
1. Stop scan: `Ctrl+C` or close terminal
2. Check tokens: `python token_refresh.py`
3. Check ngrok: Restart if needed
4. Review logs in `reports/` folder
5. Revert to previous commit if needed: `git checkout HEAD~1`

---

**Test Owner:** Young Grasshoppa  
**Agent:** Aristotle (via Danu)  
**Document Version:** 1.0  
**Last Updated:** 2026-05-24

---

## Notes

- This is the **final validation test** before enabling daily automation
- Per Section 26.7: "A scheduled job may be added only after one more clean manual test run"
- Per Section 27.2: Cron job must run analysis only and must not place trades
- All trades remain manual in thinkorswim paperMoney

**DO NOT PROCEED TO SCHEDULING WITHOUT CLEAN TEST RESULTS**
