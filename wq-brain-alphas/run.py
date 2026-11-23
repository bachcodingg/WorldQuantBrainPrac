"""CLI for the BRAIN alpha pipeline.

  python run.py simulate alphas/starter.txt          # simulate a list of expressions
  python run.py fields fundamental6 -o fields.txt    # fetch field ids for a dataset
  python run.py sweep alphas/templates.txt fields.txt --windows 20 60 250
  python run.py report                               # show results, best first
  python run.py submit <ALPHA_ID>                    # submit one alpha (manual on purpose)

Add --dry-run to any command to use the offline fake client instead of the real API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib

from brain.client import BrainClient
from brain.fake import FakeClient
from brain.store import Store
from brain.templates import diagnose, expand, failed_checks, load_expressions, passes


def load_settings(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def make_client(dry_run: bool):
    if dry_run:
        return FakeClient()
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    email, pw = os.getenv("BRAIN_EMAIL"), os.getenv("BRAIN_PASSWORD")
    if not email or not pw:
        sys.exit("Set BRAIN_EMAIL and BRAIN_PASSWORD in .env (see .env.example), or use --dry-run.")
    c = BrainClient(email, pw)
    c.login()
    return c


def run_batch(client, store: Store, expressions: list[str], sim: dict, overrides: dict) -> None:
    settings = {**sim, **overrides}
    todo = [e for e in expressions if not store.seen(e, settings)]
    print(f"{len(expressions)} expressions, {len(expressions) - len(todo)} already done, {len(todo)} to run")
    for i, expr in enumerate(todo, 1):
        res = client.simulate(expr, settings)
        store.save(res, settings)
        if res.status == "OK":
            m = res.metrics
            print(f"[{i}/{len(todo)}] S={m['sharpe']:>5} F={m['fitness']:>5} T={m['turnover']:>6}  {expr}")
        else:
            print(f"[{i}/{len(todo)}] ERROR {res.message[:80]}  {expr}")


def parse_overrides(pairs: list[str]) -> dict:
    """--set decay=10 --set neutralization=MARKET"""
    out = {}
    for p in pairs or []:
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="use the offline fake client")
    ap.add_argument("--db", default="alphas.db")
    ap.add_argument("--settings", default="settings.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("simulate"); p.add_argument("file")
    p.add_argument("--set", action="append", help="override a setting, e.g. decay=10")

    p = sub.add_parser("sweep"); p.add_argument("templates"); p.add_argument("fields")
    p.add_argument("--windows", type=int, nargs="*", default=[20, 60, 250])
    p.add_argument("--limit", type=int, default=50, help="max expressions to run")
    p.add_argument("--set", action="append")

    p = sub.add_parser("fields"); p.add_argument("dataset"); p.add_argument("-o", "--out", default="fields.txt")
    p.add_argument("--min-coverage", type=float, default=0.7)

    p = sub.add_parser("report"); p.add_argument("--all", action="store_true", help="show failing alphas too")
    p.add_argument("--top", type=int, default=20)

    p = sub.add_parser("submit"); p.add_argument("alpha_id")

    a = ap.parse_args()
    cfg = load_settings(a.settings)
    sim, flt = cfg["simulation"], cfg["filter"]
    store = Store(a.db)

    if a.cmd == "report":
        rows = sorted(store.rows(), key=lambda r: (r["fitness"] or -9), reverse=True)
        if not a.all:
            rows = [r for r in rows if passes(r, flt["min_sharpe"], flt["min_fitness"],
                                              flt["max_turnover"], flt["min_turnover"])]
        print(f"{'alpha_id':<12}{'sharpe':>7}{'fit':>6}{'turn':>7}{'ret':>7}  sub  note / expression")
        for r in rows[: a.top]:
            note = ", ".join(failed_checks(json.loads(r["checks"]))) or diagnose(r)
            print(f"{r['alpha_id']:<12}{r['sharpe']:>7.2f}{r['fitness']:>6.2f}{r['turnover']:>7.3f}"
                  f"{r['returns']:>7.3f}  {'yes' if r['submitted'] else ' - '}  [{note}] {r['expression']}")
        if not rows:
            print("No alphas pass yet. Run with --all to see what failed and why.")
        return

    client = make_client(a.dry_run)

    if a.cmd == "simulate":
        run_batch(client, store, load_expressions(a.file), sim, parse_overrides(a.set))
    elif a.cmd == "sweep":
        exprs = expand(load_expressions(a.templates), load_expressions(a.fields), a.windows)[: a.limit]
        run_batch(client, store, exprs, sim, parse_overrides(a.set))
    elif a.cmd == "fields":
        fields = [f for f in client.data_fields(a.dataset, sim)
                  if f.get("type") == "MATRIX" and (f.get("coverage") or 0) >= a.min_coverage]
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("\n".join(x["id"] for x in fields) + "\n")
        print(f"Wrote {len(fields)} fields to {a.out}")
    elif a.cmd == "submit":
        print(json.dumps(client.submit(a.alpha_id), indent=2)[:2000])
        store.mark_submitted(a.alpha_id)


if __name__ == "__main__":
    main()
