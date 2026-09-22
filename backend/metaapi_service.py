"""MetaApi (MetaTrader/Tickmill) data gateway with graceful fallback.

The rest of the app never calls MetaApi directly: it asks this module for real
candles/quotes and, if the broker terminal is not connected, gets None back and
falls back to simulated data. Kept intentionally best-effort and non-blocking.
"""
import os
import json
import time
import asyncio
import logging
import urllib.request

logger = logging.getLogger("metaapi")

TF_MAP = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
          "H1": "1h", "H4": "4h", "D1": "1d"}
SYMBOL_MAP = {
    "EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "XAU/USD": "XAUUSD",
    "USD/CHF": "USDCHF", "USD/CAD": "USDCAD", "AUD/USD": "AUDUSD",
    "BTC/USDT": "BTCUSD", "ETH/USDT": "ETHUSD",
    "NVDA": "NVDA", "AAPL": "AAPL", "US30": "US30",
}
PROVISIONING_HOST = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"

_state = {
    "connected": False,
    "last_error": None,
    "checked_at": 0.0,
    "account_name": None,
    "login": None,
    "server": None,
    "api": None,
    "account": None,
    "connection": None,
}
_CACHE_TTL = 30  # seconds


def _provisioning_status():
    token = os.environ.get("METAAPI_TOKEN")
    acc = os.environ.get("METAAPI_ACCOUNT_ID")
    if not token or not acc:
        return {"connected": False, "error": "Credenziali MetaApi mancanti"}
    url = f"{PROVISIONING_HOST}/users/current/accounts/{acc}"
    req = urllib.request.Request(url, headers={"auth-token": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        return {
            "connected": d.get("connectionStatus") == "CONNECTED",
            "state": d.get("state"),
            "connection_status": d.get("connectionStatus"),
            "name": d.get("name"),
            "login": d.get("login"),
            "server": d.get("server"),
            "error": None,
        }
    except Exception as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        return {"connected": False, "error": (str(e) + " " + body).strip()[:220]}


async def check_connected(force: bool = False) -> bool:
    now = time.time()
    if not force and (now - _state["checked_at"]) < _CACHE_TTL:
        return _state["connected"]
    res = await asyncio.to_thread(_provisioning_status)
    _state["checked_at"] = now
    _state["connected"] = bool(res.get("connected"))
    _state["last_error"] = res.get("error")
    _state["account_name"] = res.get("name")
    _state["login"] = res.get("login")
    _state["server"] = res.get("server")
    _state["connection_status"] = res.get("connection_status")
    return _state["connected"]


async def get_status() -> dict:
    token = os.environ.get("METAAPI_TOKEN")
    acc = os.environ.get("METAAPI_ACCOUNT_ID")
    await check_connected()
    return {
        "configured": bool(token and acc),
        "connected": _state["connected"],
        "connection_status": _state.get("connection_status"),
        "last_error": _state["last_error"],
        "account_id": acc,
        "account_name": _state.get("account_name"),
        "login": _state.get("login"),
        "server": _state.get("server"),
    }


async def _ensure_rpc():
    if _state["connection"] is not None:
        return _state["connection"]
    token = os.environ.get("METAAPI_TOKEN")
    acc = os.environ.get("METAAPI_ACCOUNT_ID")
    from metaapi_cloud_sdk import MetaApi
    if _state["api"] is None:
        _state["api"] = MetaApi(token)
    account = await _state["api"].metatrader_account_api.get_account(acc)
    _state["account"] = account
    conn = account.get_rpc_connection()
    await conn.connect()
    await asyncio.wait_for(conn.wait_synchronized(), timeout=25)
    _state["connection"] = conn
    return conn


async def _fetch_page(sym, tf, start_time, limit):
    """One backward page from the broker (candles with time < start_time)."""
    account = _state["account"]
    if account is None:
        await _ensure_rpc()
        account = _state["account"]
    rows = await asyncio.wait_for(
        account.get_historical_candles(symbol=sym, timeframe=tf, start_time=start_time, limit=limit),
        timeout=45,
    )
    return rows or []


def _norm(rows):
    out = []
    for r in rows:
        t = r.get("time")
        out.append({
            "time": t.isoformat() if hasattr(t, "isoformat") else str(t),
            "o": r.get("open"), "h": r.get("high"),
            "l": r.get("low"), "c": r.get("close"),
            "v": r.get("tickVolume", r.get("volume", 0)),
            "_t": t,
        })
    return out


async def fetch_candles(symbol: str, timeframe: str, n: int):
    """Return up to `n` candles {time,o,h,l,c,v} from the broker (or None).

    Loads history in backward pages (MetaApi caps a single call at ~1000
    candles) so multi-year windows (e.g. 5 years of D1) can be assembled.
    Retries once with a fresh RPC connection on timeout/error."""
    if not await check_connected():
        return None
    sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
    tf = TF_MAP.get(timeframe, "15m")
    for attempt in range(2):
        try:
            collected = []
            start_time = None
            seen = set()
            # page backward until we have `n` candles or the broker runs dry
            for _ in range(12):
                limit = min(1000, n - len(collected)) if n > len(collected) else 1000
                if limit <= 0:
                    break
                rows = await _fetch_page(sym, tf, start_time, min(1000, limit))
                if not rows:
                    break
                page = _norm(rows)
                page.sort(key=lambda x: x["time"])
                new = [c for c in page if c["time"] not in seen]
                if not new:
                    break
                for c in new:
                    seen.add(c["time"])
                collected = new + collected
                if len(rows) < 900 or len(collected) >= n:
                    break
                # next page ends just before the earliest candle we have
                earliest = page[0]["_t"]
                start_time = earliest
            if not collected:
                if attempt == 0:
                    _state["connection"] = None
                    continue
                return None
            collected.sort(key=lambda x: x["time"])
            for c in collected:
                c.pop("_t", None)
            return collected[-n:]
        except Exception as e:
            _state["last_error"] = str(e)[:220]
            logger.warning(f"MetaApi fetch_candles attempt {attempt} failed: {e}")
            _state["connection"] = None  # drop stale connection before retry
    return None


async def place_market_order(symbol: str, side: str, volume: float, sl=None, tp=None):
    """Execute a real market order on the connected demo account."""
    if not await check_connected():
        return {"ok": False, "error": "Account non connesso al broker"}
    try:
        conn = await _ensure_rpc()
        sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        fn = conn.create_market_buy_order if side.upper() == "BUY" else conn.create_market_sell_order
        result = await asyncio.wait_for(
            fn(symbol=sym, volume=volume, stop_loss=sl, take_profit=tp,
               options={"comment": "apexflow", "clientId": "apexflow-fwd"}),
            timeout=30,
        )
        return {"ok": True, "result": result}
    except Exception as e:
        _state["last_error"] = str(e)[:220]
        return {"ok": False, "error": str(e)[:220]}
