"""
Instruction Validator — Prevents hallucination and drift
Run this before generating any output to ensure compliance
"""

import json
import re
from datetime import datetime
from pathlib import Path

INSTRUCTIONS_FILE = Path(__file__).parent / "ARISTOTLE_INSTRUCTIONS.md"

# Hard rules that CANNOT be violated
HARD_RULES = {
    "no_live_trades": "NEVER place live or paper trades via API",
    "no_margin": "NEVER use margin",
    "no_naked_options": "NEVER sell naked/uncovered options",
    "no_universe_override": "NEVER trade outside approved universe without approval",
    "no_earnings_ignore": "NEVER ignore earnings risk",
    "no_limit_override": "NEVER exceed collateral limits",
    "no_fake_data": "NEVER make up data (quotes, IV, earnings, etc.)",
    "no_rule_changes": "NEVER change rules without human approval",
    "exit_50_percent": "ALWAYS include 50% profit exit order",
    "rejection_reasons": "ALWAYS provide rejection reasons",
}

# Approved universe
APPROVED_TICKERS = {
    "tier1": ["NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AVGO", "COST", "LLY", "AMD", "JPM", "UNH", "ORCL"],
    "tier2": ["SPY", "QQQ", "IWM", "SMH", "XLK", "XLF"],
    "tier3": ["TQQQ", "SOXL", "NVDL", "TSLL", "BITX"],
}

# Portfolio limits by phase
PHASE_LIMITS = {
    1: {  # Days 1-30
        "max_collateral_per_trade": 12500,
        "max_total_collateral": 50000,
        "max_single_ticker": 25000,
        "max_leveraged_etf": 12500,
        "min_cash_reserve": 0.70,
        "assignment_allowed": False,
    },
    2: {  # Days 31-60
        "max_collateral_per_trade": 18750,
        "max_total_collateral": 75000,
        "max_single_ticker": 37500,
        "max_leveraged_etf": 25000,
        "min_cash_reserve": 0.60,
        "assignment_allowed": True,
    },
    3: {  # Days 61-90
        "max_collateral_per_trade": 25000,
        "max_total_collateral": 100000,
        "max_single_ticker": 50000,
        "max_leveraged_etf": 37500,
        "min_cash_reserve": 0.50,
        "assignment_allowed": True,
    }
}


def validate_output(output_text: str, phase: int = 1) -> dict:
    """
    Validate agent output against hard rules
    Returns: {"valid": bool, "violations": list, "warnings": list}
    """
    violations = []
    warnings = []
    
    # Check for hard rule violations
    lower_output = output_text.lower()
    
    # Check for trade placement suggestions
    if any(phrase in lower_output for phrase in ["place the trade", "execute the trade", "submit order", "buy now", "sell now"]):
        violations.append("VIOLATION: Suggests placing trades — Agent is READ-ONLY")
    
    # Check for margin suggestions
    if "margin" in lower_output and "do not use" not in lower_output:
        violations.append("VIOLATION: Mentions margin without prohibition")
    
    # Check for naked options
    if "naked" in lower_output or "uncovered" in lower_output:
        violations.append("VIOLATION: Mentions naked/uncovered options")
    
    # Check for 50% exit orders
    if "trade candidate" in lower_output and "50%" not in lower_output:
        violations.append("VIOLATION: Trade candidate missing 50% exit order")
    
    # Check for rejection reasons
    if "rejected" in lower_output and "rejection reason" not in lower_output:
        # Check if rejection section has reasons
        reject_section = re.search(r'REJECTED\n-+\n(.*?)(?=\n-+|$)', output_text, re.DOTALL)
        if reject_section:
            lines = reject_section.group(1).strip().split('\n')
            for line in lines:
                if line.strip() and '|' not in line:
                    violations.append(f"VIOLATION: Rejection missing reason: {line}")
    
    # Check for made-up data indicators
    fake_indicators = ["approximately", "around", "estimated", "likely", "probably"]
    for indicator in fake_indicators:
        if indicator in lower_output:
            warnings.append(f"WARNING: Uses uncertain language '{indicator}' — verify data source")
    
    # Check for unverified claims
    if "i believe" in lower_output or "i think" in lower_output:
        warnings.append("WARNING: Uses subjective language — stick to data")
    
    # Check portfolio limits
    limits = PHASE_LIMITS.get(phase, PHASE_LIMITS[1])
    
    # Extract collateral amounts from trade candidates only
    # Pattern: "Collateral: $X" in candidate sections (not headers)
    candidate_sections = re.findall(r'\d+\.\s+\w+.*?Collateral:\s*\$?([\d,]+)', output_text, re.DOTALL)
    for match in candidate_sections:
        collateral = int(match.replace(',', ''))
        if collateral > limits["max_collateral_per_trade"]:
            violations.append(f"VIOLATION: Collateral ${collateral:,} exceeds limit ${limits['max_collateral_per_trade']:,}")
    
    # Check for approved tickers
    all_approved = APPROVED_TICKERS["tier1"] + APPROVED_TICKERS["tier2"] + APPROVED_TICKERS["tier3"]
    ticker_pattern = r'\b([A-Z]{1,5})\b'
    found_tickers = set(re.findall(ticker_pattern, output_text))
    for ticker in found_tickers:
        if ticker not in all_approved and ticker not in ["SPY", "QQQ", "VIX", "ETF", "DTE", "CSP", "CC", "IV"]:
            warnings.append(f"WARNING: Ticker {ticker} not in approved universe")
    
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "warnings": warnings
    }


def validate_candidate(candidate: dict, phase: int = 1) -> dict:
    """
    Validate a single trade candidate against all rules
    """
    violations = []
    warnings = []
    
    limits = PHASE_LIMITS.get(phase, PHASE_LIMITS[1])
    
    # Check ticker approval
    ticker = candidate.get("ticker", "")
    all_approved = APPROVED_TICKERS["tier1"] + APPROVED_TICKERS["tier2"] + APPROVED_TICKERS["tier3"]
    if ticker not in all_approved:
        violations.append(f"VIOLATION: Ticker {ticker} not in approved universe")
    
    # Check cloud score
    cloud_score = candidate.get("cloud_score", 0)
    if cloud_score < 2:
        violations.append(f"VIOLATION: Cloud score {cloud_score}/3 below minimum (2)")
    
    # Check market cap
    market_cap = candidate.get("market_cap", 0)
    if ticker in APPROVED_TICKERS["tier1"] and market_cap < 200:
        violations.append(f"VIOLATION: Market cap ${market_cap}B below $200B minimum")
    
    # Check IV
    iv = candidate.get("iv", 0)
    if iv < 40:
        warnings.append(f"WARNING: IV {iv}% below 40% threshold")
    if iv > 70:
        warnings.append(f"WARNING: IV {iv}% above 70% — HIGH RISK")
    
    # Check collateral
    collateral = candidate.get("collateral", 0)
    if collateral > limits["max_collateral_per_trade"]:
        violations.append(f"VIOLATION: Collateral ${collateral:,} exceeds ${limits['max_collateral_per_trade']:,} limit")
    
    # Check return
    return_pct = candidate.get("return_pct", 0)
    if return_pct < 2:
        warnings.append(f"WARNING: Return {return_pct}% below 2% minimum")
    
    # Check if earnings before expiration
    earnings_date = candidate.get("earnings_date")
    expiration = candidate.get("expiration")
    if earnings_date and expiration:
        try:
            earn_dt = datetime.strptime(earnings_date, "%Y-%m-%d")
            exp_dt = datetime.strptime(expiration, "%Y-%m-%d")
            if earn_dt <= exp_dt:
                violations.append(f"VIOLATION: Earnings {earnings_date} before expiration {expiration}")
        except:
            warnings.append("WARNING: Could not parse earnings/expiration dates")
    
    # Check exit order
    if "exit_order" not in candidate:
        violations.append("VIOLATION: Missing 50% profit exit order")
    
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "score": candidate.get("score", 0)
    }


def print_validation_report(result: dict):
    """Print validation results"""
    print("\n" + "="*60)
    print("VALIDATION REPORT")
    print("="*60)
    
    if result["valid"]:
        print("[PASS] Output is valid — no hard rule violations")
    else:
        print("[FAIL] Hard rule violations detected!")
    
    if result["violations"]:
        print(f"\nVIOLATIONS ({len(result['violations'])}):")
        for v in result["violations"]:
            print(f"  - {v}")
    
    if result["warnings"]:
        print(f"\nWARNINGS ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"  - {w}")
    
    if not result["violations"] and not result["warnings"]:
        print("\nClean — no issues found")
    
    print("="*60)


if __name__ == "__main__":
    # Test with sample output
    sample = """
    CAPITAL FLYWHEEL DAILY REPORT
    
    TOP TRADE CANDIDATES
    
    1. NVDA
       Decision: TRADE
       Score: 92/100
       Collateral: $15,000
       Exit Order: Buy to close at 50% of credit
       
    REJECTED
    - TSLA | Rejection reason: Earnings before expiration
    """
    
    result = validate_output(sample, phase=1)
    print_validation_report(result)
