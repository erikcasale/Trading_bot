"""Backend regression tests for Apex Flow API."""
import os
import time
import uuid
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
    return s


@pytest.fixture(scope="module")
def auth(session):
    r = session.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    session.headers.update({"Authorization": f"Bearer {data['token']}"})
    return data


# ---------- Auth ----------
class TestAuth:
    def test_login_ok(self, auth):
        assert auth["user"]["email"] == DEMO_EMAIL

    def test_login_wrong(self, session):
        r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": "wrong"}, timeout=10)
        assert r.status_code == 401

    def test_me(self, session, auth):
        r = session.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == DEMO_EMAIL

    def test_register_new(self, session):
        email = f"test_{uuid.uuid4().hex[:8]}@apexflow.io"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "pass1234", "name": "T"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == email

    def test_register_duplicate(self, session):
        r = requests.post(f"{API}/auth/register", json={"email": DEMO_EMAIL, "password": "x123456"}, timeout=10)
        assert r.status_code == 400

    def test_no_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401


# ---------- Market ----------
class TestMarket:
    def test_watchlist(self, session, auth):
        r = session.get(f"{API}/market/watchlist", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) == 8
        syms = {x["symbol"] for x in data}
        assert {"BTC/USDT", "XAU/USD", "EUR/USD"}.issubset(syms)

    @pytest.mark.parametrize("tf", ["M1", "M5", "M15", "H1", "H4", "D1"])
    def test_candles_tf(self, session, auth, tf):
        r = session.get(f"{API}/market/candles", params={"symbol": "BTC/USDT", "timeframe": tf}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "candles" in d and len(d["candles"]) > 50
        assert "zones" in d and "order_blocks" in d["zones"]

    def test_candles_invalid_symbol(self, session, auth):
        r = session.get(f"{API}/market/candles", params={"symbol": "FAKE/XYZ"}, timeout=10)
        assert r.status_code == 404


# ---------- AI Analysis ----------
class TestAI:
    def test_ai_analysis(self, session, auth):
        r = session.post(f"{API}/ai/analysis", json={"symbol": "BTC/USDT", "timeframe": "M15"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "analysis" in d
        a = d["analysis"]
        assert a["bias"] in ["bullish", "bearish", "neutral"]
        assert isinstance(a.get("score"), int)
        assert "setup" in a and "entry" in a["setup"] and "sl" in a["setup"]
        assert "tp1" in a["setup"] and "tp2" in a["setup"] and "tp3" in a["setup"]
        assert isinstance(a.get("narrative"), str) and len(a["narrative"]) > 10


# ---------- Bot ----------
class TestBot:
    def test_get_bot(self, session, auth):
        r = session.get(f"{API}/bot", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["bot"]["status"] in ["running", "stopped"]
        assert d["account"]["balance"] >= 0

    def test_toggle_bot(self, session, auth):
        r1 = session.get(f"{API}/bot", timeout=10).json()
        initial = r1["bot"]["status"]
        r2 = session.post(f"{API}/bot/toggle", timeout=10)
        assert r2.status_code == 200
        assert r2.json()["status"] != initial
        # verify persisted
        r3 = session.get(f"{API}/bot", timeout=10).json()
        assert r3["bot"]["status"] == r2.json()["status"]
        # toggle back
        session.post(f"{API}/bot/toggle", timeout=10)

    def test_update_bot(self, session, auth):
        cfg = {"winrate_filter": 97, "max_drawdown": 2.0, "risk_percent": 0.8,
               "max_open_trades": 4, "lot_mode": "fixed"}
        r = session.put(f"{API}/bot", json=cfg, timeout=10)
        assert r.status_code == 200
        assert r.json()["max_drawdown"] == 2.0
        # verify persisted
        r2 = session.get(f"{API}/bot", timeout=10).json()
        assert r2["bot"]["max_drawdown"] == 2.0
        assert r2["bot"]["lot_mode"] == "fixed"

    def test_stop_bot(self, session, auth):
        session.post(f"{API}/bot/toggle", timeout=10)  # start
        r = session.post(f"{API}/bot/stop", timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"


# ---------- Positions ----------
class TestPositions:
    def test_list(self, session, auth):
        r = session.get(f"{API}/positions", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["active"]) >= 1
        assert len(d["history"]) >= 1
        for p in d["active"]:
            assert p["status"] == "active"
            assert "pnl" in p and "current" in p

    def test_close_and_persist(self, session, auth):
        active = session.get(f"{API}/positions", timeout=15).json()["active"]
        assert active
        pid = active[0]["id"]
        r = session.post(f"{API}/positions/{pid}/close", timeout=10)
        assert r.status_code == 200
        # verify moved to history
        d = session.get(f"{API}/positions", timeout=15).json()
        assert pid not in [p["id"] for p in d["active"]]
        assert pid in [p["id"] for p in d["history"]]

    def test_close_invalid(self, session, auth):
        r = session.post(f"{API}/positions/nonexistent-id/close", timeout=10)
        assert r.status_code == 404


# ---------- Backtest ----------
class TestBacktest:
    def test_backtest(self, session, auth):
        r = session.post(f"{API}/backtest", json={"symbol": "EUR/USD", "period": "1Y"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert 90 <= d["winrate"] <= 100
        assert d["total_trades"] > 0
        assert len(d["equity_curve"]) > 5
        assert len(d["log"]) >= 5

    def test_backtest_invalid_symbol(self, session, auth):
        r = session.post(f"{API}/backtest", json={"symbol": "XX", "period": "6M"}, timeout=10)
        assert r.status_code == 404
