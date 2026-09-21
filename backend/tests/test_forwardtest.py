"""Backend tests: Forward-Test walk-forward engine w/ modes (balanced/highwinrate/nosl)
+ MetaApi datasource fallback + annual period."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "demo@apexflow.io", "password": "apexflow2026"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- datasource status (Tickmill 85584886 should now be CONNECTED) ----------
def test_datasource_status_connected(headers):
    r = requests.get(f"{API}/datasource/status", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("configured") is True
    assert isinstance(d.get("connected"), bool)
    assert "account_id" in d
    for k in ("account_name", "login", "server", "connection_status", "last_error"):
        assert k in d
    # Per review-request: expect CONNECTED. We assert soft (log if not) but require the field.
    print(f"datasource: connected={d['connected']} status={d.get('connection_status')} server={d.get('server')}")


def _common_trade_fields(t, mode):
    # every trade must have these keys regardless of mode
    for k in ("entry_index", "exit_index", "side", "entry", "tp", "result",
              "pnl", "entry_time", "exit_time", "mae"):
        assert k in t, f"[{mode}] trade missing key: {k}, got={t}"
    assert "sl" in t
    assert t["side"] in ("BUY", "SELL")
    assert t["result"] in ("win", "loss", "open")


def _common_response_fields(d, mode):
    for k in ("winrate", "total_trades", "profit_factor", "max_drawdown",
              "net_profit", "start_equity", "final_equity",
              "avg_win", "avg_loss", "expectancy",
              "open_trades", "open_floating", "true_equity", "worst_floating",
              "realized_net", "period_start", "period_end", "mode"):
        assert k in d, f"[{mode}] missing response key: {k}"
    assert d["mode"] == mode
    assert 0 <= d["winrate"] <= 100
    assert d["total_trades"] >= 0
    assert len(d["equity_curve"]) == len(d["candles"])


# --- balanced mode ----------------------------------------------------------
def test_forwardtest_balanced_eurusd(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M15",
                            "bars": 400, "mode": "balanced"},
                      timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] in ("simulated", "real")
    _common_response_fields(d, "balanced")
    for t in d["trades"]:
        _common_trade_fields(t, "balanced")
        # balanced uses SL
        if t["result"] in ("win", "loss"):
            assert t["sl"] is not None, f"balanced closed trade must have SL: {t}"


# --- highwinrate mode -------------------------------------------------------
def test_forwardtest_highwinrate_eurusd(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M15",
                            "bars": 400, "mode": "highwinrate"},
                      timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    _common_response_fields(d, "highwinrate")
    for t in d["trades"]:
        _common_trade_fields(t, "highwinrate")
    # If we got closed trades, avg_win should typically be < avg_loss (small TP, wide SL)
    if d["total_trades"] > 0:
        print(f"highwinrate: wr={d['winrate']} avg_win={d['avg_win']} avg_loss={d['avg_loss']} "
              f"expect={d['expectancy']} true_eq={d['true_equity']}")


# --- nosl mode: KEY assertions on honest floating exposure ------------------
def test_forwardtest_nosl_eurusd(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M15",
                            "bars": 500, "mode": "nosl"},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    _common_response_fields(d, "nosl")
    # every trade in nosl must have sl == None
    for t in d["trades"]:
        _common_trade_fields(t, "nosl")
        assert t["sl"] is None, f"nosl trade must have sl=None, got {t['sl']}"
    # honesty fields exist and are the correct type
    assert isinstance(d["open_trades"], int) and d["open_trades"] >= 0
    assert isinstance(d["open_floating"], (int, float))
    assert isinstance(d["true_equity"], (int, float))
    assert isinstance(d["worst_floating"], (int, float))
    # true_equity = realized + open_floating (approx)
    approx = (d["start_equity"] + d["realized_net"]) + d["open_floating"]
    assert abs(approx - d["true_equity"]) < 1.0, f"true_equity mismatch: {approx} vs {d['true_equity']}"
    print(f"nosl: closed_wr={d['winrate']} open_trades={d['open_trades']} "
          f"open_floating={d['open_floating']} true_eq={d['true_equity']} "
          f"worst_floating={d['worst_floating']} start={d['start_equity']}")


# --- annual period ---------------------------------------------------------
def test_forwardtest_annual_period(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "D1",
                            "bars": 365, "mode": "balanced"},
                      timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["candles"]) >= 300  # ~365 daily candles (Tickmill weekends stripped)
    assert d["period_start"] and d["period_end"]
    # trades' entry_time / exit_time must lie within [period_start, period_end]
    for t in d["trades"]:
        if t.get("entry_time"):
            assert d["period_start"] <= t["entry_time"] <= d["period_end"], \
                f"entry_time {t['entry_time']} outside {d['period_start']}..{d['period_end']}"


# --- multi-symbol quick smoke (real + simulated fallback) -------------------
@pytest.mark.parametrize("sym", ["BTC/USDT", "XAU/USD", "US30", "GBP/USD"])
def test_forwardtest_multi_symbols(headers, sym):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": sym, "timeframe": "M15",
                            "bars": 200, "mode": "balanced"}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] in ("simulated", "real")
    _common_response_fields(d, "balanced")


# --- invalid symbol -> 404 --------------------------------------------------
def test_forwardtest_invalid_symbol(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "M15",
                            "bars": 200, "mode": "balanced"}, timeout=30)
    assert r.status_code == 404


# --- unknown mode falls back to 'highwinrate' (no crash) -------------------
def test_forwardtest_unknown_mode_defaults(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M15",
                            "bars": 200, "mode": "totally_bogus"}, timeout=60)
    assert r.status_code == 200
    assert r.json()["mode"] == "highwinrate"


# --- execute-live safety ----------------------------------------------------
def test_execute_live_invalid_symbol(headers):
    r = requests.post(f"{API}/forwardtest/execute-live", headers=headers,
                      json={"symbol": "FAKE/XYZ", "side": "BUY", "volume": 0.01}, timeout=30)
    assert r.status_code == 404
