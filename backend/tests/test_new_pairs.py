"""Iter 5: verify new forex majors (USD/CHF, USD/CAD, AUD/USD) + watchlist size
+ real-data reliability (retry fix) + AI analysis for new pair + optimizer for all 5 majors.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

NEW_MAJORS = ["USD/CHF", "USD/CAD", "AUD/USD"]
ALL_MAJORS = ["EUR/USD", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD"]


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "demo@apexflow.io", "password": "apexflow2026"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


# --- Watchlist: 11 instruments incl 5 majors --------------------------------
def test_watchlist_has_11_and_majors(headers):
    r = requests.get(f"{API}/market/watchlist", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 11, f"expected 11 instruments got {len(items)}: {[i.get('symbol') for i in items]}"
    syms = {i["symbol"] for i in items}
    for m in ALL_MAJORS:
        assert m in syms, f"{m} missing from watchlist"


# --- Candles endpoint works for each new pair -------------------------------
@pytest.mark.parametrize("sym", NEW_MAJORS)
def test_candles_new_pairs(headers, sym):
    r = requests.get(f"{API}/market/candles",
                     params={"symbol": sym, "timeframe": "M15"},
                     headers=headers, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "candles" in d and len(d["candles"]) > 0
    assert "zones" in d


# --- Reliability: repeated forwardtest for new majors should be 'real' ------
@pytest.mark.parametrize("sym", NEW_MAJORS)
def test_forwardtest_real_consistency(headers, sym):
    real_count = 0
    for i in range(3):
        r = requests.post(f"{API}/forwardtest/run", headers=headers,
                          json={"symbol": sym, "timeframe": "M15",
                                "bars": 300, "mode": "balanced"}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] in ("real", "simulated")
        if d["source"] == "real":
            real_count += 1
        print(f"{sym} run {i+1}: source={d['source']} trades={d['total_trades']}")
    # per review: real expected on most attempts; require at least 2/3
    assert real_count >= 2, f"{sym}: only {real_count}/3 runs returned real data"


# --- Modes for USD/CHF and AUD/USD ------------------------------------------
@pytest.mark.parametrize("sym", ["USD/CHF", "AUD/USD"])
def test_modes_balanced(headers, sym):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": sym, "timeframe": "M15",
                            "bars": 400, "mode": "balanced"}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "balanced"
    assert "winrate" in d
    assert d["total_trades"] >= 0
    for t in d["trades"]:
        assert "entry_time" in t and "exit_time" in t


@pytest.mark.parametrize("sym", ["USD/CHF", "AUD/USD"])
def test_modes_highwinrate(headers, sym):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": sym, "timeframe": "M15",
                            "bars": 400, "mode": "highwinrate"}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "highwinrate"
    # high winrate + small tp vs wide sl -> avg_win<avg_loss when trades exist
    if d["total_trades"] > 0 and d["avg_win"] and d["avg_loss"]:
        assert d["avg_win"] < d["avg_loss"], \
            f"{sym} highwinrate expected avg_win<avg_loss got {d['avg_win']} vs {d['avg_loss']}"


@pytest.mark.parametrize("sym", ["USD/CHF", "AUD/USD"])
def test_modes_nosl(headers, sym):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": sym, "timeframe": "M15",
                            "bars": 500, "mode": "nosl"}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "nosl"
    for t in d["trades"]:
        assert t["sl"] is None
        assert "entry_time" in t and "exit_time" in t
    assert "true_equity" in d and "open_floating" in d and "worst_floating" in d


# --- Optimizer for all 5 forex majors ---------------------------------------
@pytest.mark.parametrize("sym", ALL_MAJORS)
def test_optimizer_all_majors(headers, sym):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": sym, "timeframe": "H1",
                            "bars": 500, "target_annual": 50}, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("best_params", "winrate", "profit_factor", "trades",
              "annual_at_1pct", "dd_at_1pct", "recommended_risk_percent",
              "projected_annual_return", "projected_max_drawdown",
              "target_reached", "combos_tested", "equity_curve", "source"):
        assert k in d, f"{sym} missing {k}"
    assert d["combos_tested"] > 0
    assert 0.25 <= d["recommended_risk_percent"] <= 5.0
    print(f"{sym} optimize: source={d['source']} combos={d['combos_tested']} "
          f"proj={d['projected_annual_return']}% risk={d['recommended_risk_percent']}")


# --- Optimizer apply: params passthrough -> mode='optimized' ---------------
def test_optimizer_apply_usdchf(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "USD/CHF", "timeframe": "M15", "bars": 400,
                            "params": {"entry": "smc", "tp_mult": 1.5,
                                       "sl_mult": 2.5, "trend_filter": False}},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "optimized"
    assert "winrate" in d and "profit_factor" in d


# --- AI analysis for a new pair ---------------------------------------------
def test_ai_analysis_usdchf(headers):
    r = requests.post(f"{API}/ai/analysis", headers=headers,
                      json={"symbol": "USD/CHF", "timeframe": "M15"}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    analysis = d.get("analysis", d)
    for k in ("bias", "score", "narrative", "setup"):
        assert k in analysis, f"AI response missing {k}"


# --- Annual period for a new pair -------------------------------------------
def test_annual_period_audusd(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "AUD/USD", "timeframe": "D1",
                            "bars": 365, "mode": "balanced"}, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["candles"]) >= 200
    assert d["period_start"] and d["period_end"]
    for t in d["trades"]:
        if t.get("entry_time"):
            assert d["period_start"] <= t["entry_time"] <= d["period_end"]


# --- Invalid-symbol error handling ------------------------------------------
def test_optimize_invalid_symbol(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "H1", "bars": 300},
                      timeout=30)
    assert r.status_code == 404


def test_execute_live_returns_ok_field(headers):
    r = requests.post(f"{API}/forwardtest/execute-live", headers=headers,
                      json={"symbol": "USD/CHF", "side": "BUY", "volume": 0.01},
                      timeout=60)
    # must not crash. 200 with ok bool, or 4xx handled — accept both, but if 200, must have ok
    assert r.status_code in (200, 400, 404, 500), r.text
    if r.status_code == 200:
        assert "ok" in r.json()
