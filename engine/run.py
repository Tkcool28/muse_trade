#!/usr/bin/env python3
"""Hook entrypoint: settle -> copy scan -> candidate scan -> dashboard.
Prints one JSON summary; the shell wrapper decides silent vs wake."""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledger import load_state, save_state, equity  # noqa: E402
from settle import run_settle  # noqa: E402
from copy import run_copy  # noqa: E402
from scanner import scan  # noqa: E402
import dashboard  # noqa: E402


def main():
    t0 = time.time()
    out = {"ok": True, "events": [], "ts": int(t0)}
    try:
        s = load_state()
        out["events"].extend(run_settle(s))
        out["events"].extend(run_copy(s))
        c = scan()
        out["candidates"] = {k: len(v) for k, v in c.items()
                             if isinstance(v, list)}
        dashboard.render()
        save_state(s)
        e = equity(s)
        out["equity"] = {k: round(v, 2) for k, v in e.items()}
        out["open"] = len(s["positions"])
        out["halted"] = s.get("halted", False)
        out["took_s"] = round(time.time() - t0, 1)
    except Exception as ex:  # noqa: BLE001
        out["ok"] = False
        out["error"] = str(ex)[:200]
        out["trace"] = traceback.format_exc()[-800:]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
