# muse_trade — Poly LLM paper trading

Paper-only Polymarket trading system run by Muse, racing Terry's mechanical
Polycopy bot on identical terms: **$200 fixed bankroll, no replenishment,
real fees modeled on every fill.**

📊 **Live dashboard:** https://tkcool28.github.io/muse_trade/

## The bet
Two halves, $100 each:
- **Copy book** — mirrors 4 evaluated smart wallets (direction only, our sizing).
- **Discretionary book** — Muse's own trades, each with a written reason.

Question: does LLM discretion beat cold mechanical copying after fees?

## Money rules
- $200 start, **never replenished**. $5/trade cap, bank tied-up cap $120.
- Profits swept to a separate sweep account at $25 intervals.
- Kill criteria: −20% drawdown halts everything; 60-day review needs net P&L > 0.

## Fees (fully incorporated, read live)
- Taker fee per fill: `shares × rate × p × (1−p)`, rate read live from each
  market's `feeSchedule` (crypto .07 / sports .05 / politics-finance-tech .04 /
  geopolitics 0). Makers pay 0. No fee on winnings. +$0.005 gas/fill.
- Fills at the executable book price; copy fills include real detection latency.

## Layout
- `engine/` — the system: `pm_api.py` (public read-only APIs), `fees.py`,
  `ledger.py` (cash/positions/sweeps/P&L), `copy.py`, `settle.py`,
  `scanner.py` (new/niche/cross-market candidates), `dashboard.py`,
  `run.py` (15-min loop entry), `trade.py` (discretionary CLI),
  `eval_wallets.py` (wallet screening).
- `tests/` — pytest suite for the money math (fees, ledger). No network.
- `docs/dashboard.html` — generated phone-first dashboard (GitHub Pages).
- `state/` — decision records: evaluated wallet roster (`wallets.json`,
  `wallet_eval.json`). Live ledger state is NOT committed.

## How it runs
A 15-minute loop (settle → copy scan → candidate scan → dashboard regen) plus
twice-daily discretionary sessions where Muse reviews candidates and trades
with written reasons. Paper only — no keys, no real orders, ever.

## Spec
See [SPEC.md](SPEC.md).
