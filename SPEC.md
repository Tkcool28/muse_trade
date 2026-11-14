# Poly LLM — paper trading spec (v1, 2026-10-14)

Paper-only Polymarket system. Muse runs it; Terry watches the dashboard.
Comparison target: Terry's Polycopy (mechanical copy bot, $200 paper).

## 1. Bankroll
- $200 start, **no replenishment ever**. Two sub-books: copy $100, discretionary $100.
- Sweep account starts $0. After every settlement pass: while
  `(realized_pnl − swept_total) ≥ $25`: move $25 cash → sweep. (Mirrors Polycopy.)
- Dynamic reallocation (monthly, Muse's call): shift $25 from the worse half to
  the better half on realized P&L, never dropping either half below $50.
  This is the "manage the money better than a bot" part.

## 2. Fees — fully incorporated, read live
- Taker fee per fill: `fee = shares × rate × p × (1−p)` (peaks at 50¢).
  `rate` read LIVE from each market's Gamma `feeSchedule`
  (feeType like `sports_fees_v3`); fallback table: crypto 0.07, sports 0.05,
  economics/culture/weather/other 0.05, politics/finance/tech/mentions 0.04,
  geopolitics/world-events 0.
- Makers pay 0 — but v1 paper fills are always taker (market orders).
- No fee on winnings at redemption (verified Oct 2026: fees are per-trade).
- Gas: $0.005 flat per fill (real range $0.001–0.01 on Polygon).
- Fill price: executable price from CLOB `/price?side=BUY|SELL` at decision time.
- Copy fills include real detection latency: we fill at the price observed when
  the hook first sees the wallet's trade. Never backfilled.

## 3. Copy book (mechanical half)
- Wallets: independently evaluated shortlist (eval_wallets.py). Gates:
  ≥8 trades/30d, median hold ≤21d, last trade ≤5d ago, realized closes exist
  (REDEEM events). Bank tie-up protected by the 21-day time stop plus the
  30-day resolution cap on entries (below).
- Mirror BUYs only (direction, not size). Size: $5/trade (2.5% of bank).
- Skip if: price moved >4% adverse vs wallet's fill; best-side depth < 3× our
  size; copy-book tied-up ≥ $60; token has no CLOB book; wallet trade older
  than 6h when first seen (stale); market resolves >30 days out
  (`long_resolution`, added 2026-10-23 on Terry's call — "one month tops").
- No copy position lives longer than 21 days (time stop, sold at market).
  (History: an endDate-based filter was removed 2026-10-14 because Gamma
  endDate then read 2027-01-01 for everything. The Oct 20-23 shadow log shows
  endDate is differentiated now, so the 30-day entry filter is back — but it
  fails OPEN on a missing/unparseable date, so a bad field can never block
  the whole book again; the time stop remains the hard backstop. The eval
  gates already proved these wallets hold ~0.1–4 days.)
- Floor salvage stop (added 2026-11-14, Terry's call): a copy position is
  sold the first run its mark prints below 0.15. Backtest on all 54 settled
  copy positions (CLOB price history, real exit fees, train <Oct 26 vs
  holdout ≥Oct 26): +$14.98 / +$10.86, +$25.84 total. A sports carve-out was
  tested and rejected — it gave back $10.90 of salvage and saved zero
  winners. Relative 50%-of-entry stops were ~breakeven and are not used.
- Mirror SELLs by closing our matching position; REDEEM/resolution settles it.
- **Exits bypass the halt guard** (2026-11-14): sells (time stop, floor
  stop, wallet-exit mirror) are never blocked by the halt or the daily loss
  brake — the guard exists to limit NEW risk, and blocking a sell traps the
  position, which is what froze all exits Oct 31–Nov 14. Buys still respect
  the halt, brake, and caps.
- Wallet dropped after ≥10 copied trades with copied realized P&L < 0.

## 4. Discretionary book (Muse's half)
- Hunting ground only: (a) new markets (<12h old), (b) niche (<$10k 7d volume),
  (c) cross-market structure gaps (>6pp between logically linked outcomes).
  Never general reasoning on well-covered books — that's the efficient part.
- $5/trade max, ≤5 concurrent. Every trade carries a 1–2 sentence `reason`
  in the ledger. No averaging down.
- Decisions made by Muse in 2× daily scheduled sessions from candidates.json.

## 5. Risk / kill criteria
- Per-trade cap $5 (2.5% of bank). Bank-wide tied-up cap $120 (60%).
- Drawdown halt: equity < halt line (−20% from baseline) → no new entries,
  notify Terry. Baseline $200 / line $160 at start; tripped Oct 31, 2026 at
  $159.40. **Restarted 2026-11-14 on Terry's call: baseline $136.25, new line
  $109.00** (same −20% chance from where the book is). The restart run's
  time stop closed Hyperliquid No (+$2.35) and BTC $90k Yes (−$4.57); the
  West Indies position could NOT be sold — its CLOB token 404s (market
  resolved 0.5/0.5, no live book) — it stays open pending a split-settle
  fix, which Terry has not authorized.
- 60-day review: need ≥40 closed trades; net realized P&L ≤ $0 kills the
  losing half (keeps a green half); both ≤ $0 = full stop + post-mortem.
- Daily loss brake: −$15 realized in a day → no new entries until next day.

## 6. Settlement
- Hook checks open positions each run: Gamma market by condition → resolved?
  Winners redeem $1.00/share, losers $0. Losers/winners both close, realized
  P&L booked net of all fees+gas paid on the position.
- **Split resolution (added 2026-11-14, Terry's call):** a market that
  resolves to a fractional payout (e.g. outcomePrices `["0.5","0.5"]` on a
  drawn series) settles at that price per share for our side. Without this
  the position never settles — and once the market closes CLOB delists the
  token (404 on /price), so it can't be sold either. First use: West Indies
  T20 settled SPLIT @ 0.50 the same day (+$3.62 proceeds, −$1.46 realized).
  Only 2-outcome markets; a clean 1/0 is a win, never a split.

## 7. Dashboard
- `dashboard.html`, regenerated every hook run. Phone-first, dark.
- Bank, free cash, tied-up, sweep account, total equity, realized/unrealized
  P&L, fees paid; per-book P&L; wallets (copied trades, P&L, win rate, status);
  open positions; recent trades with reasons; kill-criteria status.

## 9. Shadow signal log (added 2026-10-20, Terry's call)
- Every fresh wallet BUY the copy loop evaluates is appended to
  `state/signals.jsonl` (`engine/shadow.py`): decision (`copied`/`skipped`),
  skip-reason category, and detection-time features (wallet price, our
  executable price, adverse %, fee rate, book depth, market id).
- Each run, resolved signals are graded: would-be P&L of a $5 taker copy at
  the detection price, held to settlement, real fee model. A skip is
  "correct" when copying would not have profited; the learner-facing
  reward is +would-be-P&L for copies, −would-be-P&L for skips.
- Signals whose price was never honestly observable (stale, no book,
  unmapped side, closed market) are logged `evaluable: false` and never
  graded — no invented prices.
- Grading cadence (fixed 2026-11-14, Terry's call): a still-unresolved
  signal is re-checked at most once per 6h (`state/shadow_checked.json`);
  the 30 checks/run rotate through the backlog oldest-first. Before the
  fix the grader re-checked the same 30 oldest unresolved signals every
  run, so grading sat at 244 for three weeks while ~8,600 signals waited.
- Purpose: the dataset a future condition-learner (bandit-style, per
  Terry's validation standard — shadow first, pre-declared rule,
  walk-forward, kill rule on top) trains on. Logging only; nothing in the
  trade path reads it yet. Summary: `python3 engine/shadow.py`.

## 8. Honesty notes
- $5 size ⇒ ~5% round-trip fee drag at 50¢ sports. The edge must clear that.
  This is the experiment's load-bearing fact, not a bug.
- Copy latency and spread are modeled pessimistically; paper should
  *understate*, never flatter.
