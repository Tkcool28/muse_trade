#!/usr/bin/env python3
"""Polymarket fee model (verified Oct 2026).

Taker fee per fill: fee = shares x rate x p x (1-p). Makers pay 0.
Rate is read LIVE from each market's Gamma feeSchedule; the table below is
only a fallback. No platform fee on winnings at redemption. Gas ~$0.005/fill.
"""
GAS_PER_FILL = 0.005

# Fallback rates by feeType prefix (live feeSchedule.rate wins when present).
FALLBACK_RATES = {
    "crypto": 0.07,
    "sports": 0.05,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "other": 0.05,
    "general": 0.05,
    "finance": 0.04,
    "politics": 0.04,
    "tech": 0.04,
    "mentions": 0.04,
    "geopolitics": 0.0,
    "world": 0.0,
}


def fee_rate_for(market):
    """Return (rate, source) for a Gamma market object."""
    fs = (market or {}).get("feeSchedule") or {}
    if fs.get("rate") is not None:
        return float(fs["rate"]), "live"
    if not (market or {}).get("feesEnabled", True):
        return 0.0, "disabled"
    ftype = str((market or {}).get("feeType") or "").lower()
    for prefix, rate in FALLBACK_RATES.items():
        if ftype.startswith(prefix):
            return rate, "fallback"
    return 0.05, "fallback-default"


def taker_fee(shares, price, market):
    """USDC taker fee for a fill of `shares` at price p (0..1)."""
    if shares <= 0 or not (0 < price < 1):
        return 0.0
    rate, _ = fee_rate_for(market)
    if rate <= 0:
        return 0.0
    return shares * rate * price * (1.0 - price)


def fill_cost(shares, price, market):
    """Total friction for one taker fill: fee + gas."""
    return taker_fee(shares, price, market) + GAS_PER_FILL
