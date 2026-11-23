"""SQLite storage: one row per simulation, so nothing is simulated twice."""

from __future__ import annotations

import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS sims (
    id INTEGER PRIMARY KEY,
    created REAL,
    expression TEXT,
    settings TEXT,
    alpha_id TEXT,
    status TEXT,
    message TEXT,
    sharpe REAL, fitness REAL, turnover REAL, returns REAL, drawdown REAL, margin REAL,
    checks TEXT,
    submitted INTEGER DEFAULT 0,
    UNIQUE(expression, settings)
);
"""


class Store:
    def __init__(self, path: str = "alphas.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @staticmethod
    def _key(settings: dict) -> str:
        return json.dumps(settings, sort_keys=True)

    def seen(self, expression: str, settings: dict) -> bool:
        cur = self.db.execute("SELECT 1 FROM sims WHERE expression=? AND settings=?",
                              (expression, self._key(settings)))
        return cur.fetchone() is not None

    def save(self, res, settings: dict) -> None:
        m = res.metrics or {}
        self.db.execute(
            """INSERT OR REPLACE INTO sims
               (created, expression, settings, alpha_id, status, message,
                sharpe, fitness, turnover, returns, drawdown, margin, checks)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), res.expression, self._key(settings), res.alpha_id, res.status, res.message,
             m.get("sharpe"), m.get("fitness"), m.get("turnover"), m.get("returns"),
             m.get("drawdown"), m.get("margin"), json.dumps(res.checks or [])),
        )
        self.db.commit()

    def rows(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM sims WHERE status='OK'"))

    def mark_submitted(self, alpha_id: str) -> None:
        self.db.execute("UPDATE sims SET submitted=1 WHERE alpha_id=?", (alpha_id,))
        self.db.commit()
