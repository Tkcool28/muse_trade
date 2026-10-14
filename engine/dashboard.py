#!/usr/bin/env python3
"""Render dashboard.html from state. Phone-first, dark."""
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
    return f'<span class="{c}">${x:,.2f}</span>'


def render():
    s = _load("state.json", {})
    wstate = _load("wallets.json", {"wallets": []})
    cands = _load("candidates.json", {})
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

    # recent ledger events (newest first, skip fills noise? keep all, cap 40)
    evs = []
    lp = os.path.join(ROOT, "state", "ledger.jsonl")
    if os.path.exists(lp):
        with open(lp) as f:
            lines = f.readlines()[-60:]
        for line in reversed(lines):
            try:
                evs.append(json.loads(line))
            except ValueError:
                pass

    def ev_row(e):
        t = time.strftime("%m-%d %H:%M", time.localtime(e.get("ts", 0)))
        typ = e.get("type", "")
        q = (e.get("question") or "")[:52]
        det = ""
        if typ == "fill":
            det = (f"BUY {e.get('side')} @ {e.get('price')} "
                   f"(${e.get('usd')}) fee ${e.get('fee')}")
        elif typ in ("close", "settle"):
            det = f"{'WIN' if (e.get('realized') or 0) >= 0 else 'LOSS'} { _money(e.get('realized') or 0)}"
        elif typ == "sweep":
            det = f"swept ${e.get('amount')}"
        elif typ == "halt":
            det = e.get("reason", "")
        r = e.get("reason")
        if r and typ == "fill":
            det += f"<div class='rsn'>{r[:110]}</div>"
        badge = {"copy": "COPY", "disc": "MUSE"}.get(e.get("book"), "")
        return (f"<div class='ev'><div class='evh'><span>{t}</span>"
                f"<span class='tag'>{typ}</span>{(' <span class=tag>'+badge+'</span>') if badge else ''}</div>"
                f"<div class='evq'>{q}</div><div class='evd'>{det}</div></div>")

    pos_rows = []
    for tid, p in sorted(pos.values(), key=lambda x: -x["cost"]):
        lp_ = p.get("last_price") or p["avg_price"]
        u = (lp_ - p["avg_price"]) * p["shares"]
        badge = "COPY" if p.get("book") == "copy" else "MUSE"
        w = f"<div class='wln'>via {p['wallet'][:10]}…</div>" if p.get("wallet") else ""
        rsn = f"<div class='rsn'>{p['reason'][:110]}</div>" if p.get("reason") else ""
        pos_rows.append(
            f"<div class='pos'><div class='evh'><span class='tag'>{badge}</span>"
            f"<span>{p['side']} @ {p['avg_price']:.3f} → {lp_:.3f}</span>"
            f"<span>{_money(u)}</span></div>"
            f"<div class='evq'>{p['question'][:64]}</div>{w}{rsn}</div>")

    w_rows = []
    for w in wstate.get("wallets", []):
        st = w.get("status", "?")
        w_rows.append(
            f"<div class='wrow'><div class='evh'><span>{w.get('name', w['address'][:10])}</span>"
            f"<span class='tag'>{st}</span></div>"
            f"<div class='evd'>copied {w.get('copied_trades', 0)} · "
            f"P&L {_money(w.get('copied_pnl', 0))}</div></div>")

    halt = (f"<div class='halt'>⛔ HALTED — {s.get('halt_reason','')}</div>"
            if s.get("halted") else "")
    upd = time.strftime("%Y-%m-%d %H:%M", time.localtime())

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poly LLM — paper</title><style>
body{{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;margin:0;padding:12px;max-width:640px}}
h2{{font-size:15px;color:#8b949e;margin:18px 0 8px;text-transform:uppercase;letter-spacing:.5px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px;margin-bottom:10px}}
.big{{font-size:30px;font-weight:700}}.pos{{color:#3fb950}}.neg{{color:#f85149}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.k{{font-size:11px;color:#8b949e}}.v{{font-size:17px;font-weight:600}}
.ev,.pos,.wrow{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px;margin-bottom:6px;font-size:13px}}
.evh{{display:flex;justify-content:space-between;gap:6px;align-items:center}}
.evq{{color:#c9d1d9;margin:3px 0}}.evd{{color:#8b949e;font-size:12px}}
.rsn{{color:#a5d6ff;font-style:italic;margin-top:3px;font-size:12px}}
.wln{{color:#8b949e;font-size:11px}}
.tag{{background:#21262d;border:1px solid #30363d;border-radius:4px;padding:1px 6px;font-size:10px;color:#8b949e}}
.halt{{background:#3d1113;border:1px solid #f85149;border-radius:8px;padding:10px;margin-bottom:10px}}
.ft{{color:#6e7681;font-size:11px;margin-top:16px;text-align:center}}
</style></head><body>
<h2>🎯 Poly LLM · paper · updated {upd}</h2>{halt}
<div class="card"><div class="k">TOTAL EQUITY (bank + sweep)</div>
<div class="big">{_money(eq + sweep)}</div>
<div class="grid" style="margin-top:8px">
<div><div class="k">Bank equity</div><div class="v">{_money(eq)}</div></div>
<div><div class="k">Sweep account</div><div class="v">{_money(sweep)}</div></div>
<div><div class="k">Free cash</div><div class="v">{_money(cash)}</div></div>
<div><div class="k">Tied up</div><div class="v">{_money(tied)}</div></div>
<div><div class="k">Realized P&L</div><div class="v">{_money(rpnl)}</div></div>
<div><div class="k">Unrealized</div><div class="v">{_money(un)}</div></div>
<div><div class="k">Fees paid</div><div class="v">{_money(-fees)}</div></div>
<div><div class="k">Copy / Muse realized</div><div class="v">{_money(s['books']['copy']['realized'])} / {_money(s['books']['disc']['realized'])}</div></div>
</div></div>
<h2>Open positions ({len(pos)})</h2>
{''.join(pos_rows) if pos_rows else "<div class='evd'>none</div>"}
<h2>Wallets copied</h2>
{''.join(w_rows) if w_rows else "<div class='evd'>none yet</div>"}
<h2>Recent activity</h2>
{''.join(ev_row(e) for e in evs[:40])}
<div class="ft">Paper only · fees modeled per fill · sweeps at $25 · kill: -20% halt / 60-day review</div>
</body></html>"""
    with open(OUT, "w") as f:
        f.write(html)
    return OUT


if __name__ == "__main__":
    print(render())
