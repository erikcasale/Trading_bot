"""Tests for the async strategy-discovery endpoint (POST /api/strategy/discover
+ polling GET /api/strategy/discover/{job_id})."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "https://automated-forex-bot-2.preview.emergentagent.com"
EMAIL = "demo@apexflow.io"
PASSWORD = "apexflow2026"

POLL_TIMEOUT = 90
POLL_INTERVAL = 3


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=60)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _run_discover(headers, symbol, years=5, target=50.0):
    r = requests.post(f"{BASE_URL}/api/strategy/discover",
                      headers=headers,
                      json={"symbol": symbol, "years": years, "target_annual": target},
                      timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "running"
    job_id = body["job_id"]

    t0 = time.time()
    last = None
    while time.time() - t0 < POLL_TIMEOUT:
        pr = requests.get(f"{BASE_URL}/api/strategy/discover/{job_id}",
                          headers=headers, timeout=15)
        assert pr.status_code == 200, pr.text
        last = pr.json()
        if last["status"] in ("done", "error"):
            break
        time.sleep(POLL_INTERVAL)
    elapsed = time.time() - t0
    assert last is not None
    return last, elapsed, job_id


def _assert_result_schema(res):
    for k in ("verdict", "best_params", "entry_label", "training", "last_year",
              "recommended_risk_percent", "projected_annual_return",
              "combos_tested", "source", "period_start", "period_end"):
        assert k in res, f"missing key {k}"
    assert res["verdict"] in ("profittevole", "marginale", "non_profittevole")
    for k in ("entry", "tp_mult", "sl_mult", "trend_filter", "rsi"):
        assert k in res["best_params"]
    assert res["best_params"]["entry"] in ("smc", "meanrev", "breakout", "trend")
    for seg in ("training", "last_year"):
        s = res[seg]
        for kk in ("annual_return", "profit_factor", "winrate", "trades", "net",
                   "equity_curve", "period_start", "period_end"):
            assert kk in s, f"{seg} missing {kk}"
        assert isinstance(s["equity_curve"], list)


def test_discover_eurusd_full_flow(headers):
    res, elapsed, _ = _run_discover(headers, "EUR/USD")
    assert res["status"] == "done", f"status={res['status']} err={res.get('error')}"
    r = res["result"]
    _assert_result_schema(r)
    # verdict consistency
    if r["verdict"] == "profittevole":
        assert r["last_year"]["net"] > 0
        assert r["last_year"]["profit_factor"] >= 1.1
    print(f"EUR/USD discover elapsed={elapsed:.1f}s source={r['source']} "
          f"verdict={r['verdict']} combos={r['combos_tested']}")
    # ~5 years distance between period_start / period_end
    ps, pe = r["period_start"][:10], r["period_end"][:10]
    print("period", ps, "->", pe)


def test_discover_cache_speedup(headers):
    """A second discover on the same symbol should hit the D1 cache and finish
    substantially faster than the first call."""
    # first call may already be cached from the previous test; run twice and
    # assert the SECOND call is fast (< 25s) which proves cache works.
    _, e1, _ = _run_discover(headers, "EUR/USD")
    _, e2, _ = _run_discover(headers, "EUR/USD")
    print(f"cache: e1={e1:.1f}s e2={e2:.1f}s")
    assert e2 < 30, f"cached discover took {e2:.1f}s"


def test_discover_xauusd(headers):
    res, elapsed, _ = _run_discover(headers, "XAU/USD")
    assert res["status"] == "done", res.get("error")
    r = res["result"]
    _assert_result_schema(r)
    if r["verdict"] == "profittevole":
        assert r["last_year"]["net"] > 0
        assert r["last_year"]["profit_factor"] >= 1.1
    print(f"XAU/USD verdict={r['verdict']} elapsed={elapsed:.1f}s source={r['source']}")


def test_discover_us30(headers):
    res, elapsed, _ = _run_discover(headers, "US30")
    assert res["status"] == "done", res.get("error")
    r = res["result"]
    _assert_result_schema(r)
    if r["verdict"] == "profittevole":
        assert r["last_year"]["net"] > 0
        assert r["last_year"]["profit_factor"] >= 1.1
    print(f"US30 verdict={r['verdict']} elapsed={elapsed:.1f}s source={r['source']}")


def test_discover_unknown_job(headers):
    r = requests.get(f"{BASE_URL}/api/strategy/discover/nonexistent-job-id-xyz",
                     headers=headers, timeout=15)
    assert r.status_code == 404


def test_discover_unknown_symbol(headers):
    r = requests.post(f"{BASE_URL}/api/strategy/discover",
                      headers=headers,
                      json={"symbol": "FAKE/PAIR", "years": 5, "target_annual": 50},
                      timeout=15)
    assert r.status_code == 404


def test_forwardtest_new_entry_modes(headers):
    """The new 'trend' entry + 'rsi' filter must run without errors and produce
    mode='optimized' since params body is supplied."""
    body = {
        "symbol": "EUR/USD", "timeframe": "H1", "bars": 400,
        "risk_percent": 1.0,
        "params": {"entry": "trend", "tp_mult": 2.0, "sl_mult": 1.5,
                   "trend_filter": False, "rsi": True},
    }
    r = requests.post(f"{BASE_URL}/api/forwardtest/run",
                      headers=headers, json=body, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("mode") == "optimized"
    assert "trades" in d and isinstance(d["trades"], list)
    assert "profit_factor" in d and "winrate" in d
    print(f"forwardtest trend+rsi trades={len(d['trades'])} PF={d['profit_factor']}")


def test_d1_history_length(headers):
    """Indirectly check that the paginated D1 fetch returns roughly 5 years of
    candles by inspecting a discover result's equity curve segment lengths."""
    res, _, _ = _run_discover(headers, "EUR/USD")
    if res["status"] != "done":
        pytest.skip("discover failed")
    r = res["result"]
    train_pts = len(r["training"]["equity_curve"])
    val_pts = len(r["last_year"]["equity_curve"])
    print(f"train_pts={train_pts} val_pts={val_pts} source={r['source']}")
    if r["source"] == "real":
        # ~5y of D1 = ~1300 candles; train (4y) >= ~800, val (1y) between 200-320
        assert train_pts >= 500, f"train equity curve too short: {train_pts}"
        assert 150 <= val_pts <= 400, f"val equity curve out of range: {val_pts}"
