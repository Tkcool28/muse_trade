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
  (REDEEM events). Bank tie-up protected by the 21-day time stop, not the
  (meaningless) endDate field.
- Mirror BUYs only (direction, not size). Size: $5/trade (2.5% of bank).
- Skip if: price moved >4% adverse vs wallet's fill; best-side depth < 3× our
  size; copy-book tied-up ≥ $60; token has no CLOB book; wallet trade older
  than 6h when first seen (stale).
- No copy position lives longer than 21 days (time stop, sold at market).
  (The market `endDate` field is a placeholder — everything reads 2027-01-01,
  even tonight's games — so duration is enforced by the time stop, not endDate.
  The eval gates already proved these wallets hold ~0.1–4 days.)
- Mirror SELLs by closing our matching position; REDEEM/resolution settles it.
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
- Drawdown halt: equity < $160 (−20%) → no new entries, notify Terry.
- 60-day review: need ≥40 closed trades; net realized P&L ≤ $0 kills the
  losing half (keeps a green half); both ≤ $0 = full stop + post-mortem.
- Daily loss brake: −$15 realized in a day → no new entries until next day.

## 6. Settlement
- Hook checks open positions each run: Gamma market by condition → resolved?
  Winners redeem $1.00/share, losers $0. Losers/winners both close, realized
  P&L booked net of all fees+gas paid on the position.

## 7. Dashboard
- `dashboard.html`, regenerated every hook run. Phone-first, dark.
- Bank, free cash, tied-up, sweep account, total equity, realized/unrealized
  P&L, fees paid; per-book P&L; wallets (copied trades, P&L, win rate, status);
  open positions; recent trades with reasons; kill-criteria status.

## 8. Honesty notes
- $5 size ⇒ ~5% round-trip fee drag at 50¢ sports. The edge must clear that.
  This is the experiment's load-bearing fact, not a bug.
- Copy latency and spread are modeled pessimistically; paper should
  *understate*, never flatter.
