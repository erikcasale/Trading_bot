"""Backend tests for Forward-Test walk-forward engine + MetaApi datasource fallback."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://automated-forex-bot-2.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@apexflow.io", "password": "apexflow2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- datasource status -------------------------------------------------------
def test_datasource_status(headers):
    r = requests.get(f"{API}/datasource/status", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("configured") is True
    # broker connection state is dynamic; just verify field exists & is boolean
    assert isinstance(d.get("connected"), bool)
    assert "account_id" in d
    # Fields present (may be None if provisioning API failed, but keys should exist)
    for k in ("account_name", "login", "server", "connection_status", "last_error"):
        assert k in d


# --- forward-test EUR/USD ----------------------------------------------------
def test_forwardtest_eurusd(headers):
    r = requests.post(f"{API}/forwardtest/run",
                      headers=headers,
                      json={"symbol": "EUR/USD", "timeframe": "M15", "bars": 320},
                      timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] in ("simulated", "real")
    assert d["warmup"] == 45
    assert len(d["candles"]) == 320
    assert len(d["equity_curve"]) == len(d["candles"])
    for k in ("winrate", "total_trades", "profit_factor", "max_drawdown", "net_profit", "start_equity", "final_equity"):
        assert k in d
    assert 0 <= d["winrate"] <= 100
    assert d["total_trades"] >= 0
    assert isinstance(d["trades"], list)
    for t in d["trades"]:
        for k in ("entry_index", "exit_index", "side", "entry", "sl", "tp", "result", "pnl"):
            assert k in t, f"trade missing {k}: {t}"
        assert t["side"] in ("BUY", "SELL")
        assert t["result"] in ("win", "loss")


@pytest.mark.parametrize("sym", ["BTC/USDT", "XAU/USD", "US30"])
def test_forwardtest_multi_symbols(headers, sym):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": sym, "timeframe": "M15", "bars": 200}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] in ("simulated", "real")
    assert 0 <= d["winrate"] <= 100
    assert d["total_trades"] >= 0
    assert len(d["equity_curve"]) == len(d["candles"])


def test_forwardtest_invalid_symbol(headers):
    r = requests.post(f"{API}/forwardtest/run", headers=headers,
                      json={"symbol": "FAKE/XYZ", "timeframe": "M15", "bars": 200}, timeout=30)
    assert r.status_code == 404


# --- execute-live must not crash even when broker is disconnected -----------
def test_execute_live_disconnected(headers):
    r = requests.post(f"{API}/forwardtest/execute-live", headers=headers,
                      json={"symbol": "EUR/USD", "side": "BUY", "volume": 0.01}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is False
    assert "error" in d and d["error"]


def test_execute_live_invalid_symbol(headers):
    r = requests.post(f"{API}/forwardtest/execute-live", headers=headers,
                      json={"symbol": "FAKE/XYZ", "side": "BUY", "volume": 0.01}, timeout=30)
    assert r.status_code == 404
