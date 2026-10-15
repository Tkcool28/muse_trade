#!/usr/bin/env python3
"""Read-only Polymarket API clients: Gamma (markets), CLOB (books/prices),
Data API v2 (trades, activity, positions, leaderboard). No auth, no orders."""
import json
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
UA = {"User-Agent": "poly-llm-paper/1.0 (paper trading research)"}


def _get(url, params=None, timeout=15, tries=3):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - retry then raise
            last = e
            time.sleep(1 + i)
    raise RuntimeError(f"GET failed {url}: {last}")


# ---- Gamma ----
def gamma_markets(params):
    return _get(f"{GAMMA}/markets", params=params or {})


def gamma_market_by_id(mid):
    return _get(f"{GAMMA}/markets/{mid}")


def gamma_market_by_condition(condition_id):
    """Exact market lookup by condition_id.

    NOTE (2026-10-15): the Gamma /markets endpoint silently IGNORES the
    singular `condition_id` query param — it returns unrelated markets
    (e.g. "Xi Jinping out before 2027?" for an esports condition_id),
    which corrupted position metadata and nearly settled a position against
    the wrong market. The plural `condition_ids` is the working filter.
    """
    ms = gamma_markets({"condition_ids": str(condition_id), "limit": 1})
    return ms[0] if ms else None


def gamma_search(query, limit=10):
    return _get(f"{GAMMA}/public-search", {"q": query, "limit": limit})


# ---- CLOB ----
def clob_book(token_id):
    return _get(f"{CLOB}/book", {"token_id": str(token_id)})


def clob_midpoint(token_id):
    d = _get(f"{CLOB}/midpoint", {"token_id": str(token_id)})
    return float(d.get("mid") or 0)


def clob_price(token_id, side):
    """Executable taker price for side BUY|SELL."""
    d = _get(f"{CLOB}/price", {"token_id": str(token_id), "side": side})
    return float(d.get("price") or 0)


def book_depth_ok(token_id, side, need_shares, multiple=3.0):
    """True if the book's best-side size covers multiple× our need."""
    try:
        b = clob_book(token_id)
    except RuntimeError:
        return False
    lvl = b.get("asks") if side == "BUY" else b.get("bids")
    if not lvl:
        return False
    return float(lvl[0].get("size") or 0) >= need_shares * multiple


# ---- Data API v2 ----
def _paged(path, params, limit=200):
    out, cursor, params = [], dict(params or {}), dict(params or {})
    params["limit"] = min(limit, 500)
    while True:
        d = _get(f"{DATA}/{path}", params)
        rows = d.get("data") if isinstance(d, dict) else d
        if not rows:
            break
        out.extend(rows)
        if len(out) >= limit:
            break
        pg = d.get("pagination") if isinstance(d, dict) else None
        cursor = (pg or {}).get("cursor") or (pg or {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
    return out[:limit]


def data_trades(limit=100):
    return _paged("v2/trades", {}, limit)


def data_activity(user, limit=200):
    return _paged("v2/activity", {"user": user}, limit)


def data_positions(user, limit=200):
    return _paged("v2/positions", {"user": user}, limit)


def data_leaderboard(limit=50):
    d = _get(f"{DATA}/v2/leaderboard", {"limit": limit})
    return d.get("data", d) if isinstance(d, dict) else d
