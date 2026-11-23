"""Expression generation and result filtering. Pure functions, easy to test."""

from __future__ import annotations

import itertools
import json


def load_expressions(path: str) -> list[str]:
    """One expression per line. Blank lines and lines starting with # are skipped."""
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]


def expand(templates: list[str], fields: list[str], windows: list[int] | None = None) -> list[str]:
    """Fill {field} and optional {window} placeholders.

    expand(["-rank({field})"], ["ebit", "sales"])
      -> ["-rank(ebit)", "-rank(sales)"]
    """
    windows = windows or [20]
    out: list[str] = []
    for t in templates:
        if "{window}" in t:
            out += [t.format(field=f, window=w) for f, w in itertools.product(fields, windows)]
        elif "{field}" in t:
            out += [t.format(field=f) for f in fields]
        else:
            out.append(t)
    return list(dict.fromkeys(out))  # dedupe, keep order


def failed_checks(checks: list[dict]) -> list[str]:
    return [c["name"] for c in checks if c.get("result") == "FAIL"]


def passes(row, min_sharpe: float, min_fitness: float, max_turnover: float = 0.7,
           min_turnover: float = 0.01) -> bool:
    """Our own thresholds plus no FAIL in BRAIN's check list."""
    if row["sharpe"] is None or row["fitness"] is None or row["turnover"] is None:
        return False
    checks = json.loads(row["checks"] or "[]")
    return (row["sharpe"] >= min_sharpe and row["fitness"] >= min_fitness
            and min_turnover <= row["turnover"] <= max_turnover
            and not failed_checks(checks))


def diagnose(row) -> str:
    """One-line hint for what to change, following the usual BRAIN tuning rules."""
    s, f, t = row["sharpe"] or 0, row["fitness"] or 0, row["turnover"] or 0
    if s < 0:
        return "negative Sharpe: try flipping the sign"
    if s < 0.5:
        return "weak signal: change the idea, settings will not fix it"
    if t > 0.7:
        return "turnover too high: raise decay, add ts_mean or trade_when"
    if s >= 1.25 and f < 1.0:
        return "Sharpe ok, fitness low: cut turnover or try another neutralization"
    if s < 1.25:
        return "close: try neutralization/decay/universe variants"
    return "ok"
