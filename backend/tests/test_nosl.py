"""Backend tests for /api/portfolio/nosl (No-Stop-Loss compounding backtest)."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://automated-forex-bot-2.preview.emergentagent.com").rstrip("/")
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


@pytest.fixture(scope="module")
def nosl_result(session):
    """Run the nosl job once and reuse the completed result across tests."""
    r = session.post(f"{API}/portfolio/nosl",
                     json={"start_date": "2026-01-01", "start_balance": 10000, "lot_per_10k": 0.1},
                     timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "running"
    assert body.get("total") == 7
    assert "job_id" in body
    job_id = body["job_id"]

    # Poll up to ~7 minutes (cold cache: sequential 5y*7 fetches + retries)
    deadline = time.time() + 420
    last = None
    while time.time() < deadline:
        gr = session.get(f"{API}/portfolio/backtest/{job_id}", timeout=30)
        assert gr.status_code == 200, gr.text
        st = gr.json()
        # Serialization: task should NEVER appear
        assert "task" not in st, f"Response leaks 'task' field: {list(st.keys())}"
        last = st
        if st.get("status") == "done":
            return st
        if st.get("status") == "error":
            pytest.fail(f"nosl job errored: {st.get('error')}")
        time.sleep(6)
    pytest.fail(f"nosl job did not complete within deadline. Last status: {last}")


# --- endpoint / plumbing tests ---
def test_nosl_start_returns_job(session):
    r = session.post(f"{API}/portfolio/nosl",
                     json={"start_date": "2026-01-01", "start_balance": 10000, "lot_per_10k": 0.1},
                     timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "running"
    assert d["total"] == 7
    assert isinstance(d["job_id"], str) and len(d["job_id"]) > 10


def test_get_nonexistent_job_404(session):
    r = session.get(f"{API}/portfolio/backtest/does-not-exist-{int(time.time())}", timeout=15)
    assert r.status_code == 404


# --- result shape ---
def test_nosl_result_mode_and_shape(nosl_result):
    r = nosl_result["result"]
    assert r["mode"] == "nosl_compound"
    for key in ("realized_balance", "true_equity", "net_true", "return_true_percent",
                "open_trades", "open_floating", "tp_wins", "closed_trades",
                "max_drawdown", "min_equity", "wiped", "per_symbol",
                "real_symbols", "sim_symbols", "equity_curve", "start_date",
                "end_date", "start_balance", "lot_per_10k"):
        assert key in r, f"missing key {key}"
    assert r["start_balance"] == 10000
    assert r["lot_per_10k"] == 0.1
    assert isinstance(r["per_symbol"], list)
    assert isinstance(r["equity_curve"], list) and len(r["equity_curve"]) > 0
    # 7 portfolio symbols split between real & sim
    assert len(r["real_symbols"]) + len(r["sim_symbols"]) <= 7
    assert isinstance(r["wiped"], bool)
    if r["wiped"]:
        assert r["wipe_date"] is not None


def test_nosl_closed_equals_tp_wins(nosl_result):
    """No SL => every closed trade is a TP."""
    r = nosl_result["result"]
    assert r["closed_trades"] == r["tp_wins"]


def test_nosl_realized_plus_floating_equals_true_equity(nosl_result):
    """Coherence: realized_balance + open_floating ~= true_equity (rounding tolerated)."""
    r = nosl_result["result"]
    est = r["realized_balance"] + r["open_floating"]
    diff = abs(est - r["true_equity"])
    # allow up to €5 rounding / last-bar drift across 7 symbols
    assert diff <= 5.0, f"|realized+float - true| = {diff} (realized={r['realized_balance']} float={r['open_floating']} true={r['true_equity']})"


def test_nosl_return_percent_matches_true_equity(nosl_result):
    r = nosl_result["result"]
    expected = round((r["true_equity"] - r["start_balance"]) / r["start_balance"] * 100, 1)
    assert abs(r["return_true_percent"] - expected) <= 0.2


def test_nosl_wiped_flag_consistency(nosl_result):
    r = nosl_result["result"]
    if r["min_equity"] <= 0:
        assert r["wiped"] is True and r["wipe_date"] is not None
    else:
        assert r["wiped"] is False


def test_nosl_no_task_field_in_get(session, nosl_result):
    """After completion the job dict must still not leak the asyncio Task."""
    # nosl_result fixture guarantees the last GET didn't have 'task'.
    # Additionally verify final GET again.
    # Find any running job_id via a fresh start would take too long; assert on completed result envelope
    assert "task" not in nosl_result, list(nosl_result.keys())
