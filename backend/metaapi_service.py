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
    "EUR/GBP": "EURGBP", "EUR/AUD": "EURAUD", "EUR/CHF": "EURCHF",
    "EUR/CAD": "EURCAD", "GBP/AUD": "GBPAUD", "GBP/CHF": "GBPCHF",
    "AUD/CAD": "AUDCAD",
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


_price_cache = {"ts": 0.0, "data": {}}
_dref_cache = {"ts": 0.0, "data": {}}
_acct_cache = {"ts": 0.0, "data": None}
_refs_lock = asyncio.Lock()
_real_symbols = set()  # symbols that have ever returned a real broker price


_REV_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}
_pos_cache = {"ts": 0.0, "data": None}


async def get_positions():
    """Real open positions [{symbol, side, volume, profit, open_price,
    current_price}] from the broker, or None if unavailable. Cached 5s."""
    now = time.time()
    if (now - _pos_cache["ts"]) < 5 and _pos_cache["data"] is not None:
        return _pos_cache["data"]
    if not await check_connected():
        return None
    try:
        conn = await _ensure_rpc()
        rows = await asyncio.wait_for(conn.get_positions(), timeout=8)
        out = []
        for p in (rows or []):
            broker_sym = p.get("symbol", "")
            typ = str(p.get("type", "")).upper()
            t = p.get("time")
            out.append({
                "id": str(p.get("id", "")),
                "symbol": _REV_SYMBOL.get(broker_sym, broker_sym),
                "side": "SELL" if "SELL" in typ else "BUY",
                "volume": p.get("volume"),
                "profit": round(p.get("profit", 0), 2),
                "open_price": p.get("openPrice"),
                "current_price": p.get("currentPrice"),
                "tp": p.get("takeProfit"),
                "swap": round(p.get("swap", 0) or 0, 2),
                "comment": p.get("comment") or p.get("clientId") or "",
                "time": t.isoformat() if hasattr(t, "isoformat") else (str(t) if t else None),
            })
        _pos_cache.update({"ts": now, "data": out})
        return out
    except Exception as e:
        _state["last_error"] = str(e)[:200]
        _state["connection"] = None
        if _pos_cache["data"] is not None and (time.time() - _pos_cache["ts"]) < 60:
            return _pos_cache["data"]
        return None


async def get_account_info():
    """Real MT5 account {balance, equity, currency, margin, free_margin,
    leverage, profit} from the broker, or None if unavailable. Cached 8s."""
    now = time.time()
    if (now - _acct_cache["ts"]) < 8 and _acct_cache["data"]:
        return _acct_cache["data"]
    if not await check_connected():
        return None
    try:
        conn = await _ensure_rpc()
        info = await asyncio.wait_for(conn.get_account_information(), timeout=8)
        if not info or info.get("equity") is None:
            return None
        bal = round(info.get("balance", 0), 2)
        eq = round(info.get("equity", 0), 2)
        prof = info.get("profit")
        prof = round(prof if prof is not None else (eq - bal), 2)
        data = {
            "balance": bal,
            "equity": eq,
            "currency": info.get("currency", "USD"),
            "margin": round(info.get("margin", 0), 2),
            "free_margin": round(info.get("freeMargin", 0), 2),
            "leverage": info.get("leverage"),
            "profit": prof,
        }
        _acct_cache.update({"ts": now, "data": data})
        return data
    except Exception as e:
        _state["last_error"] = str(e)[:200]
        _state["connection"] = None
        # serve last-known account on transient failure (avoid real->demo flicker)
        if _acct_cache["data"] and (time.time() - _acct_cache["ts"]) < 60:
            return _acct_cache["data"]
        return None


def is_configured():
    return bool(os.environ.get("METAAPI_TOKEN") and os.environ.get("METAAPI_ACCOUNT_ID"))


def known_real(app_sym):
    return app_sym in _real_symbols


async def get_prices(symbols):
    """Live {app_symbol: {price, bid, ask}} from the broker (or {} if down).
    Cached 4s so frequent polling doesn't hammer the RPC connection."""
    now = time.time()
    if (now - _price_cache["ts"]) < 6 and _price_cache["data"]:
        return _price_cache["data"]
    if not await check_connected():
        return {}
    try:
        conn = await _ensure_rpc()
    except Exception:
        return {}
    out = {}

    async def one(app_sym):
        sym = SYMBOL_MAP.get(app_sym, app_sym.replace("/", ""))
        try:
            p = await asyncio.wait_for(conn.get_symbol_price(sym), timeout=3)
            bid, ask = p.get("bid"), p.get("ask")
            if bid is None:
                return
            out[app_sym] = {"bid": bid, "ask": ask,
                            "price": round((bid + ask) / 2, 5) if ask else bid}
            _real_symbols.add(app_sym)
        except Exception as e:
            _state["last_error"] = str(e)[:180]

    await asyncio.gather(*[one(s) for s in symbols])
    if out:
        _price_cache.update({"ts": now, "data": out})
    return out


async def fetch_candles_before(symbol: str, timeframe: str, end_time, n: int):
    """Fetch up to `n` candles ending at/around `end_time` (a datetime), for
    drilling into the exact intraday moment SL/TP was touched."""
    if not await check_connected():
        return None
    sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
    tf = TF_MAP.get(timeframe, "1h")
    try:
        rows = await _fetch_page(sym, tf, end_time, min(max(n, 24), 1000))
        if not rows:
            return None
        page = _norm(rows)
        page.sort(key=lambda x: x["time"])
        for c in page:
            c.pop("_t", None)
        return page
    except Exception as e:
        _state["last_error"] = str(e)[:220]
        _state["connection"] = None
        return None


async def get_daily_refs(symbols):
    """Yesterday's D1 close per symbol (for daily change %). Cached 120s.
    Fetched in parallel with a short timeout so one slow/failing symbol
    (e.g. BTCUSD not available) never blocks the whole watchlist."""
    now = time.time()
    if (now - _dref_cache["ts"]) < 120 and _dref_cache["data"]:
        return _dref_cache["data"]
    async with _refs_lock:
        # another concurrent caller may have just populated it
        now = time.time()
        if (now - _dref_cache["ts"]) < 120 and _dref_cache["data"]:
            return _dref_cache["data"]
        if not await check_connected():
            return {}
        try:
            await _ensure_rpc()
        except Exception:
            return {}
        account = _state["account"]
        refs = {}

        async def one(app_sym):
            sym = SYMBOL_MAP.get(app_sym, app_sym.replace("/", ""))
            try:
                rows = await asyncio.wait_for(
                    account.get_historical_candles(symbol=sym, timeframe="1d", start_time=None, limit=2),
                    timeout=8)
                if rows and len(rows) >= 2:
                    refs[app_sym] = rows[-2].get("close")
            except Exception:
                pass

        await asyncio.gather(*[one(s) for s in symbols])
        if refs:
            _dref_cache.update({"ts": now, "data": refs})
        return refs


def cached_daily_refs():
    """Return the daily-change reference cache without triggering a fetch."""
    if (time.time() - _dref_cache["ts"]) < 300 and _dref_cache["data"]:
        return _dref_cache["data"]
    return {}


async def warm_up():
    """Establish the RPC connection ahead of the first user request so cold
    starts don't silently fall back to simulated data. Also primes the live
    price and daily-change caches so the first watchlist load is instant."""
    try:
        if not await check_connected(force=True):
            return False
        await _ensure_rpc()
        syms = list(SYMBOL_MAP.keys())
        try:
            await get_prices(syms)
            await get_daily_refs(syms)
        except Exception:
            pass
        return True
    except Exception as e:
        _state["last_error"] = str(e)[:220]
        logger.warning(f"MetaApi warm_up failed: {e}")
        _state["connection"] = None
        return False


async def place_market_order(symbol: str, side: str, volume: float, sl=None, tp=None, comment="apexflow"):
    """Execute a real market order on the connected demo account."""
    if not await check_connected():
        return {"ok": False, "error": "Account non connesso al broker"}
    try:
        conn = await _ensure_rpc()
        sym = SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        fn = conn.create_market_buy_order if side.upper() == "BUY" else conn.create_market_sell_order
        result = await asyncio.wait_for(
            fn(symbol=sym, volume=volume, stop_loss=sl, take_profit=tp,
               options={"comment": comment[:26]}),
            timeout=30,
        )
        _pos_cache["ts"] = 0.0  # invalidate so the new position shows immediately
        return {"ok": True, "result": result}
    except Exception as e:
        details = getattr(e, "details", None) or getattr(e, "args", None)
        logger.warning("place_market_order failed: %s | details=%s", e, details)
        _state["last_error"] = str(e)[:220]
        return {"ok": False, "error": str(e)[:220], "details": str(details)[:400]}


async def close_position(position_id: str):
    """Close an open position by id at market on the connected demo account."""
    if not await check_connected():
        return {"ok": False, "error": "Account non connesso al broker"}
    try:
        conn = await _ensure_rpc()
        result = await asyncio.wait_for(conn.close_position(str(position_id)), timeout=30)
        _pos_cache["ts"] = 0.0
        return {"ok": True, "result": result}
    except Exception as e:
        _state["last_error"] = str(e)[:220]
        return {"ok": False, "error": str(e)[:220]}


async def get_closed_deals(days: int = 120):
    """Realized closing deals (round-trip P&L) from broker history, newest first.
    Returns list [{symbol, side, volume, profit, price, time, comment, position_id}]
    or None if unavailable."""
    if not await check_connected():
        return None
    try:
        import datetime as _dt
        conn = await _ensure_rpc()
        end = _dt.datetime.now(_dt.timezone.utc)
        start = end - _dt.timedelta(days=days)
        res = await asyncio.wait_for(conn.get_deals_by_time_range(start, end), timeout=20)
        deals = res.get("deals", res) if isinstance(res, dict) else res
        out = []
        for d in (deals or []):
            if str(d.get("entryType", "")).upper() != "DEAL_ENTRY_OUT":
                continue
            broker_sym = d.get("symbol", "")
            typ = str(d.get("type", "")).upper()  # closing deal type is opposite of position side
            t = d.get("time")
            out.append({
                "symbol": _REV_SYMBOL.get(broker_sym, broker_sym),
                "side": "BUY" if "SELL" in typ else "SELL",  # original position side
                "volume": d.get("volume"),
                "profit": round((d.get("profit", 0) or 0) + (d.get("swap", 0) or 0) + (d.get("commission", 0) or 0), 2),
                "price": d.get("price"),
                "time": t.isoformat() if hasattr(t, "isoformat") else (str(t) if t else None),
                "comment": d.get("comment") or d.get("brokerComment") or "",
                "position_id": str(d.get("positionId", "")),
            })
        out.sort(key=lambda x: x["time"] or "", reverse=True)
        return out
    except Exception as e:
        _state["last_error"] = str(e)[:220]
        _state["connection"] = None
        return None
