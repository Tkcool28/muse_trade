#!/usr/bin/env python3
"""Render dashboard.html from state. Phone-first, dark, scannable sections."""
import json
import os
import time

ROOT = os.path.expanduser("~/workspace/poly-llm")
OUT = os.path.join(ROOT, "dashboard.html")


def _load(name, default):
    p = os.path.join(ROOT, "state", name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def _money(x):
    c = "pos" if x >= 0 else "neg"
    sign = "-" if x < 0 else ""
    return f'<span class="{c}">{sign}${abs(x):,.2f}</span>'


def render():
    s = _load("state.json", {})
    wstate = _load("wallets.json", {"wallets": []})
    pos = s.get("positions", {})
    cash, sweep = s.get("cash", 0), s.get("sweep", 0)
    tied = sum(p["cost"] for p in pos.values())
    un = 0.0
    for p in pos.values():
        lp = p.get("last_price") or p["avg_price"]
        un += (lp - p["avg_price"]) * p["shares"]
    eq = cash + tied + un
    rpnl = s.get("realized_pnl", 0)
    fees = s.get("fees_paid", 0)
    books = s.get("books", {"copy": {"realized": 0.0},
                            "disc": {"realized": 0.0}})
    copy_tied = sum(p["cost"] for p in pos.values()
                    if p.get("book") == "copy")
    disc_tied = sum(p["cost"] for p in pos.values()
                    if p.get("book") == "disc")
    copy_open = sum(1 for p in pos.values() if p.get("book") == "copy")
    disc_open = sum(1 for p in pos.values() if p.get("book") == "disc")

    evs = []
    lp = os.path.join(ROOT, "state", "ledger.jsonl")
    if os.path.exists(lp):
        with open(lp) as f:
            lines = f.readlines()[-50:]
        for line in reversed(lines):
            try:
                evs.append(json.loads(line))
            except ValueError:
                pass

    def ev_row(e):
        t = time.strftime("%m-%d %H:%M", time.localtime(e.get("ts", 0)))
        typ = e.get("type", "")
        q = (e.get("question") or "")[:56]
        det = ""
        if typ == "fill":
            det = (f"BUY {e.get('side')} @ {e.get('price')} "
                   f"(${e.get('usd')}) · fee ${e.get('fee')}")
        elif typ in ("close", "settle"):
            r = e.get("realized") or 0
            det = f"{'WIN' if r >= 0 else 'LOSS'} {_money(r)}"
        elif typ == "sweep":
            det = f"swept ${e.get('amount'):.2f} → sweep account"
        elif typ == "halt":
            det = e.get("reason", "")
        elif typ == "wallet_dropped":
            det = e.get("reason", "")
        r = e.get("reason")
        if r and typ == "fill":
            det += f"<div class='rsn'>{r[:120]}</div>"
        badge = {"copy": "COPY", "disc": "MUSE"}.get(e.get("book"), "")
        bhtml = f"<span class='tag b{badge.lower()}'>{badge}</span>" if badge else ""
        return (f"<div class='ev'><div class='evh'><span class='t'>{t}</span>"
                f"<span><span class='tag'>{typ}</span> {bhtml}</span></div>"
                f"<div class='evq'>{q}</div><div class='evd'>{det}</div></div>")

    pos_cards = []
    for tid, p in sorted(pos.items(), key=lambda kv: -kv[1]["cost"]):
        lp_ = p.get("last_price") or p["avg_price"]
        u = (lp_ - p["avg_price"]) * p["shares"]
        badge = "COPY" if p.get("book") == "copy" else "MUSE"
        w = (f"<div class='wln'>via {p['wallet'][:12]}…</div>"
             if p.get("wallet") else "")
        rsn = (f"<div class='rsn'>{p['reason'][:120]}</div>"
               if p.get("reason") else "")
        pos_cards.append(
            f"<div class='pcard'><div class='evh'>"
            f"<span class='tag b{badge.lower()}'>{badge}</span>"
            f"<span class='px'>{p['side']} @ {p['avg_price']:.3f} → {lp_:.3f}</span>"
            f"<span>{_money(u)}</span></div>"
            f"<div class='evq'>{p['question'][:64]}</div>{w}{rsn}"
            f"<div class='evd'>{p['shares']:.1f} shares · "
            f"in ${_money(p['cost'])}</div></div>")

    w_rows = []
    for w in wstate.get("wallets", []):
        st = w.get("status", "?")
        nm = w.get("name", w["address"][:12])
        if len(nm) > 18:
            nm = nm[:17] + "…"
        w_rows.append(
            f"<div class='wrow'><div class='evh'><span class='wn'>{nm}</span>"
            f"<span class='tag'>{st}</span></div>"
            f"<div class='evd'>{w.get('style', '')}</div>"
            f"<div class='evh' style='margin-top:4px'>"
            f"<span class='evd'>copied {w.get('copied_trades', 0)}</span>"
            f"<span>P&L {_money(w.get('copied_pnl', 0))}</span></div></div>")

    halt = (f"<div class='halt'>⛔ HALTED — {s.get('halt_reason', '')}</div>"
            if s.get("halted") else "")
    upd = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    recent, older = evs[:10], evs[10:40]
    older_html = "".join(ev_row(e) for e in older)
    older_block = (f"<details><summary>Older activity ({len(older)})</summary>"
                   f"{older_html}</details>" if older else "")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poly LLM — paper</title><style>
*{{box-sizing:border-box}}
body{{background:#0d1117;color:#e6edf3;font-family:system-ui,-apple-system,sans-serif;
margin:0;padding:14px;font-size:15px;line-height:1.45;max-width:680px;margin-left:auto;margin-right:auto}}
h1{{font-size:17px;margin:2px 0 12px;color:#e6edf3}}
h2{{font-size:13px;color:#8b949e;margin:22px 0 10px;text-transform:uppercase;letter-spacing:.8px}}
.hero{{background:linear-gradient(160deg,#161b22,#1a2332);border:1px solid #30363d;
border-radius:14px;padding:18px 16px;margin-bottom:12px}}
.hero .k{{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:.6px}}
.hero .big{{font-size:38px;font-weight:800;margin:4px 0 10px}}
.herorow{{display:flex;gap:10px}}
.herostat{{flex:1;min-width:0;background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:10px 12px}}
.tiles{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}
.tile{{min-width:0;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px 14px}}
.tile .k{{font-size:12px;color:#8b949e;margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tile .v{{font-size:21px;font-weight:700}}
.books{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}
.book{{min-width:0;background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px 14px}}
.book h3{{margin:0 0 8px;font-size:14px}}
.book .pnl{{font-size:22px;font-weight:700;margin-bottom:6px}}
.pos{{color:#3fb950}}.neg{{color:#f85149}}
.ev,.pcard,.wrow{{background:#161b22;border:1px solid #30363d;border-radius:10px;
padding:10px 12px;margin-bottom:8px}}
.evh{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
.ev .t{{color:#8b949e;font-size:12px;white-space:nowrap}}
.evq{{margin:5px 0 3px;font-size:14px}}
.evd{{color:#8b949e;font-size:13px}}
.px{{font-size:13px;color:#c9d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.rsn{{color:#a5d6ff;font-style:italic;margin-top:4px;font-size:13px}}
.wln{{color:#8b949e;font-size:12px}}
.wn{{font-weight:600;font-size:15px}}
.tag{{display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:5px;
padding:2px 7px;font-size:11px;color:#8b949e;white-space:nowrap}}
.bcopy{{color:#79c0ff;border-color:#1f6feb}}
.bmuse{{color:#d2a8ff;border-color:#8957e5}}
.halt{{background:#3d1113;border:1px solid #f85149;border-radius:10px;padding:12px;margin-bottom:12px;font-size:14px}}
details{{margin-top:6px}}
summary{{color:#8b949e;font-size:14px;cursor:pointer;padding:8px 0}}
.empty{{color:#6e7681;font-size:14px;padding:6px 0}}
.ft{{color:#6e7681;font-size:12px;margin:22px 0 8px;text-align:center}}
</style></head><body>
<h1>🎯 Poly LLM · paper · <span style="color:#8b949e;font-weight:400">{upd}</span></h1>
{halt}
<div class="hero"><div class="k">Total equity (bank + sweep)</div>
<div class="big">{_money(eq + sweep)}</div>
<div class="herorow">
<div class="herostat"><div class="k">Bank</div><div style="font-size:19px;font-weight:700">{_money(eq)}</div></div>
<div class="herostat"><div class="k">Sweep acct</div><div style="font-size:19px;font-weight:700">{_money(sweep)}</div></div>
</div></div>

<div class="tiles">
<div class="tile"><div class="k">Free cash</div><div class="v">{_money(cash)}</div></div>
<div class="tile"><div class="k">Tied up</div><div class="v">{_money(tied)}</div></div>
<div class="tile"><div class="k">Realized P&amp;L</div><div class="v">{_money(rpnl)}</div></div>
<div class="tile"><div class="k">Unrealized</div><div class="v">{_money(un)}</div></div>
<div class="tile"><div class="k">Fees paid</div><div class="v">{_money(-fees)}</div></div>
<div class="tile"><div class="k">Swept total</div><div class="v">{_money(s.get("swept_total", 0))}</div></div>
</div>

<h2>The two books</h2>
<div class="books">
<div class="book"><h3>📋 Copy <span class="tag">mechanical</span></h3>
<div class="pnl">{_money(books["copy"]["realized"])}</div>
<div class="evd">{copy_open} open · {_money(copy_tied)} tied</div></div>
<div class="book"><h3>🧠 Muse <span class="tag">discretionary</span></h3>
<div class="pnl">{_money(books["disc"]["realized"])}</div>
<div class="evd">{disc_open} open · {_money(disc_tied)} tied</div></div>
</div>

<h2>Open positions ({len(pos)})</h2>
{''.join(pos_cards) if pos_cards else "<div class='empty'>None — loop is watching wallets and markets.</div>"}

<h2>Wallets copied</h2>
{''.join(w_rows) if w_rows else "<div class='empty'>None yet.</div>"}

<h2>Recent activity</h2>
{''.join(ev_row(e) for e in recent) if recent else "<div class='empty'>No trades yet.</div>"}
{older_block}
<div class="ft">Paper only · fees modeled per fill · $25 sweeps · kill: −20% halt / 60-day review</div>
</body></html>"""
    with open(OUT, "w") as f:
        f.write(html)
    return OUT


if __name__ == "__main__":
    print(render())
