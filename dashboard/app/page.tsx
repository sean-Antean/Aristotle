import { getServerClient } from "@/lib/supabase";
import type { SnapshotRow, Guardrail, Position, ActionItem, StockPosition, Pullback } from "@/lib/types";
import RefreshBar from "./RefreshBar";

// On-demand only: read the latest snapshot fresh on each visit, never poll in the
// background. Data is refreshed when you run `python reconcile.py --push` locally.
export const dynamic = "force-dynamic";
export const revalidate = 0;

async function getLatest(): Promise<{ row?: SnapshotRow; error?: string }> {
  try {
    const supabase = getServerClient();
    const { data, error } = await supabase
      .from("snapshots")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error) return { error: error.message };
    if (!data) return { error: "No snapshots yet. Run: python reconcile.py --push" };
    return { row: data as SnapshotRow };
  } catch (e: any) {
    return { error: e?.message ?? "Unknown error" };
  }
}

const pct = (n: number | null | undefined, d = 1) =>
  n === null || n === undefined ? "—" : `${(n * 100).toFixed(d)}%`;
const money = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `$${Math.round(n).toLocaleString()}`;

function StatusDot({ status }: { status: Guardrail["status"] }) {
  return <span className={`dot dot-${status.toLowerCase()}`} title={status} />;
}

const STATUS_PILL: Record<string, string> = {
  LAYER_OK: "pill-ok", NO_BOTTOM_LAYER: "pill-action", OVER_CAP: "pill-do_now", INCOME_FIRST_ONLY: "pill-watch",
  SELL_CALLS_NOW: "pill-ok", WAIT: "pill-watch", COVERED: "pill-ok",
  CLEAR: "pill-ok", WATCH: "pill-action", CAUTION: "pill-do_now",
};
const STATUS_TEXT: Record<string, string> = {
  LAYER_OK: "Layer OK", NO_BOTTOM_LAYER: "No room to add", OVER_CAP: "Over cap", INCOME_FIRST_ONLY: "Income First only",
  SELL_CALLS_NOW: "Sell calls now", WAIT: "Wait", COVERED: "Covered",
};
const PATH_TEXT: Record<string, string> = {
  income_first: "Income First", balanced: "Balanced", hold_for_upside: "Hold for Upside",
};

// Pullback & Assignment Playbook (mentor's Sandwich Method + Pullback Program, within Flywheel caps)
function PullbackCard({ p }: { p: Pullback }) {
  if (p.status === "UNAVAILABLE") return null;
  const d = p.drawdown, m = p.macro;
  const checks = p.assignment_check ?? [];
  const calls = p.covered_calls ?? [];
  return (
    <>
      <h2>Pullback &amp; Assignment Playbook</h2>
      <p className="cashrule">
        Assignment is the middle of the wheel: pick a path, sell calls on top, add puts underneath only on red days and only within caps.
      </p>
      <section className="card">
        <div className="regime">
          <div>
            <span className="label">Market (QQQ vs 52-week high)</span>
            {d?.status === "OK" ? (
              <div>
                <strong className={d.bucket === "none" ? "text-pass" : "text-warn"}>
                  {d.drawdown_pct}% · {d.bucket === "none" ? "No pullback" : d.bucket?.toUpperCase()}
                </strong>
                {d.core_only && <> <span className="pill pill-action">Core-only entries</span></>}
                {d.bucket_frequency && <div className="sub muted">History: {d.bucket_frequency}</div>}
              </div>
            ) : <div className="muted">unavailable</div>}
          </div>
          <div>
            <span className="label">Macro regime (rates + unemployment)</span>
            {m?.status === "OK" ? (
              <div>
                <span className={`pill ${STATUS_PILL[m.regime ?? ""] ?? "pill-watch"}`}>{m.regime}</span>{" "}
                <span className="muted">
                  Fed funds {m.fed_funds}% ({(m.fed_funds_12m_change ?? 0) >= 0 ? "+" : ""}{m.fed_funds_12m_change} over 12m) ·
                  unemployment {m.unemployment}% ({(m.unemployment_3m_vs_12m_low ?? 0) >= 0 ? "+" : ""}{m.unemployment_3m_vs_12m_low} vs 12m low)
                </span>
              </div>
            ) : <div className="muted">unavailable</div>}
          </div>
        </div>
      </section>

      {checks.length > 0 && (
        <>
          <h3>If in-the-money puts are assigned</h3>
          <div className="card list">
            {checks.map((c, i) => (
              <div className="li" key={i}>
                <span className={`pill ${STATUS_PILL[c.status]}`}>{STATUS_TEXT[c.status]}</span>
                <span className="li-check" style={{ flex: 1 }}>
                  <strong>{c.ticker}</strong> · {c.itm_puts.join(", ")}
                </span>
                <span>{c.shares_if_assigned} sh · {money(c.cost_if_assigned)}</span>
                <span className={c.room_for_puts < 0 ? "text-fail" : "muted"}>
                  {c.status === "INCOME_FIRST_ONLY"
                    ? "no adds: decaying fund, sell calls right away if assigned"
                    : c.room_for_puts < 0 ? `${money(-c.room_for_puts)} over cap` : `${money(c.room_for_puts)} room to add`}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {calls.length > 0 && (
        <>
          <h3>Covered calls: when to sell (by path)</h3>
          <div className="card list">
            {calls.map((c, i) => (
              <div className="li" key={i}>
                <span className={`pill ${STATUS_PILL[c.action]}`}>{STATUS_TEXT[c.action]}</span>
                <span className="li-check" style={{ flex: 1 }}>
                  <strong>{c.ticker}</strong> · {c.shares} sh · {PATH_TEXT[c.path]} <span className="muted">— {c.why}</span>
                </span>
                {c.adjusted_basis != null && c.price != null && (
                  <span className="muted">
                    basis {money(c.adjusted_basis)} vs {money(c.price)}
                    {c.basis_gap != null && c.basis_gap > 0
                      ? ` · ~${c.months_to_breakeven_at_10pct} mo to break-even at 10%/mo`
                      : " · above basis"}
                  </span>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function cashState(cashPct: number): string {
  const c = cashPct * 100;
  if (c > 70) return "Very cash-heavy → A+, A, qualified B";
  if (c >= 50) return "Target / moderate → A+ and A";
  if (c >= 30) return "Aggressively deployed → A+ only";
  return "BELOW HARD RESERVE → no new entries";
}

export default async function Page() {
  const { row, error } = await getLatest();

  if (!row) {
    return (
      <main className="wrap">
        <header className="head">
          <h1>Aristotle — Live Reconciliation</h1>
          <span className="badge">Advisory only</span>
        </header>
        <div className="card empty">
          <p>No data to show yet.</p>
          <p className="muted">{error}</p>
          <pre>python reconcile.py --push</pre>
        </div>
      </main>
    );
  }

  const s = row.payload.snapshot;
  const guards = row.payload.guardrails ?? [];
  const actions = row.payload.action_items ?? [];
  const fails = guards.filter((g) => g.status === "FAIL");
  const order = { FAIL: 0, WARN: 1, PASS: 2 } as const;
  const sortedGuards = [...guards].sort((a, b) => order[a.status] - order[b.status]);
  const prio = { DO_NOW: 0, ACTION: 1, WATCH: 2 } as const;
  const sortedActions = [...actions].sort(
    (a, b) => (prio[a.priority as keyof typeof prio] ?? 3) - (prio[b.priority as keyof typeof prio] ?? 3)
  );

  // TOS-style: cost basis = credit you agreed to collect; market value = current
  // value (premium ± how far it's moved); P/L = the difference (amount up/down).
  const collected = (p: Position) => (p.entry_premium ?? 0) * 100 * p.contracts;
  const mktValue = (p: Position) =>
    p.current_mark != null ? p.current_mark * 100 * p.contracts : null;
  const pnl = (p: Position) => {
    const mv = mktValue(p);
    return mv != null ? collected(p) - mv : null;
  };
  const shortPuts = s.open_options.filter((p) => p.type === "PUT");
  const shortCalls = s.open_options.filter((p) => p.type === "CALL");
  const stockPositions: StockPosition[] = s.stock_positions ?? [];
  const program = row.payload.program_recovery;
  const premiumCollected = shortPuts.reduce((sum, p) => sum + collected(p), 0);
  const totCollected = shortPuts.reduce((sum, p) => sum + collected(p), 0);
  const totMkt = shortPuts.reduce((sum, p) => sum + (mktValue(p) ?? 0), 0);
  const totPnl = totCollected - totMkt;

  // Group open premium by expiration month (helps pace the 5% monthly target)
  const fmtExp = (d: string | null) =>
    d ? new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
  const fmtMonth = (m: string) =>
    new Date(m + "-01T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const byMonth: Record<string, { collected: number; mkt: number; count: number }> = {};
  for (const p of shortPuts) {
    if (!p.expiry) continue;
    const m = p.expiry.slice(0, 7);
    if (!byMonth[m]) byMonth[m] = { collected: 0, mkt: 0, count: 0 };
    byMonth[m].collected += collected(p);
    byMonth[m].mkt += mktValue(p) ?? 0;
    byMonth[m].count += 1;
  }
  const months = Object.keys(byMonth).sort();

  const pacing = row.payload.pacing;
  const paceClass = (st?: string) =>
    st === "AHEAD" ? "text-pass" : st === "ON PACE" ? "text-pass" : "text-warn";

  return (
    <main className="wrap">
      <header className="head">
        <div>
          <h1>Aristotle — Live Reconciliation</h1>
          <p className="muted">
            As of {s.as_of} · {row.payload.snapshot.accounts.length} accounts ·{" "}
            {fails.length > 0 ? (
              <span className="text-fail">{fails.length} guardrail breach{fails.length > 1 ? "es" : ""}</span>
            ) : (
              <span className="text-pass">all guardrails pass</span>
            )}
          </p>
        </div>
        <div className="head-right">
          <span className="badge">Advisory only</span>
          <RefreshBar createdAt={row.created_at} />
        </div>
      </header>

      {/* Top stats */}
      <section className="stats">
        <div className="card stat">
          <span className="label">Combined Net Liq</span>
          <span className="value">{money(s.combined_net_liq)}</span>
        </div>
        <div className="card stat">
          <span className="label">Deployed</span>
          <span className="value">{pct(s.deployed_pct)}</span>
          <span className="sub">{money(s.combined_collateral)} collateral · max 70%</span>
        </div>
        <div className="card stat">
          <span className="label">Cash Reserve</span>
          <span className="value">{pct(s.cash_reserve_pct)}</span>
          <span className="sub">target 50% · floor 30%</span>
        </div>
        <div className="card stat">
          <span className="label">Open Put Credit</span>
          <span className="value text-pass">{money(premiumCollected)}</span>
          <span className="sub">on the books now · {shortPuts.length} open put{shortPuts.length === 1 ? "" : "s"}</span>
        </div>
      </section>
      <p className="cashrule">{cashState(s.cash_reserve_pct)}</p>

      {row.payload.pullback && <PullbackCard p={row.payload.pullback} />}

      {/* 5% monthly pace + deployment */}
      {pacing && (
        <section className="card pace">
          <div className="pace-head">
            <h2 style={{ margin: 0 }}>5% Monthly Pace</h2>
            <span className={`pace-status ${paceClass(pacing.pace_status)}`}>
              {pacing.pace_status} · day {pacing.day}/{pacing.days_in_month}
            </span>
          </div>
          <div className="pacebar">
            <span
              className="pacebar-fill"
              style={{ width: `${Math.min(100, Math.max(0, pacing.pct_of_target * 100))}%` }}
            />
            <span
              className="pacebar-marker"
              style={{ left: `${Math.min(100, (pacing.day / pacing.days_in_month) * 100)}%` }}
              title={`Expected by today: ${money(pacing.expected_by_now)}`}
            />
          </div>
          <div className="pace-grid">
            <div>
              <span className="label">Collected MTD</span>
              <span className="value text-pass">{money(pacing.mtd_premium)}</span>
              <span className="sub">{pct(pacing.pct_of_target, 0)} of {money(pacing.target_dollars)} target</span>
            </div>
            <div>
              <span className="label">{pacing.gap_dollars > 0 ? "Gap to target" : "Over target"}</span>
              <span className={`value ${pacing.gap_dollars > 0 ? "text-warn" : "text-pass"}`}>
                {money(Math.abs(pacing.gap_dollars))}
              </span>
              <span className="sub">
                {pacing.gap_dollars > 0
                  ? `≈ ${pacing.contracts_to_close_gap} more contracts (~${money(pacing.avg_credit_per_contract)}/ea)`
                  : "stretch toward 10%"}
              </span>
            </div>
            <div>
              <span className="label">Deployed</span>
              <span className="value">{pct(pacing.deployed_pct)}</span>
              <span className="sub">target ~{pct(pacing.deploy_target_pct, 0)}</span>
            </div>
            <div>
              <span className="label">Idle cash that could work</span>
              <span className="value text-warn">{money(pacing.idle_deployable)}</span>
              <span className="sub">deploy into qualified setups — don&apos;t force</span>
            </div>
          </div>
        </section>
      )}

      {/* Program break-even: has the MarketMoves tuition paid for itself? */}
      {program && (
        <section className="card pace">
          <div className="pace-head">
            <h2 style={{ margin: 0 }}>Program Break-Even</h2>
            <span className={`pace-status ${program.paid_off ? "text-pass" : "text-warn"}`}>
              {program.paid_off ? "PAID OFF ✓" : `${money(program.to_break_even)} to break even`}
            </span>
          </div>
          <div className="pacebar">
            <span
              className="pacebar-fill"
              style={{ width: `${Math.min(100, Math.max(0, program.recovered_pct ?? 0))}%` }}
            />
          </div>
          <div className="pace-grid">
            <div>
              <span className="label">Premium generated</span>
              <span className="value text-pass">{money(program.net_premium_collected)}</span>
              <span className="sub">
                {program.recovered_pct}% of the {money(program.program_cost)} {program.provider} cost
              </span>
            </div>
            <div>
              <span className="label">{program.paid_off ? "Profit past break-even" : "To break even"}</span>
              <span className={`value ${program.paid_off ? "text-pass" : "text-warn"}`}>
                {money(program.to_break_even)}
              </span>
              <span className="sub">since {program.since ?? "inception"}</span>
            </div>
            <div>
              <span className="label">Program cost</span>
              <span className="value">{money(program.program_cost)}</span>
              <span className="sub">{program.provider} · one-time tuition</span>
            </div>
          </div>
        </section>
      )}

      {/* Accounts */}
      <section className="grid2">
        {s.accounts.map((a) => (
          <div className="card" key={a.mask}>
            <div className="row-between">
              <strong>*{a.mask}</strong>
              <span className="muted">{a.type}</span>
            </div>
            <div className="row-between">
              <span className="muted">Net liq</span>
              <span>{money(a.net_liq)}</span>
            </div>
            <div className="row-between">
              <span className="muted">Concentration</span>
              <span className={a.concentration_pct && a.concentration_pct > 0.75 ? "text-fail" : ""}>
                {pct(a.concentration_pct)} <span className="muted">/ 75% cap</span>
              </span>
            </div>
          </div>
        ))}
      </section>

      {/* Positions (cash-secured puts) */}
      <h2>Open Cash-Secured Puts</h2>
      <div className="card table">
        <div className="tr th">
          <span>Acct</span><span>Tier</span><span>Ticker</span><span>Contract</span>
          <span>DTE</span><span>Cost basis</span><span>Mkt value</span><span>P/L</span><span>To 50%</span><span>GTC</span>
        </div>
        {shortPuts.length === 0 && <div className="tr"><span className="muted">No open put positions</span></div>}
        {shortPuts.map((p: Position, i) => (
          <div className="tr" key={i}>
            <span>*{p.account_mask}</span>
            <span className={`tier tier-${p.tier.toLowerCase()}`}>{p.tier}</span>
            <span><strong>{p.underlying}</strong></span>
            <span className="contract-cell">
              <span>{p.strike}{p.type === "PUT" ? "P" : "C"} ×{p.contracts}</span>
              <span className="contract-exp muted">{fmtExp(p.expiry)}</span>
            </span>
            <span>{p.dte ?? "—"}</span>
            <span className="text-pass">{money(collected(p))}</span>
            <span>{mktValue(p) != null ? money(mktValue(p)) : "—"}</span>
            <span className={pnl(p) != null ? (pnl(p)! >= 0 ? "text-pass" : "text-fail") : ""}>
              {pnl(p) != null ? money(pnl(p)) : "—"}
            </span>
            <span>
              <span className="bar"><span className="fill" style={{ width: `${Math.min(100, Math.max(0, (p.pct_to_50_target ?? 0) * 200))}%` }} /></span>
              <span className="barlabel">{pct(p.pct_to_50_target, 0)}</span>
            </span>
            <span className={p.has_gtc_exit ? "text-pass" : "text-fail"}>{p.has_gtc_exit ? "OK" : "NONE"}</span>
          </div>
        ))}
        {shortPuts.length > 0 && (
          <div className="tr tr-total">
            <span></span><span></span><span className="muted">Total</span><span></span><span></span>
            <span className="text-pass">{money(totCollected)}</span>
            <span>{money(totMkt)}</span>
            <span className={totPnl >= 0 ? "text-pass" : "text-fail"}>{money(totPnl)}</span>
            <span></span><span></span>
          </div>
        )}
      </div>

      {/* Assigned stock + covered calls — the other side of the wheel */}
      {(stockPositions.length > 0 || shortCalls.length > 0) && (
        <>
          <h2>Assigned Stock &amp; Covered Calls</h2>
          <p className="cashrule">The other side of the wheel — shares you were assigned, and the calls written against them.</p>
          <div className="card list">
            {stockPositions.map((st, i) => {
              const cc = shortCalls.find((c) => c.underlying === st.symbol);
              return (
                <div className="li" key={`s${i}`}>
                  <span className="li-check" style={{ flex: 1 }}>
                    <span className={`tier tier-${st.tier.toLowerCase()}`}>{st.tier}</span>{" "}
                    <strong>{st.symbol}</strong> · {st.shares} sh @ {money(st.effective_basis ?? st.avg_price)}/sh basis
                    {st.effective_basis != null && st.avg_price != null && st.effective_basis !== st.avg_price && (
                      <span className="muted"> (strike {money(st.avg_price)} − put premium)</span>
                    )}
                  </span>
                  <span>{money(st.market_value)} <span className="muted">value</span></span>
                  <span className={st.unrealized_pl != null && st.unrealized_pl >= 0 ? "text-pass" : "text-fail"}>
                    {money(st.unrealized_pl)} <span className="muted">unrl</span>
                  </span>
                  <span className="muted">
                    {cc ? `↳ ${cc.strike}C ${fmtExp(cc.expiry)} · ${money(collected(cc))}` : "uncovered"}
                  </span>
                </div>
              );
            })}
            {shortCalls
              .filter((c) => !stockPositions.some((st) => st.symbol === c.underlying))
              .map((c, i) => (
                <div className="li" key={`c${i}`}>
                  <span className="li-check" style={{ flex: 1 }}>
                    <span className={`tier tier-${c.tier.toLowerCase()}`}>{c.tier}</span>{" "}
                    <strong>{c.underlying}</strong> · covered call {c.strike}C {fmtExp(c.expiry)} ×{c.contracts}
                  </span>
                  <span>{money(collected(c))} <span className="muted">collected</span></span>
                </div>
              ))}
          </div>
        </>
      )}

      {/* Premium by expiration month */}
      {months.length > 0 && (
        <>
          <h2>Premium by expiration</h2>
          <p className="cashrule">How your open premium spreads across expirations — helps pace the 5% monthly target.</p>
          <div className="card list">
            {months.map((m) => (
              <div className="li" key={m}>
                <span className="li-check"><strong>{fmtMonth(m)}</strong> · {byMonth[m].count} put{byMonth[m].count === 1 ? "" : "s"}</span>
                <span><strong>{money(byMonth[m].mkt)}</strong> <span className="muted">still in play</span></span>
                <span className="muted">{money(byMonth[m].collected)} collected</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Guardrails */}
      <h2>Guardrail Audit</h2>
      <div className="card list">
        {sortedGuards.map((g, i) => (
          <div className="li" key={i}>
            <StatusDot status={g.status} />
            <span className="li-check">{g.check}</span>
            <span className="muted">{g.detail}</span>
          </div>
        ))}
      </div>

      {/* Actions */}
      <h2>Action Items</h2>
      <div className="card list">
        {sortedActions.length === 0 && <div className="li"><span className="muted">Nothing flagged — hold / wait for qualified setups.</span></div>}
        {sortedActions.map((a: ActionItem, i) => (
          <div className="li" key={i}>
            <span className={`pill pill-${a.priority.toLowerCase()}`}>{a.priority}</span>
            <span>{a.message}</span>
          </div>
        ))}
      </div>

      <footer className="foot">
        Aristotle stages tickets; you place every order. Not investment advice.<br />
        Refresh data with <code>python reconcile.py --push</code>.
      </footer>
    </main>
  );
}
