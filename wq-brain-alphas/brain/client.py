"""Minimal client for the WorldQuant BRAIN REST API.

Endpoints used:
  POST /authentication              log in (HTTP basic auth, sets a session cookie)
  POST /simulations                 start a simulation, returns a Location header to poll
  GET  <Location>                   poll; Retry-After header > 0 means still running
  GET  /alphas/{id}                 in-sample metrics and submission checks
  POST /alphas/{id}/submit          submit an alpha (poll the same way)
  GET  /data-fields                 list data fields for a dataset
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

API = "https://api.worldquantbrain.com"


class BrainError(RuntimeError):
    pass


@dataclass
class SimResult:
    expression: str
    alpha_id: str | None
    status: str            # "OK" or "ERROR"
    message: str = ""
    metrics: dict | None = None
    checks: list | None = None


class BrainClient:
    def __init__(self, email: str, password: str, session: requests.Session | None = None,
                 poll_cap: float = 30.0):
        self.email = email
        self.password = password
        self.s = session or requests.Session()
        self.poll_cap = poll_cap

    # ---------- auth ----------
    def login(self) -> None:
        r = self.s.post(f"{API}/authentication", auth=HTTPBasicAuth(self.email, self.password))
        if r.status_code == 401 and "persona" in r.headers.get("WWW-Authenticate", "").lower():
            # Biometric check required. The user finishes it in a browser, then we confirm.
            url = urljoin(r.url, r.headers["Location"])
            input(f"Complete the biometric check in your browser:\n  {url}\nPress Enter when done...")
            r = self.s.post(url)
        if r.status_code not in (200, 201):
            raise BrainError(f"Login failed ({r.status_code}): {r.text[:300]}")

    # ---------- helpers ----------
    def _request(self, method: str, url: str, **kw) -> requests.Response:
        """Request with retry on 429 (rate limit) and one re-login on 401."""
        for attempt in range(6):
            r = self.s.request(method, url, **kw)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 10)))
                continue
            if r.status_code == 401 and attempt == 0:
                self.login()
                continue
            return r
        raise BrainError(f"Gave up on {method} {url} after repeated 429s")

    def _poll(self, url: str) -> requests.Response:
        while True:
            r = self._request("GET", url)
            wait = float(r.headers.get("Retry-After", 0))
            if wait == 0:
                return r
            time.sleep(min(wait, self.poll_cap))

    # ---------- simulation ----------
    def simulate(self, expression: str, settings: dict) -> SimResult:
        payload = {"type": "REGULAR", "settings": settings, "regular": expression}
        r = self._request("POST", f"{API}/simulations", json=payload)
        if r.status_code != 201:
            return SimResult(expression, None, "ERROR", f"{r.status_code}: {r.text[:300]}")

        done = self._poll(r.headers["Location"]).json()
        if done.get("status") in ("ERROR", "FAIL") or "alpha" not in done:
            return SimResult(expression, None, "ERROR", str(done.get("message", done))[:300])

        alpha = self.get_alpha(done["alpha"])
        ins = alpha.get("is", {}) or {}
        metrics = {k: ins.get(k) for k in
                   ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin")}
        return SimResult(expression, done["alpha"], "OK", metrics=metrics,
                         checks=ins.get("checks", []))

    def get_alpha(self, alpha_id: str) -> dict:
        r = self._request("GET", f"{API}/alphas/{alpha_id}")
        r.raise_for_status()
        return r.json()

    def submit(self, alpha_id: str) -> dict:
        r = self._request("POST", f"{API}/alphas/{alpha_id}/submit")
        if r.status_code >= 400:
            raise BrainError(f"Submit failed ({r.status_code}): {r.text[:300]}")
        final = self._poll(f"{API}/alphas/{alpha_id}/submit")
        return final.json() if final.content else {"status_code": final.status_code}

    # ---------- data ----------
    def data_fields(self, dataset: str, settings: dict, limit: int = 50) -> list[dict]:
        out, offset = [], 0
        while True:
            params = {
                "instrumentType": settings["instrumentType"], "region": settings["region"],
                "delay": settings["delay"], "universe": settings["universe"],
                "dataset.id": dataset, "limit": limit, "offset": offset,
            }
            r = self._request("GET", f"{API}/data-fields", params=params)
            r.raise_for_status()
            page = r.json()
            out += page.get("results", [])
            offset += limit
            if offset >= page.get("count", 0):
                return out
