"""Offline stand-in for BrainClient so the pipeline can run without an account (--dry-run).

Metrics are random but deterministic per expression. They mean nothing about real performance.
"""

from __future__ import annotations

import hashlib
import random

from .client import SimResult


class FakeClient:
    def login(self) -> None:
        pass

    def simulate(self, expression: str, settings: dict) -> SimResult:
        seed = int(hashlib.md5((expression + str(sorted(settings.items()))).encode()).hexdigest(), 16)
        rng = random.Random(seed)
        if "(" not in expression:
            return SimResult(expression, None, "ERROR", "Fake: expression has no operator")
        sharpe = round(rng.uniform(-0.5, 2.5), 2)
        turnover = round(rng.uniform(0.01, 0.9), 4)
        returns = round(rng.uniform(-0.05, 0.25), 4)
        fitness = round(sharpe * (abs(returns) / max(turnover, 0.125)) ** 0.5, 2)
        checks = [
            {"name": "LOW_SHARPE", "result": "PASS" if sharpe >= 1.25 else "FAIL", "limit": 1.25, "value": sharpe},
            {"name": "LOW_FITNESS", "result": "PASS" if fitness >= 1.0 else "FAIL", "limit": 1.0, "value": fitness},
            {"name": "HIGH_TURNOVER", "result": "PASS" if turnover <= 0.7 else "FAIL", "limit": 0.7, "value": turnover},
            {"name": "LOW_TURNOVER", "result": "PASS" if turnover >= 0.01 else "FAIL", "limit": 0.01, "value": turnover},
            {"name": "SELF_CORRELATION", "result": "PENDING"},
        ]
        metrics = {"sharpe": sharpe, "fitness": fitness, "turnover": turnover, "returns": returns,
                   "drawdown": round(rng.uniform(0.02, 0.3), 4), "margin": round(rng.uniform(0, 0.002), 6)}
        return SimResult(expression, f"FAKE{seed % 10**8:08d}", "OK", metrics=metrics, checks=checks)

    def submit(self, alpha_id: str) -> dict:
        return {"dry_run": True, "alpha": alpha_id}

    def data_fields(self, dataset: str, settings: dict, limit: int = 50) -> list[dict]:
        return [{"id": f, "description": "fake", "type": "MATRIX", "coverage": 0.9}
                for f in ("assets", "liabilities", "sales", "ebit", "capex", "operating_income")]
