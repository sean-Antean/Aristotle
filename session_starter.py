"""
Aristotle Session Starter
Run this at the beginning of every session to load instructions
and prevent drift
"""

import sys
from pathlib import Path

INSTRUCTIONS_FILE = Path(__file__).parent / "ARISTOTLE_INSTRUCTIONS.md"
VALIDATOR_FILE = Path(__file__).parent / "instruction_validator.py"


def load_instructions():
    """Load and display key rules from instructions"""
    if not INSTRUCTIONS_FILE.exists():
        print("[ERROR] Instructions file not found!")
        return False
    
    with open(INSTRUCTIONS_FILE, encoding='utf-8') as f:
        content = f.read()
    
    print("="*60)
    print("ARISTOTLE CAPITAL FLYWHEEL — SESSION START")
    print("="*60)
    print(f"Instructions: {INSTRUCTIONS_FILE}")
    print(f"Version: 1.0.0")
    print(f"Status: ACTIVE")
    print(f"Enforcement: STRICT")
    print("="*60)
    
    # Display critical rules
    print("\n[CRITICAL RULES — DO NOT VIOLATE]")
    print("-"*60)
    print("1. NEVER place live or paper trades via API")
    print("2. NEVER use margin")
    print("3. NEVER sell naked/uncovered options")
    print("4. NEVER make up data (quotes, IV, earnings, etc.)")
    print("5. ALWAYS include 50% profit exit order")
    print("6. ALWAYS provide rejection reasons")
    print("7. NEVER exceed collateral limits")
    print("8. NEVER ignore earnings risk")
    print("-"*60)
    
    # Display current phase
    print("\n[CURRENT PHASE: 1 — Conservative]")
    print("- Max collateral per trade: $12,500")
    print("- Max total open collateral: $50,000")
    print("- Min cash reserve: 70%")
    print("- Assignment trades: NOT ALLOWED")
    print("-"*60)
    
    # Display approved universe
    print("\n[APPROVED UNIVERSE]")
    print("Tier 1 (Mega-cap): NVDA, MSFT, AAPL, AMZN, GOOGL, META, TSLA, NFLX, AVGO, COST, LLY, AMD, JPM, UNH, ORCL")
    print("Tier 2 (ETFs): SPY, QQQ, IWM, SMH, XLK, XLF")
    print("Tier 3 (Leveraged): TQQQ, SOXL, NVDL, TSLL, BITX [PAPER TEST ONLY]")
    print("-"*60)
    
    return True


def verify_validator():
    """Check that validator is available"""
    if VALIDATOR_FILE.exists():
        print("\n[VALIDATOR] instruction_validator.py — READY")
        return True
    else:
        print("\n[WARNING] Validator not found — drift detection disabled")
        return False


def main():
    print("\n")
    
    if not load_instructions():
        print("\n[CRITICAL] Cannot start session without instructions!")
        sys.exit(1)
    
    verify_validator()
    
    print("\n" + "="*60)
    print("SESSION READY")
    print("="*60)
    print("\nNext steps:")
    print("1. Run token_refresh.py to ensure API access")
    print("2. Run daily_scan_v3.py (v3.0 — has strike-level collateral filtering)")
    print("   DO NOT use daily_scan_v1_DEPRECATED.py — it has the old hard price cap bug")
    print("3. Validate all outputs with instruction_validator.py")
    print("\nRemember: READ-ONLY. Human executes all trades.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
