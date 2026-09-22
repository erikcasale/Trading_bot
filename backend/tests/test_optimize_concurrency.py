"""Verify /api/optimize (heavy CPU, ~72 combos) no longer blocks the event loop.

Fires ONE long POST /api/optimize and, while it is in flight, hits GET
/api/datasource/status and GET /api/market/watchlist and asserts each short
call returns quickly (well under 2s). Also verifies full optimize schema for
USD/CAD, USD/CHF, EUR/USD; invalid symbol -> 404; forwardtest regression;
watchlist size = 11 with 5 forex majors.
"""
import os
import time
import threading
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"

REQUIRED = [
    "best_params", "winrate", "profit_factor", "trades",
    "annual_at_1pct", "dd_at_1pct", "recommended_risk_percent",
    "projected_annual_return", "projected_max_drawdown",
    "target_reached", "combos_tested", "days",
    "period_start", "period_end", "equity_curve", "source",
]

MAJORS = {"EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD"}


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "demo@apexflow.io", "password": "apexflow2026"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


def _validate(d, expect_source_real=True):
    for k in REQUIRED:
        assert k in d, f"missing key {k}"
    assert d["combos_tested"] == 72, f"expected 72 combos, got {d['combos_tested']}"
    bp = d["best_params"]
    assert bp["entry"] in ("smc", "meanrev", "breakout")
    assert isinstance(bp["tp_mult"], (int, float))
    assert isinstance(bp["sl_mult"], (int, float))
    assert isinstance(bp["trend_filter"], bool)
    assert 0.25 <= d["recommended_risk_percent"] <= 5.0
    assert isinstance(d["projected_annual_return"], (int, float))
    assert isinstance(d["projected_max_drawdown"], (int, float))
    assert isinstance(d["target_reached"], bool)
    assert d["source"] in ("real", "simulated")
    assert isinstance(d["equity_curve"], list) and len(d["equity_curve"]) > 0
    if expect_source_real:
        # majors should be real; log soft-warning if simulated
        if d["source"] != "real":
            print(f"WARN: expected source=real, got {d['source']}")


@pytest.mark.parametrize("sym", ["USD/CAD", "USD/CHF", "EUR/USD"])
def test_optimize_schema_majors(headers, sym):
    t0 = time.time()
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": sym, "timeframe": "H1",
                            "bars": 600, "target_annual": 50}, timeout=60)
    dt = time.time() - t0
    assert r.status_code == 200, r.text
    d = r.json()
    _validate(d, expect_source_real=True)
    print(f"{sym}: {dt:.2f}s source={d['source']} combos={d['combos_tested']} "
          f"best={d['best_params']} proj_annual={d['projected_annual_return']} "
          f"risk={d['recommended_risk_percent']}")


def test_optimize_invalid_symbol(headers):
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "H1", "bars": 300},
                      timeout=30)
    assert r.status_code == 404


def test_optimize_insufficient_data_graceful(headers):
    """A valid symbol with tiny bars should return 422 gracefully, not 500."""
    # bars is clamped to min 200 in server; force insufficient trades path.
    # Use very short window on TF where trades will be few -> 422 if best is None.
    r = requests.post(f"{API}/optimize", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M5", "bars": 200,
                            "target_annual": 50}, timeout=60)
    # Either succeeds with valid data, or returns 422 gracefully. NEVER 500.
    assert r.status_code in (200, 422), f"unexpected {r.status_code}: {r.text}"
    if r.status_code == 422:
        assert "insufficient" in r.text.lower() or "insufficienti" in r.text.lower()


def test_concurrency_event_loop_not_blocked(headers):
    """Fire long /optimize; mid-flight, short GET /datasource/status must be fast."""
    result_holder = {}

    def _run_optimize():
        t0 = time.time()
        try:
            r = requests.post(f"{API}/optimize", headers=headers,
                              json={"symbol": "EUR/USD", "timeframe": "H1",
                                    "bars": 700, "target_annual": 50}, timeout=60)
            result_holder["optimize"] = (r.status_code, time.time() - t0, r.text[:200])
        except Exception as e:
            result_holder["optimize"] = ("ERR", time.time() - t0, str(e))

    t = threading.Thread(target=_run_optimize)
    t.start()

    # Give the server ~0.5s to start the heavy work
    time.sleep(0.5)

    # Fire short requests while optimize is in flight
    short_calls = []
    for i in range(3):
        t0 = time.time()
        r = requests.get(f"{API}/datasource/status", headers=headers, timeout=10)
        dt = time.time() - t0
        short_calls.append(("datasource/status", r.status_code, dt))
        assert r.status_code == 200, r.text
        assert dt < 3.0, f"datasource/status blocked {dt:.2f}s while optimize running"
        time.sleep(0.3)

    t0 = time.time()
    r = requests.get(f"{API}/market/watchlist", headers=headers, timeout=10)
    dt = time.time() - t0
    short_calls.append(("market/watchlist", r.status_code, dt))
    assert r.status_code == 200
    assert dt < 3.0, f"market/watchlist blocked {dt:.2f}s while optimize running"

    # Wait for optimize thread to finish
    t.join(timeout=90)
    assert not t.is_alive(), "optimize thread did not finish"
    opt_status, opt_dur, opt_body = result_holder.get("optimize", (None, 0, ""))
    print(f"OPTIMIZE: status={opt_status} dur={opt_dur:.2f}s")
    for name, code, dur in short_calls:
        print(f"  concurrent {name}: {code} in {dur*1000:.0f}ms")
    assert opt_status == 200, f"optimize failed: {opt_body}"
    # optimize should actually take some real time (>1s) to prove concurrency test was valid
    assert opt_dur > 1.0, f"optimize was too fast ({opt_dur:.2f}s) to be a meaningful concurrency test"
    # max concurrent short call latency
    max_short = max(d for _, _, d in short_calls)
    assert max_short < 2.0, f"a concurrent short call took {max_short:.2f}s (>2s) — loop may be blocked"


def test_forwardtest_preset_balanced(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "H1", "bars": 600,
                            "mode": "balanced"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "balanced"
    assert "trades" in d and isinstance(d["trades"], list)
    if d["trades"]:
        tr = d["trades"][0]
        assert "entry_time" in tr and "exit_time" in tr


def test_forwardtest_preset_highwinrate(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "USD/CAD", "timeframe": "H1", "bars": 600,
                            "mode": "highwinrate"}, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "highwinrate"


def test_forwardtest_preset_nosl(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "USD/CHF", "timeframe": "H1", "bars": 600,
                            "mode": "nosl"}, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "nosl"


def test_forwardtest_explicit_optimized_params(headers):
    payload = {"symbol": "EUR/USD", "timeframe": "H1", "bars": 600,
               "risk_percent": 0.75,
               "params": {"entry": "breakout", "tp_mult": 2.0,
                          "sl_mult": 2.5, "trend_filter": False}}
    r = requests.post(f"{API}/forwardtest/run", headers=headers, json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "optimized"
    if d["trades"]:
        tr = d["trades"][0]
        assert "entry_time" in tr and "exit_time" in tr


def test_watchlist_11_with_5_majors(headers):
    r = requests.get(f"{API}/market/watchlist", headers=headers, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 11, f"expected 11, got {len(items)}"
    symbols = {it.get("symbol") for it in items}
    present_majors = MAJORS & symbols
    assert len(present_majors) >= 5, f"expected >=5 forex majors, got {present_majors}"
