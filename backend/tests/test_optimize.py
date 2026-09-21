"""Backend tests: /api/optimize grid-search + /forwardtest/run with optimized params."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "demo@apexflow.io", "password": "apexflow2026"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


REQUIRED_OPTIMIZE_KEYS = [
    "best_params", "winrate", "profit_factor", "trades",
    "annual_at_1pct", "dd_at_1pct", "recommended_risk_percent",
    "projected_annual_return", "projected_max_drawdown",
    "target_reached", "combos_tested", "days",
    "period_start", "period_end", "equity_curve", "source",
]


def _check_optimize(d):
    for k in REQUIRED_OPTIMIZE_KEYS:
        assert k in d, f"missing {k}"
    bp = d["best_params"]
    assert bp["entry"] in ("smc", "meanrev", "breakout")
    assert isinstance(bp["tp_mult"], (int, float))
    assert isinstance(bp["sl_mult"], (int, float))
    assert isinstance(bp["trend_filter"], bool)
    assert d["combos_tested"] > 0
    assert 0.25 <= d["recommended_risk_percent"] <= 5.0
    assert isinstance(d["projected_annual_return"], (int, float))
    assert isinstance(d["target_reached"], bool)
    assert d["source"] in ("real", "simulated")


def test_optimize_us30(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "US30", "timeframe": "H1",
                            "bars": 600, "target_annual": 50}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    _check_optimize(d)
    print(f"US30 optimize: combos={d['combos_tested']} best={d['best_params']} "
          f"proj_annual={d['projected_annual_return']} risk={d['recommended_risk_percent']} "
          f"target_reached={d['target_reached']} source={d['source']}")


@pytest.mark.parametrize("sym", ["EUR/USD", "XAU/USD", "GBP/USD"])
def test_optimize_multi(headers, sym):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": sym, "timeframe": "H1",
                            "bars": 500, "target_annual": 50}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    _check_optimize(d)
    # real-data symbols expected to be 'real' (per review), soft-log
    print(f"{sym} source={d['source']} proj_annual={d['projected_annual_return']}")


def test_optimize_invalid_symbol(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "H1", "bars": 300},
                      timeout=30)
    assert r.status_code == 404


def test_forwardtest_with_optimized_params(headers):
    payload = {
        "symbol": "US30", "timeframe": "H1", "bars": 600,
        "risk_percent": 0.56,
        "params": {"entry": "breakout", "tp_mult": 2.0, "sl_mult": 2.5, "trend_filter": False},
    }
    r = requests.post(f"{API}/forwardtest/run", headers=headers, json=payload, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "optimized"
    for k in ("winrate", "profit_factor", "realized_net", "true_equity", "trades",
              "total_trades", "period_start", "period_end"):
        assert k in d
    assert d["source"] in ("real", "simulated")
