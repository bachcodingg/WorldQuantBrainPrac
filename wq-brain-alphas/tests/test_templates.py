import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.fake import FakeClient
from brain.store import Store
from brain.templates import diagnose, expand, passes


def test_expand_fields_and_windows():
    out = expand(["-rank({field})", "ts_rank({field}, {window})", "rank(close)"], ["a", "b"], [5, 10])
    assert out[:2] == ["-rank(a)", "-rank(b)"]
    assert "ts_rank(b, 10)" in out
    assert out[-1] == "rank(close)"
    assert len(out) == 2 + 4 + 1


def test_expand_dedupes():
    assert expand(["rank(x)", "rank(x)"], ["f"]) == ["rank(x)"]


def row(sharpe, fitness, turnover, checks=()):
    return {"sharpe": sharpe, "fitness": fitness, "turnover": turnover, "checks": json.dumps(list(checks))}


def test_passes_thresholds_and_checks():
    assert passes(row(1.5, 1.2, 0.3), 1.25, 1.0)
    assert not passes(row(1.1, 1.2, 0.3), 1.25, 1.0)
    assert not passes(row(1.5, 1.2, 0.8), 1.25, 1.0)
    assert not passes(row(1.5, 1.2, 0.3, [{"name": "CONCENTRATED_WEIGHT", "result": "FAIL"}]), 1.25, 1.0)


def test_diagnose():
    assert "flip" in diagnose(row(-0.4, -0.2, 0.3))
    assert "turnover" in diagnose(row(1.5, 0.8, 0.9))


def test_store_skips_repeats(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    client = FakeClient()
    s = {"decay": 4}
    res = client.simulate("rank(close)", s)
    store.save(res, s)
    assert store.seen("rank(close)", s)
    assert not store.seen("rank(close)", {"decay": 10})
