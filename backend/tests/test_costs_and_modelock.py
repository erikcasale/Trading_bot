"""Backend tests for CURRENT iteration:
   (a) Real trading costs applied on every trade (cost > 0 on every trade)
   (b) Legacy mode strings ('highwinrate','nosl','totally_bogus') coerced to 'balanced'
   (c) params -> mode='optimized'
   (d) Optimizer + OOS still work (cost-adjusted)
   (e) watchlist=11 ; invalid symbol -> 404
"""
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


# (a) & basic contract
def test_forwardtest_returns_balanced_and_trades_have_cost(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "H1", "bars": 500},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "balanced", f"expected balanced got {d['mode']}"
    # trades must exist (either closed or open) with 'cost' field > 0
    trades = d.get("trades", [])
    assert len(trades) > 0, "expected at least one trade for EUR/USD H1 500 bars"
    for t in trades:
        assert "cost" in t, f"trade missing 'cost': {t}"
        assert t["cost"] > 0, f"cost must be > 0, got {t['cost']}"
    # realized_net reflects costs (may be positive or negative — honest)
    assert "realized_net" in d
    assert isinstance(d["profit_factor"], (int, float))
    # PF < 1 acceptable (honest behavior)
    print(f"EUR/USD balanced: PF={d['profit_factor']} realized_net={d['realized_net']} "
          f"trades={d['total_trades']} sample_cost={trades[0]['cost']}")


# (b) legacy 'nosl' and 'highwinrate' -> coerced to balanced, NO error
@pytest.mark.parametrize("legacy_mode", ["nosl", "highwinrate", "totally_bogus"])
def test_forwardtest_legacy_modes_coerced_to_balanced(headers, legacy_mode):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "H1",
                            "bars": 400, "mode": legacy_mode},
                      timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "balanced", f"legacy mode '{legacy_mode}' must coerce to 'balanced', got {d['mode']}"


# (c) params -> optimized
def test_forwardtest_with_params_returns_optimized(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "US30", "timeframe": "H1", "bars": 500,
                            "risk_percent": 0.5,
                            "params": {"entry": "breakout", "tp_mult": 2.0,
                                       "sl_mult": 2.5, "trend_filter": False}},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "optimized"
    # costs still applied
    for t in d.get("trades", []):
        assert t.get("cost", 0) > 0


# (d) optimizer still works
def test_optimize_us30_cost_adjusted(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "US30", "timeframe": "H1",
                            "bars": 600, "target_annual": 50}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("best_params", "winrate", "profit_factor", "annual_at_1pct",
              "recommended_risk_percent", "projected_annual_return", "equity_curve"):
        assert k in d
    assert d["combos_tested"] > 0


# (d2) OOS still works
def test_optimize_oos_eurusd(headers):
    r = requests.post(f"{API}/optimize/oos", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "H1",
                            "bars": 800, "split": 0.7}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verdict"] in ("robusta", "fragile", "incerta")
    for seg in ("in_sample", "out_sample"):
        assert seg in d
        for k in ("winrate", "profit_factor", "annual_return", "trades", "equity_curve"):
            assert k in d[seg]


# (e) watchlist
def test_watchlist_11(headers):
    r = requests.get(f"{API}/market/watchlist", headers=headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", data.get("instruments", []))
    assert len(items) == 11


def test_forwardtest_invalid_symbol_404(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "H1", "bars": 300},
                      timeout=30)
    assert r.status_code == 404


def test_optimize_invalid_symbol_404(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "H1", "bars": 300},
                      timeout=30)
    assert r.status_code == 404
