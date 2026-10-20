// Shape of the payload produced by reconcile.py and stored in snapshots.payload

export interface Position {
  account_mask: string;
  underlying: string;
  type: "PUT" | "CALL";
  strike: number;
  expiry: string | null;
  dte: number | null;
  contracts: number;
  entry_premium: number | null;
  current_mark: number | null;
  pct_to_50_target: number | null;
  collateral: number;
  tier: "CORE" | "FLEX" | "OTHER";
  has_gtc_exit: boolean;
}

export interface Account {
  mask: string;
  type: string;
  net_liq: number;
  cash: number | null;
  committed_collateral: number;
  concentration_pct: number | null;
}

export interface StockPosition {
  account_mask: string;
  symbol: string;
  shares: number;
  avg_price: number | null;        // Schwab raw (assignment strike)
  effective_basis?: number | null; // strike - assigned-put premium
  current_price: number | null;
  market_value: number;
  unrealized_pl: number | null;
  tier: "CORE" | "FLEX" | "OTHER";
}

export interface ProgramRecovery {
  program_cost: number;
  provider: string;
  net_premium_collected: number;
  recovered_pct: number | null;
  to_break_even: number;
  paid_off: boolean;
  since: string | null;
  as_of: string;
}

export interface Guardrail {
  check: string;
  status: "PASS" | "WARN" | "FAIL";
  detail: string;
}

export interface ActionItem {
  priority: string;
  message: string;
}

export interface Pacing {
  basis: number;
  basis_source: string;
  target_pct: number;
  target_dollars: number;
  mtd_premium: number;
  mtd_txn_count: number;
  pct_of_target: number;
  day: number;
  days_in_month: number;
  expected_by_now: number;
  pace_status: "AHEAD" | "ON PACE" | "BEHIND";
  gap_dollars: number;
  open_credit_in_play: number;
  avg_credit_per_contract: number;
  contracts_to_close_gap: number;
  deployed_pct: number;
  deploy_target_pct: number;
  idle_deployable: number;
  as_of: string;
}

// pullback.py — gameplan.assignment_playbook + correction_protocol (2026-10-20)
export interface PullbackDrawdown {
  status: "OK" | "UNAVAILABLE";
  price?: number;
  high_52w?: number;
  drawdown_pct?: number;
  bucket?: "none" | "dip" | "correction" | "bear";
  bucket_frequency?: string | null;
  core_only?: boolean;
}

export interface MacroRegime {
  status: "OK" | "UNAVAILABLE";
  regime?: "CLEAR" | "WATCH" | "CAUTION";
  fed_funds?: number;
  fed_funds_12m_change?: number;
  rate_rising?: boolean;
  unemployment?: number;
  unemployment_3m_vs_12m_low?: number;
  unemployment_rising?: boolean;
}

export interface AssignmentCheck {
  ticker: string;
  itm_puts: string[];
  shares_if_assigned: number;
  cost_if_assigned: number;
  ticker_exposure: number;
  ticker_cap: number;
  room_for_puts: number;
  status: "LAYER_OK" | "NO_BOTTOM_LAYER" | "OVER_CAP" | "INCOME_FIRST_ONLY";
}

export interface CoveredCallTiming {
  ticker: string;
  account: string;
  shares: number;
  uncovered_shares: number;
  path: "income_first" | "balanced" | "hold_for_upside";
  action: "SELL_CALLS_NOW" | "WAIT" | "COVERED";
  why: string;
  price: number | null;
  day_change_pct: number | null;
  rsi_daily: number | null;
  adjusted_basis: number | null;
  basis_gap: number | null;
  months_to_breakeven_at_10pct: number | null;
}

export interface Pullback {
  status?: "UNAVAILABLE";
  as_of?: string;
  drawdown?: PullbackDrawdown;
  macro?: MacroRegime;
  assignment_check?: AssignmentCheck[];
  covered_calls?: CoveredCallTiming[];
}

export interface SnapshotPayload {
  snapshot: {
    as_of: string;
    combined_net_liq: number;
    combined_collateral: number;
    deployed_pct: number;
    cash_reserve_pct: number;
    accounts: Account[];
    open_options: Position[];
    stock_positions?: StockPosition[];
    ticker_exposure: Record<string, number>;
  };
  guardrails: Guardrail[];
  action_items: ActionItem[];
  pacing?: Pacing;
  program_recovery?: ProgramRecovery;
  pullback?: Pullback;
}

export interface SnapshotRow {
  id: number;
  created_at: string;
  as_of: string;
  combined_net_liq: number;
  deployed_pct: number;
  cash_reserve_pct: number;
  fail_count: number;
  warn_count: number;
  action_count: number;
  payload: SnapshotPayload;
}
