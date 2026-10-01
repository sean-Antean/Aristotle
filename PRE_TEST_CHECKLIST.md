# Capital Flywheel — Pre-Test Checklist & Final Requirements

**Date:** Wednesday, May 28, 2026  
**Time Window:** 9:45–10:15 AM ET  
**Status:** READY FOR LIVE-MARKET TEST  
**Version:** v3.0 — Three-Universe Structure

---

## ✅ SYSTEM STATUS (As of 2026-05-28 01:20 ET)

### Working Correctly:
- [x] Schwab API authentication (auto-refresh)
- [x] Real-time quote fetching (54 tickers across 3 universes)
- [x] Weekly EMA cloud calculation from candle data
- [x] Hard filter: cloud_score < 2 = REJECT
- [x] Three-universe structure implemented
- [x] Leveraged products NOT auto-rejected
- [x] LEVERAGED_* / CORE_* classification labels
- [x] Strike-level collateral filtering
- [x] Score breakdown display
- [x] Full rejection categories with counts
- [x] Read-only mode (no trades placed)
- [x] Six-section report format

### Verified EMA Cloud Scores (from test run):
| Ticker | Universe | Score | Fast | Medium | Slow | Result |
|--------|----------|-------|------|--------|------|--------|
| SOXL | Primary Leveraged | 3/3 | Bull | Bull | Bull | LEVERAGED_TRADE_REVIEW |
| NVDA | Core | 3/3 | Bull | Bull | Bull | CORE_TRADE_REVIEW |
| MSFT | Core | 1/3 | Bull | Bear | Bear | CORE_REJECT |

---

## 📋 FINAL REPORT-QUALITY REQUIREMENTS

### 1. Three-Universes Structure (CRITICAL)

**Rule:** All 54 tickers must be categorized into one of three universes:

| Universe | Tickers | Classification Prefix |
|----------|---------|----------------------|
| Primary Leveraged | 9 tickers | LEVERAGED_* |
| Expanded Leveraged | 19 tickers | LEVERAGED_* |
| Core Conservative | 26 tickers | CORE_* |

**Implementation:**
- Scanner uses `TICKER_UNIVERSES` dictionary
- Each ticker mapped to its universe
- Classification labels include universe prefix

---

### 2. Leveraged Products Handling (CRITICAL)

**Rule:** Leveraged products must NOT be auto-rejected.

| Scenario | Action |
|----------|--------|
| Leveraged product in Primary Universe | Evaluate normally, use LEVERAGED_* labels |
| Leveraged product in Expanded Universe | Evaluate normally, use LEVERAGED_* labels |
| Leveraged product fails filters | LEVERAGED_REJECT with reason |

**Risk Note Required:**
> "[!] Leveraged product — paper testing only. Higher volatility, gap risk, decay, assignment risk, and faster drawdowns. Manual confirmation required."

---

### 3. Classification Labels (CRITICAL)

**Rule:** Use only v3.0 labels. Do NOT use generic PASS or old labels.

| Label Type | Values |
|------------|--------|
| Leveraged | LEVERAGED_TRADE_REVIEW, LEVERAGED_WATCH_ONLY, LEVERAGED_MANUAL_VERIFY_REQUIRED, LEVERAGED_OVERSIZED_ANALYSIS_ONLY, LEVERAGED_REJECT |
| Core | CORE_TRADE_REVIEW, CORE_WATCH_ONLY, CORE_MANUAL_VERIFY_REQUIRED, CORE_OVERSIZED_ANALYSIS_ONLY, CORE_REJECT |

---

### 4. Earnings Handling (CRITICAL)

**Rule:** Earnings status must be clear and unambiguous.

| Scenario | Score | Classification |
|----------|-------|----------------|
| Earnings confirmed AFTER expiration | 10/10 | Can be TRADE if other filters pass |
| Earnings confirmed BEFORE expiration | Hard Reject | Cannot be TRADE or WATCH |
| Earnings date unavailable | MANUAL_VERIFY | Cannot be TRADE (can be WATCH with note) |

**Implementation:**
- Try to fetch earnings from Schwab API instruments endpoint
- If API returns earnings date: compare to expiration date
- If API returns None: mark as MANUAL_VERIFY
- If MANUAL_VERIFY: candidate max score = 90 (not 100)

---

### 5. Option-Chain Diagnostics (CRITICAL)

**Rule:** When no opportunities found, provide EXACT blocking reason.

**Required diagnostic output for each cloud-qualified ticker:**
```
Ticker: [SYMBOL]
Universe: [Primary Leveraged / Expanded Leveraged / Core]
Cloud Score: [X]/3 ✓
Eligible Expirations Reviewed: [N] (25-35 DTE)
Eligible Strikes Under Tier Limit: [list strikes]
Best Available Put by Return:
  Strike: $[price]
  Return: [X]%
  IV: [X]%
  Blocking Factor: [EXACT REASON]
```

**Blocking reasons (choose one):**
- IV below 40% threshold
- Return on collateral below 2%
- Bid/ask spread too wide (> 10% of mark)
- Open interest or volume too low
- No eligible 25-35 DTE expiration
- Collateral above tier limit (strike too high)
- Breakeven cushion insufficient (< 0%)
- Earnings unavailable (MANUAL_VERIFY)
- Earnings before expiration
- No OTM puts available

---

### 6. Top Candidate Detail (REQUIRED)

**For each top candidate, show:**

```
[Rank]. [TICKER] ([Universe])
   Cloud Score: [X]/3 ([Fast/Medium/Slow status])
   Price: $[price] | Change: [X]% | Volume: [N]
   Classification: [LEVERAGED_*/CORE_* label]
   
   Expirations Reviewed:
   - [Date] ([DTE] DTE): [N] strikes evaluated
   - [Date] ([DTE] DTE): [N] strikes evaluated
   
   Eligible Strikes (collateral ≤ tier limit):
   - $[strike]: mark=$[price], IV=[X]%, return=[X]%
   - $[strike]: mark=$[price], IV=[X]%, return=[X]%
   
   Best Opportunity:
   Strike: $[price] | Return: [X]% | IV: [X]%
   OR
   Blocking Factor: [EXACT REASON]
```

---

### 7. Read-Only Mode (NON-NEGOTIABLE)

- [ ] NO trades placed via API
- [ ] NO orders submitted
- [ ] NO margin used
- [ ] NO naked options
- [ ] Human confirmation required for all trades

---

## 🎯 TEST PROCEDURE

### 9:45 AM ET: Start Test
```powershell
cd C:\Users\Ionai48q\.openclaw-work\workspaces\work\skills\aristotle-capital-flywheel
python daily_scan_v3.py
```

### Verify Step-by-Step:
1. [ ] Persistent corrections loaded (10 checks including v3.0)
2. [ ] Quotes fetched for all 54 tickers across 3 universes
3. [ ] EMA cloud calculated for each ticker (not 0/54)
4. [ ] Cloud scores: 0-3 with Fast/Medium/Slow status
5. [ ] Hard filter applied: cloud < 2 = REJECTED
6. [ ] Three-universe structure active
7. [ ] Leveraged products NOT auto-rejected
8. [ ] LEVERAGED_* / CORE_* classification labels used
9. [ ] Option chains fetched for top candidates
10. [ ] Diagnostics show exact blocking reasons
11. [ ] Score breakdown includes cloud points
12. [ ] Earnings status: 10/10, 0/10, or MANUAL_VERIFY
13. [ ] Full rejection list with categories
14. [ ] Six-section report format
15. [ ] No trades placed
16. [ ] Report saved to `reports/` folder

### 10:15 AM ET: Complete Test

---

## ✅ SUCCESS CRITERIA

### Must Pass (ALL Required):
1. [ ] Valid weekly cloud scores for all 54 tickers
2. [ ] Three-universe structure correctly applied
3. [ ] Leveraged products NOT auto-rejected
4. [ ] LEVERAGED_* / CORE_* classification labels used
5. [ ] Clear earnings status (not just 0/10)
6. [ ] Exact option-chain blocking reasons
7. [ ] Top candidates show full diagnostics
8. [ ] Six-section report format
9. [ ] No hard rule violations
10. [ ] Read-only mode confirmed

### Should Pass:
11. [ ] At least 1 candidate with score ≥ 70
12. [ ] At least 1 candidate with opportunities
13. [ ] Earnings data available for some tickers

### Nice to Have:
14. [ ] At least 1 TRADE_REVIEW candidate (score ≥ 85)
15. [ ] Multiple expiration dates with strikes
16. [ ] IV data populated

---

## 🚀 POST-TEST ACTIONS

### If Test Passes (All Must-Pass criteria met):
1. [ ] Document results
2. [ ] Commit report to git
3. [ ] Cron job already scheduled (9:45 AM ET weekdays)
4. [ ] Update status: PRODUCTION READY v3.0

### If Test Fails:
1. [ ] Document failure reason
2. [ ] Fix issue
3. [ ] Re-test before next scheduled run

---

## 📁 FILES READY

| File | Status | Version |
|------|--------|---------|
| `daily_scan_v3.py` | ✅ Ready | v3.0 |
| `schwab_bridge.py` | ✅ EMA + quotes working | v1.2 |
| `token_refresh.py` | ✅ Auto-refresh | v1.0 |
| `ARISTOTLE_INSTRUCTIONS.md` | ✅ Master doc | v3.0 |
| `SKILL.md` | ✅ Skill definition | v3.0 |
| `CAPITAL_FLYWHEEL_PLAN.txt` | ✅ Trading plan | v3.0 |
| `CHANGELOG.md` | ✅ Version history | v3.0 |
| `LIVE_MARKET_TEST_PLAN.md` | ✅ Test plan | v3.0 |

---

## ⚠️ REMINDERS

- **Cron job scheduled:** 9:45 AM ET weekdays
- **Test must be during market hours (9:30 AM - 4:00 PM ET)**
- **All trades remain manual in thinkorswim paperMoney**
- **EMA cloud is THE core filter — no exceptions**
- **Leveraged products are central to the strategy — do NOT auto-reject**

---

**Ready for live-market test!** 🚀
