"""Backend tests for /api/portfolio/backtest async job."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://automated-forex-bot-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_EMAIL = "demo@apexflow.io"
DEMO_PASSWORD = "apexflow2026"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


# --- datasource / account sanity ---
def test_datasource_connected(session):
    r = session.get(f"{API}/datasource/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("connected") is True, d


def test_bot_account_real(session):
    r = session.get(f"{API}/bot", timeout=15)
    assert r.status_code == 200
    d = r.json()
    acc = d.get("account") or {}
    assert acc.get("real") is True, acc
    assert acc.get("currency") in ("EUR", "USD"), acc
    assert "positions" in acc and isinstance(acc["positions"], list)


# --- portfolio backtest ---
def test_portfolio_backtest_unknown_id_404(session):
    r = session.get(f"{API}/portfolio/backtest/does-not-exist", timeout=15)
    assert r.status_code == 404


@pytest.fixture(scope="module")
def portfolio_result(session):
    # walk_forward True (default) - retrain each year
    payload = {"start_date": "2025-01-01", "start_balance": 10000, "risk_percent": 1.5, "walk_forward": True}
    r = session.post(f"{API}/portfolio/backtest", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "job_id" in d and d["status"] == "running" and d["total"] == 7
    job_id = d["job_id"]
    # poll up to ~4 minutes
    last = None
    for _ in range(120):  # 120 * 2.5s = 300s
        rr = session.get(f"{API}/portfolio/backtest/{job_id}", timeout=15)
        assert rr.status_code == 200
        last = rr.json()
        st = last.get("status")
        if st == "done":
            return last
        if st == "error":
            pytest.fail(f"job errored: {last.get('error')}")
        time.sleep(2.5)
    pytest.fail(f"job did not finish in time, last={last}")


def test_portfolio_result_shape(portfolio_result):
    r = portfolio_result.get("result")
    assert r is not None
    for k in ["start_date", "end_date", "days", "start_balance", "final_balance",
              "net_profit", "return_percent", "annualized_percent", "max_drawdown",
              "total_trades", "winrate", "open_trades", "per_symbol",
              "real_symbols", "sim_symbols", "equity_curve"]:
        assert k in r, f"missing {k}"
    assert r["start_balance"] == 10000
    assert isinstance(r["per_symbol"], list) and len(r["per_symbol"]) == 7
    for row in r["per_symbol"]:
        for k in ["symbol", "entry_label", "trades", "net"]:
            assert k in row


def test_portfolio_result_consistency(portfolio_result):
    r = portfolio_result["result"]
    # final_balance ≈ start_balance + net_profit
    assert abs(r["final_balance"] - (r["start_balance"] + r["net_profit"])) < 5.0
    # sum(per_symbol.net) ≈ net_profit (allow for open pnl in equity but here they should match net_profit closely)
    s = sum(row["net"] for row in r["per_symbol"])
    assert abs(s - r["net_profit"]) < max(50.0, abs(r["net_profit"]) * 0.05), (s, r["net_profit"])
    # real symbols should cover most of the 7 when MetaApi is connected
    assert len(r["real_symbols"]) >= 4, r["real_symbols"]


# --- walk_forward specific ---
def test_walk_forward_true_flag_and_retrains(portfolio_result):
    r = portfolio_result["result"]
    assert r.get("walk_forward") is True
    # start=2025, and end year should be 2026, so >=2 segments -> retrains >=2 for each symbol with data
    for row in r["per_symbol"]:
        assert "retrains" in row, row
        assert row["retrains"] >= 2, row


def test_walk_forward_trades_list(portfolio_result):
    r = portfolio_result["result"]
    trades = r.get("trades")
    assert isinstance(trades, list) and len(trades) > 0
    # trades list >= total_trades (includes open)
    assert len(trades) >= r["total_trades"]
    for t in trades:
        for k in ["symbol", "side", "entry_date", "exit_date", "result", "r", "net"]:
            assert k in t, t
        assert t["entry_date"] <= t["exit_date"], t


def test_real_symbols_mostly_covered(portfolio_result):
    r = portfolio_result["result"]
    # with MetaApi connected and retry logic, expect 6/7 or 7/7 real
    assert len(r["real_symbols"]) >= 6, (r["real_symbols"], r["sim_symbols"])


@pytest.fixture(scope="module")
def portfolio_result_no_wf(session):
    payload = {"start_date": "2025-01-01", "start_balance": 10000, "risk_percent": 1.5, "walk_forward": False}
    r = session.post(f"{API}/portfolio/backtest", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    last = None
    for _ in range(150):
        rr = session.get(f"{API}/portfolio/backtest/{job_id}", timeout=15)
        assert rr.status_code == 200
        last = rr.json()
        st = last.get("status")
        if st == "done":
            return last
        if st == "error":
            pytest.fail(f"job errored: {last.get('error')}")
        time.sleep(2.5)
    pytest.fail(f"job did not finish in time, last={last}")


def test_walk_forward_false_flag_and_retrains(portfolio_result_no_wf):
    r = portfolio_result_no_wf["result"]
    assert r.get("walk_forward") is False
    for row in r["per_symbol"]:
        assert row.get("retrains") == 1, row


def test_walk_forward_false_consistency(portfolio_result_no_wf):
    r = portfolio_result_no_wf["result"]
    assert abs(r["final_balance"] - (r["start_balance"] + r["net_profit"])) < 5.0
    s = sum(row["net"] for row in r["per_symbol"])
    assert abs(s - r["net_profit"]) < max(50.0, abs(r["net_profit"]) * 0.05)
