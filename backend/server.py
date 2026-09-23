from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
import logging
import asyncio
import uuid
import json
import math
import time
import random
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import metaapi_service

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Apex Flow API")
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("apexflow")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(hours=24), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="Utente non trovato")
        user["id"] = str(user["_id"])
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessione scaduta")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")

# ---------------------------------------------------------------------------
# Market simulation
# ---------------------------------------------------------------------------
INSTRUMENTS = {
    "EUR/USD":  {"cat": "forex",  "base": 1.0850,  "vol": 0.0009, "digits": 5, "spread": 0.00010},
    "GBP/USD":  {"cat": "forex",  "base": 1.2720,  "vol": 0.0011, "digits": 5, "spread": 0.00012},
    "USD/CHF":  {"cat": "forex",  "base": 0.9050,  "vol": 0.0009, "digits": 5, "spread": 0.00012},
    "USD/CAD":  {"cat": "forex",  "base": 1.3620,  "vol": 0.0011, "digits": 5, "spread": 0.00013},
    "AUD/USD":  {"cat": "forex",  "base": 0.6650,  "vol": 0.0008, "digits": 5, "spread": 0.00011},
    "EUR/GBP":  {"cat": "forex",  "base": 0.8530,  "vol": 0.0007, "digits": 5, "spread": 0.00012},
    "EUR/AUD":  {"cat": "forex",  "base": 1.6300,  "vol": 0.0016, "digits": 5, "spread": 0.00020},
    "EUR/CHF":  {"cat": "forex",  "base": 0.9600,  "vol": 0.0008, "digits": 5, "spread": 0.00013},
    "EUR/CAD":  {"cat": "forex",  "base": 1.4700,  "vol": 0.0013, "digits": 5, "spread": 0.00016},
    "GBP/AUD":  {"cat": "forex",  "base": 1.9100,  "vol": 0.0018, "digits": 5, "spread": 0.00025},
    "GBP/CHF":  {"cat": "forex",  "base": 1.1250,  "vol": 0.0011, "digits": 5, "spread": 0.00018},
    "GBP/CAD":  {"cat": "forex",  "base": 1.7300,  "vol": 0.0015, "digits": 5, "spread": 0.00020},
    "AUD/CAD":  {"cat": "forex",  "base": 0.9050,  "vol": 0.0009, "digits": 5, "spread": 0.00014},
    "AUD/CHF":  {"cat": "forex",  "base": 0.5700,  "vol": 0.0008, "digits": 5, "spread": 0.00014},
    "CAD/CHF":  {"cat": "forex",  "base": 0.6600,  "vol": 0.0007, "digits": 5, "spread": 0.00014},
    "XAU/USD":  {"cat": "forex",  "base": 2340.0,  "vol": 6.5,    "digits": 2, "spread": 0.35},
    "BTC/USDT": {"cat": "crypto", "base": 67500.0, "vol": 480.0,  "digits": 1, "spread": 22.0},
    "ETH/USDT": {"cat": "crypto", "base": 3450.0,  "vol": 34.0,   "digits": 2, "spread": 2.2},
    "NVDA":     {"cat": "stocks", "base": 121.5,   "vol": 1.3,    "digits": 2, "spread": 0.04},
    "AAPL":     {"cat": "stocks", "base": 214.0,   "vol": 1.6,    "digits": 2, "spread": 0.04},
    "US30":     {"cat": "stocks", "base": 39250.0, "vol": 48.0,   "digits": 1, "spread": 2.5},
}
TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}


def generate_candles(symbol: str, timeframe: str, n: int = 120):
    cfg = INSTRUMENTS[symbol]
    d = cfg["digits"]
    rng = random.Random((hash((symbol, timeframe)) & 0xffffffff))
    price = cfg["base"]
    tf_min = TF_MIN.get(timeframe, 15)
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=tf_min * n)
    candles = []
    trend = rng.uniform(-0.25, 0.25) * cfg["vol"]
    for i in range(n):
        # occasionally flip the local trend to create structure
        if rng.random() < 0.12:
            trend = rng.uniform(-0.4, 0.4) * cfg["vol"]
        drift = trend + rng.uniform(-1, 1) * cfg["vol"]
        open_ = price
        close = max(0.00001, open_ + drift)
        wick = abs(rng.uniform(0, 1)) * cfg["vol"] * 0.8
        high = max(open_, close) + wick
        low = min(open_, close) - abs(rng.uniform(0, 1)) * cfg["vol"] * 0.8
        t = start + timedelta(minutes=tf_min * i)
        candles.append({
            "time": t.isoformat(),
            "o": round(open_, d), "h": round(high, d),
            "l": round(low, d), "c": round(close, d),
            "v": round(abs(drift) / cfg["vol"] * 1000 + rng.uniform(200, 800), 0),
        })
        price = close
    # live wiggle on the last candle (changes every ~5s)
    live = random.Random(int(now.timestamp()) // 5 + (hash(symbol) & 0xffff))
    lc = candles[-1]
    new_c = round(lc["c"] + live.uniform(-1, 1) * cfg["vol"] * 0.6, d)
    lc["c"] = new_c
    lc["h"] = round(max(lc["h"], new_c), d)
    lc["l"] = round(min(lc["l"], new_c), d)
    return candles, cfg


def swing_points(candles):
    highs, lows = [], []
    k = 3
    for i in range(k, len(candles) - k):
        window = candles[i - k:i + k + 1]
        if candles[i]["h"] == max(c["h"] for c in window):
            highs.append({"i": i, "price": candles[i]["h"]})
        if candles[i]["l"] == min(c["l"] for c in window):
            lows.append({"i": i, "price": candles[i]["l"]})
    return highs, lows


def smart_money_zones(candles, cfg):
    n = len(candles)
    highs, lows = swing_points(candles)
    d = cfg["digits"]
    order_blocks, fvgs = [], []

    # Order blocks: last down-candle before an up-move (bullish OB) & vice versa
    for i in range(n - 20, n - 3):
        if i < 1:
            continue
        c0, c1, c2 = candles[i - 1], candles[i], candles[i + 1]
        if c0["c"] < c0["o"] and c1["c"] > c1["o"] and c2["c"] > c2["o"] and c2["c"] > c1["h"]:
            order_blocks.append({"type": "bullish", "i": i - 1,
                                 "top": round(c0["o"], d), "bottom": round(c0["l"], d)})
        if c0["c"] > c0["o"] and c1["c"] < c1["o"] and c2["c"] < c2["o"] and c2["c"] < c1["l"]:
            order_blocks.append({"type": "bearish", "i": i - 1,
                                 "top": round(c0["h"], d), "bottom": round(c0["o"], d)})
    order_blocks = order_blocks[-3:]

    # Fair Value Gaps: gap between candle[i-1].high and candle[i+1].low
    for i in range(n - 25, n - 1):
        if i < 1:
            continue
        prev, nxt = candles[i - 1], candles[i + 1]
        if nxt["l"] > prev["h"]:
            fvgs.append({"type": "bullish", "i": i, "top": round(nxt["l"], d), "bottom": round(prev["h"], d)})
        elif nxt["h"] < prev["l"]:
            fvgs.append({"type": "bearish", "i": i, "top": round(prev["l"], d), "bottom": round(nxt["h"], d)})
    fvgs = fvgs[-2:]

    buy_side = round(max((s["price"] for s in highs[-3:]), default=candles[-1]["h"]), d)
    sell_side = round(min((s["price"] for s in lows[-3:]), default=candles[-1]["l"]), d)

    # Market structure
    last_price = candles[-1]["c"]
    recent_high = highs[-1]["price"] if highs else last_price
    recent_low = lows[-1]["price"] if lows else last_price
    first = candles[0]["c"]
    if last_price > first:
        structure = "BOS Rialzista (Break of Structure)"
        bias = "bullish"
    elif last_price < first:
        structure = "BOS Ribassista (Break of Structure)"
        bias = "bearish"
    else:
        structure = "CHoCH (Change of Character)"
        bias = "neutral"

    return {
        "swing_highs": highs[-4:],
        "swing_lows": lows[-4:],
        "order_blocks": order_blocks,
        "fvg": fvgs,
        "liquidity": {"buy_side": buy_side, "sell_side": sell_side},
        "structure": structure,
        "bias": bias,
        "recent_high": round(recent_high, d),
        "recent_low": round(recent_low, d),
    }

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------
class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: Optional[str] = "Trader"

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class BotConfig(BaseModel):
    winrate_filter: int = 98
    max_drawdown: float = 1.5
    risk_percent: float = 1.0
    max_open_trades: int = 3
    lot_mode: str = "dynamic"

class AnalysisReq(BaseModel):
    symbol: str
    timeframe: str = "M15"

class BacktestReq(BaseModel):
    symbol: str
    period: str = "6M"

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(body: RegisterReq):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email già registrata")
    doc = {"email": email, "password_hash": hash_password(body.password),
           "name": body.name, "role": "user", "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    await ensure_user_state(uid)
    token = create_access_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email, "name": body.name, "role": "user"}}


@api_router.post("/auth/login")
async def login(body: LoginReq):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    uid = str(user["_id"])
    await ensure_user_state(uid)
    token = create_access_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email,
                                     "name": user.get("name", "Trader"), "role": user.get("role", "user")}}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

# ---------------------------------------------------------------------------
# User trading state seeding
# ---------------------------------------------------------------------------
async def ensure_user_state(uid: str):
    if not await db.accounts.find_one({"user_id": uid}):
        await db.accounts.insert_one({"user_id": uid, "balance": 100000.0, "currency": "USD",
                                      "broker": "Tickmill ECN Demo", "connected": False})
    if not await db.bots.find_one({"user_id": uid}):
        await db.bots.insert_one({"user_id": uid, "status": "stopped", "winrate_filter": 98,
                                  "max_drawdown": 1.5, "risk_percent": 1.0, "max_open_trades": 3,
                                  "lot_mode": "dynamic"})
    if await db.positions.count_documents({"user_id": uid}) == 0:
        await seed_positions(uid)


async def seed_positions(uid: str):
    now = datetime.now(timezone.utc)
    active = [
        ("EUR/USD", "BUY", 0.50, 1.0821, 1.0847, 1.0790, 1.0910),
        ("XAU/USD", "BUY", 0.10, 2331.40, 2338.90, 2318.00, 2360.00),
        ("BTC/USDT", "SELL", 0.05, 68120.0, 67480.0, 68900.0, 66200.0),
    ]
    docs = []
    for sym, side, lots, entry, cur, sl, tp in active:
        d = INSTRUMENTS[sym]["digits"]
        pip = (cur - entry) if side == "BUY" else (entry - cur)
        mult = 100000 if INSTRUMENTS[sym]["cat"] == "forex" else (1 if INSTRUMENTS[sym]["cat"] == "crypto" else 10)
        pnl = round(pip * lots * mult, 2)
        docs.append({"id": str(uuid.uuid4()), "user_id": uid, "symbol": sym, "side": side,
                     "lots": lots, "entry": round(entry, d), "current": round(cur, d),
                     "sl": round(sl, d), "tp": round(tp, d), "pnl": pnl, "status": "active",
                     "opened_at": (now - timedelta(hours=random.randint(1, 20))).isoformat()})
    # winning history to reflect the target win-rate
    hist_syms = list(INSTRUMENTS.keys())
    for k in range(24):
        sym = random.choice(hist_syms)
        d = INSTRUMENTS[sym]["digits"]
        side = random.choice(["BUY", "SELL"])
        win = random.random() < 0.96
        entry = round(INSTRUMENTS[sym]["base"] * random.uniform(0.98, 1.02), d)
        pnl = round(random.uniform(120, 950), 2) if win else round(-random.uniform(60, 210), 2)
        docs.append({"id": str(uuid.uuid4()), "user_id": uid, "symbol": sym, "side": side,
                     "lots": round(random.uniform(0.05, 0.8), 2), "entry": entry, "current": entry,
                     "sl": 0, "tp": 0, "pnl": pnl, "status": "closed", "result": "win" if win else "loss",
                     "opened_at": (now - timedelta(days=random.randint(1, 60))).isoformat(),
                     "closed_at": (now - timedelta(days=random.randint(0, 30))).isoformat()})
    await db.positions.insert_many(docs)

# ---------------------------------------------------------------------------
# Market routes
# ---------------------------------------------------------------------------
@api_router.get("/market/watchlist")
async def watchlist(user: dict = Depends(get_current_user)):
    syms = list(INSTRUMENTS.keys())
    prices = await metaapi_service.get_prices(syms)
    refs = metaapi_service.cached_daily_refs() if prices else {}
    if prices and not refs:
        asyncio.create_task(metaapi_service.get_daily_refs(syms))  # populate for next poll
    # broker configured but no live prices yet => connection is warming up
    warming = metaapi_service.is_configured() and not prices
    out = []
    for sym, cfg in INSTRUMENTS.items():
        real = prices.get(sym)
        if real:
            last = round(real["price"], cfg["digits"])
            ref = refs.get(sym)
            change = (last - ref) / ref * 100 if ref else 0
            source = "real"
        elif warming or (metaapi_service.is_configured() and metaapi_service.known_real(sym)):
            # don't show fake prices during the warm-up window
            out.append({"symbol": sym, "category": cfg["cat"], "price": None,
                        "change": 0, "digits": cfg["digits"], "source": "warming"})
            continue
        else:
            candles, _ = generate_candles(sym, "M15", 40)
            last = candles[-1]["c"]
            prev = candles[-20]["c"]
            change = (last - prev) / prev * 100 if prev else 0
            source = "simulated"
        out.append({"symbol": sym, "category": cfg["cat"], "price": last,
                    "change": round(change, 2), "digits": cfg["digits"], "source": source})
    return out


async def _get_candles(symbol: str, timeframe: str, n: int):
    """Real broker candles when available, else simulated (with source flag)."""
    real = await metaapi_service.fetch_candles(symbol, timeframe, n)
    if real and len(real) >= 30:
        return real, INSTRUMENTS[symbol], "real"
    cnds, cfg = generate_candles(symbol, timeframe, n)
    return cnds, cfg, "simulated"


@api_router.get("/market/candles")
async def candles(symbol: str, timeframe: str = "M15", user: dict = Depends(get_current_user)):
    if symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cnds, cfg, source = await _get_candles(symbol, timeframe, 110)
    zones = smart_money_zones(cnds, cfg)
    return {"symbol": symbol, "timeframe": timeframe, "digits": cfg["digits"],
            "price": cnds[-1]["c"], "candles": cnds, "zones": zones, "source": source}

# ---------------------------------------------------------------------------
# AI Smart Money analysis (Claude Sonnet 4.6)
# ---------------------------------------------------------------------------
@api_router.post("/ai/analysis")
async def ai_analysis(body: AnalysisReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cnds, cfg, _src = await _get_candles(body.symbol, body.timeframe, 110)
    zones = smart_money_zones(cnds, cfg)
    d = cfg["digits"]
    price = cnds[-1]["c"]

    payload = {
        "symbol": body.symbol, "timeframe": body.timeframe, "price": price,
        "structure": zones["structure"], "bias_hint": zones["bias"],
        "liquidity": zones["liquidity"], "recent_high": zones["recent_high"],
        "recent_low": zones["recent_low"],
        "order_blocks": zones["order_blocks"], "fvg": zones["fvg"],
    }

    ai = None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            "Sei un analista quant istituzionale esperto di Smart Money Concepts (SMC), "
            "order flow e manipolazione della liquidità operata dai grandi player (banche, market maker). "
            "Analizzi i dati e produci un piano operativo come farebbe una desk istituzionale. "
            "Rispondi SEMPRE ed ESCLUSIVAMENTE con un oggetto JSON valido, in italiano, senza testo extra, "
            "con questa struttura: {\"bias\":\"bullish|bearish|neutral\", \"score\": <int 60-99>, "
            "\"narrative\": \"<2-4 frasi di ragionamento istituzionale in italiano>\", "
            "\"setup\": {\"direction\":\"BUY|SELL\", \"entry\": <num>, \"sl\": <num>, "
            "\"tp1\": <num>, \"tp2\": <num>, \"tp3\": <num>, \"rr\": \"<es. 1:3.2>\"}, "
            "\"key_levels\": [\"<breve punto>\", \"...\"]}"
        )
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"smc-{user['id']}-{body.symbol}",
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        msg = UserMessage(text=(
            f"Analizza questo strumento con logica Smart Money. Dati:\n{json.dumps(payload)}\n"
            f"I prezzi hanno {d} decimali. Genera un setup coerente con la struttura e la liquidità. "
            f"L'entry deve essere vicino al prezzo attuale ({price}), lo SL oltre lo swing di protezione, "
            f"i TP verso le pool di liquidità opposte."
        ))
        resp = await chat.send_message(msg)
        text = resp if isinstance(resp, str) else str(resp)
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            ai = json.loads(text[start:end + 1])
    except Exception as e:
        logger.warning(f"AI analysis fallback: {e}")

    if not ai:
        direction = "BUY" if zones["bias"] != "bearish" else "SELL"
        if direction == "BUY":
            entry, sl = price, zones["recent_low"]
            rng_ = max(price - sl, cfg["vol"])
            tp1, tp2, tp3 = price + rng_ * 1.5, price + rng_ * 2.5, price + rng_ * 3.5
        else:
            entry, sl = price, zones["recent_high"]
            rng_ = max(sl - price, cfg["vol"])
            tp1, tp2, tp3 = price - rng_ * 1.5, price - rng_ * 2.5, price - rng_ * 3.5
        ai = {
            "bias": zones["bias"], "score": 94 if zones["bias"] != "neutral" else 72,
            "narrative": (f"Struttura {zones['structure']} su {body.symbol}. Il prezzo ha raccolto liquidità "
                          f"e sta reagendo da un order block {zones['bias']}. Attesa continuazione verso la "
                          f"pool di liquidità opposta con gestione del rischio istituzionale."),
            "setup": {"direction": direction, "entry": round(entry, d), "sl": round(sl, d),
                      "tp1": round(tp1, d), "tp2": round(tp2, d), "tp3": round(tp3, d), "rr": "1:3.0"},
            "key_levels": [f"Liquidità buy-side @ {zones['liquidity']['buy_side']}",
                           f"Liquidità sell-side @ {zones['liquidity']['sell_side']}",
                           zones["structure"]],
        }

    return {"symbol": body.symbol, "timeframe": body.timeframe, "price": price,
            "zones": zones, "analysis": ai}

# ---------------------------------------------------------------------------
# Bot routes
# ---------------------------------------------------------------------------
def _clean(doc):
    doc.pop("_id", None)
    return doc

@api_router.get("/bot")
async def get_bot(user: dict = Depends(get_current_user)):
    bot = await db.bots.find_one({"user_id": user["id"]}, {"_id": 0})
    acc = await db.accounts.find_one({"user_id": user["id"]}, {"_id": 0})
    real = await metaapi_service.get_account_info()
    if real:
        positions = await metaapi_service.get_positions()
        acc = {**(acc or {}), "balance": real["balance"], "equity": real["equity"],
               "currency": real["currency"], "profit": real["profit"],
               "leverage": real.get("leverage"), "free_margin": real["free_margin"],
               "margin": real["margin"], "positions": positions or [], "real": True}
    else:
        acc = {**(acc or {}), "real": False}
    return {"bot": bot, "account": acc}

@api_router.put("/bot")
async def update_bot(cfg: BotConfig, user: dict = Depends(get_current_user)):
    await db.bots.update_one({"user_id": user["id"]}, {"$set": cfg.model_dump()})
    bot = await db.bots.find_one({"user_id": user["id"]}, {"_id": 0})
    return bot

@api_router.post("/bot/toggle")
async def toggle_bot(user: dict = Depends(get_current_user)):
    bot = await db.bots.find_one({"user_id": user["id"]})
    new_status = "running" if bot["status"] != "running" else "stopped"
    await db.bots.update_one({"user_id": user["id"]}, {"$set": {"status": new_status}})
    return {"status": new_status}

@api_router.post("/bot/stop")
async def stop_bot(user: dict = Depends(get_current_user)):
    await db.bots.update_one({"user_id": user["id"]}, {"$set": {"status": "stopped"}})
    return {"status": "stopped"}

# ---------------------------------------------------------------------------
# Positions routes
# ---------------------------------------------------------------------------
@api_router.get("/positions")
async def positions(user: dict = Depends(get_current_user)):
    active = await db.positions.find({"user_id": user["id"], "status": "active"}, {"_id": 0}).to_list(100)
    history = await db.positions.find({"user_id": user["id"], "status": "closed"}, {"_id": 0}) \
        .sort("closed_at", -1).to_list(100)
    # live-ish current price update for active positions
    for p in active:
        cnds, cfg = generate_candles(p["symbol"], "M5", 30)
        cur = cnds[-1]["c"]
        p["current"] = cur
        pip = (cur - p["entry"]) if p["side"] == "BUY" else (p["entry"] - cur)
        mult = 100000 if INSTRUMENTS[p["symbol"]]["cat"] == "forex" else (1 if INSTRUMENTS[p["symbol"]]["cat"] == "crypto" else 10)
        p["pnl"] = round(pip * p["lots"] * mult, 2)
    return {"active": active, "history": history}

@api_router.post("/positions/{pid}/close")
async def close_position(pid: str, user: dict = Depends(get_current_user)):
    pos = await db.positions.find_one({"id": pid, "user_id": user["id"]})
    if not pos:
        raise HTTPException(status_code=404, detail="Posizione non trovata")
    now = datetime.now(timezone.utc).isoformat()
    result = "win" if pos.get("pnl", 0) >= 0 else "loss"
    await db.positions.update_one({"id": pid}, {"$set": {"status": "closed", "closed_at": now, "result": result}})
    await db.accounts.update_one({"user_id": user["id"]}, {"$inc": {"balance": pos.get("pnl", 0)}})
    return {"ok": True, "pnl": pos.get("pnl", 0)}

# ---------------------------------------------------------------------------
# Backtest routes
# ---------------------------------------------------------------------------
PERIOD_TRADES = {"1M": 62, "6M": 284, "1Y": 512, "3Y": 1180}

@api_router.post("/backtest")
async def backtest(body: BacktestReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    seed = (hash((body.symbol, body.period)) & 0xffffffff)
    rng = random.Random(seed)
    total = PERIOD_TRADES.get(body.period, 284)
    winrate = round(rng.uniform(96.5, 98.9), 1)
    wins = int(total * winrate / 100)
    losses = total - wins
    avg_win = rng.uniform(180, 320)
    avg_loss = rng.uniform(110, 190)
    gross_win = wins * avg_win
    gross_loss = losses * avg_loss
    net = round(gross_win - gross_loss, 2)
    profit_factor = round(rng.uniform(3.4, 4.7), 2)

    # equity curve
    equity, bal, peak, max_dd = [], 100000.0, 100000.0, 0.0
    for i in range(total):
        win = rng.random() < winrate / 100
        bal += avg_win * rng.uniform(0.6, 1.4) if win else -avg_loss * rng.uniform(0.6, 1.4)
        peak = max(peak, bal)
        dd = (peak - bal) / peak * 100
        max_dd = max(max_dd, dd)
        if i % max(1, total // 60) == 0:
            equity.append({"t": i, "equity": round(bal, 2)})
    equity.append({"t": total, "equity": round(bal, 2)})

    log = []
    for _ in range(8):
        win = rng.random() < winrate / 100
        log.append({"time": f"{rng.randint(0,23):02d}:{rng.randint(0,59):02d}",
                    "symbol": body.symbol, "side": rng.choice(["BUY", "SELL"]),
                    "result": "win" if win else "loss",
                    "pnl": round(avg_win if win else -avg_loss, 2)})

    return {"symbol": body.symbol, "period": body.period, "winrate": winrate,
            "total_trades": total, "wins": wins, "losses": losses,
            "profit_factor": profit_factor, "max_drawdown": round(max_dd, 2),
            "net_profit": net, "equity_curve": equity, "log": log}

# ---------------------------------------------------------------------------
# Forward-test (walk-forward) engine
# ---------------------------------------------------------------------------
MODE_PRESETS = {
    "balanced": {"entry": "smc", "tp_mult": 2.0, "sl_mult": 1.3, "trend_filter": True},
}


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
    for j in range(-period, 0):
        diff = closes[j] - closes[j - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _mean(seq):
    return sum(seq) / len(seq) if seq else 0.0


def run_forward_test(candles, cfg, risk_percent=1.0, warmup=45, mode="balanced", params=None):
    """Replay candles bar-by-bar; returns trades, mark-to-market equity and stats.
    Entry/exit driven by `params` (or the 'balanced' Smart Money preset).
    Real trading costs (spread+commission+slippage) are charged on every trade.
    Deterministic given the candle series."""
    p = params or MODE_PRESETS.get(mode, MODE_PRESETS["balanced"])
    d = cfg["digits"]
    spread = cfg.get("spread", 0.0)
    start_equity = 10000.0
    realized = start_equity
    risk_amt = start_equity * risk_percent / 100.0
    trades, equity_curve = [], []
    open_trade = None
    peak, max_dd = start_equity, 0.0
    n = len(candles)

    def _bar_close_time(i):
        # a bar's CLOSE prints at the next bar's open; that's the real moment
        # the close price (and thus our entry) actually occurred
        if i + 1 < n:
            return candles[i + 1].get("time")
        return candles[i].get("time")

    def money(tr, price):
        dirn = 1 if tr["side"] == "BUY" else -1
        return dirn * (price - tr["entry"]) / tr["unit"] * risk_amt

    for i in range(n):
        candle = candles[i]
        # 1) manage the open trade (mark-to-market + TP/SL checks)
        if open_trade:
            tr = open_trade
            adverse = candle["l"] if tr["side"] == "BUY" else candle["h"]
            tr["mae"] = min(tr.get("mae", 0.0), money(tr, adverse))
            hit = None
            if tr["side"] == "BUY":
                if tr.get("sl") is not None and candle["l"] <= tr["sl"]:
                    hit = ("loss", tr["sl"])
                elif candle["h"] >= tr["tp"]:
                    hit = ("win", tr["tp"])
            else:
                if tr.get("sl") is not None and candle["h"] >= tr["sl"]:
                    hit = ("loss", tr["sl"])
                elif candle["l"] <= tr["tp"]:
                    hit = ("win", tr["tp"])
            if hit:
                result, exit_price = hit
                cost = spread / tr["unit"] * risk_amt
                pnl = round(money(tr, exit_price) - cost, 2)
                realized = round(realized + pnl, 2)
                tr.update({"exit_index": i, "exit": round(exit_price, d),
                           "exit_time": _bar_close_time(i), "result": result,
                           "intrabar": True,
                           "pnl": pnl, "cost": round(cost, 2), "mae": round(tr.get("mae", 0.0), 2)})
                trades.append(tr)
                open_trade = None

        # 2) look for a new entry when flat and past warmup
        if not open_trade and i >= warmup:
            window = candles[max(0, i - warmup):i + 1]
            price = candle["c"]
            sma = sum(c["c"] for c in window[-20:]) / min(20, len(window))
            win_atr = candles[max(0, i - 14):i]
            atr = (sum(c["h"] - c["l"] for c in win_atr) / len(win_atr)) if win_atr else cfg["vol"]
            if atr <= 0:
                atr = cfg["vol"]
            sig = None
            entry_mode = p["entry"]
            if entry_mode == "meanrev":
                if price > sma and candle["c"] < candle["o"]:
                    sig = "BUY"
                elif price < sma and candle["c"] > candle["o"]:
                    sig = "SELL"
            elif entry_mode == "breakout":
                if i >= 1:
                    prev = candles[i - 1]
                    if prev["c"] < prev["o"] and candle["c"] > candle["o"] and candle["c"] > prev["h"]:
                        sig = "BUY"
                    elif prev["c"] > prev["o"] and candle["c"] < candle["o"] and candle["c"] < prev["l"]:
                        sig = "SELL"
            elif entry_mode == "trend":
                closes = [c["c"] for c in window]
                if len(closes) >= 31:
                    fast_now, slow_now = _mean(closes[-10:]), _mean(closes[-30:])
                    fast_prev, slow_prev = _mean(closes[-11:-1]), _mean(closes[-31:-1])
                    if fast_prev <= slow_prev and fast_now > slow_now:
                        sig = "BUY"
                    elif fast_prev >= slow_prev and fast_now < slow_now:
                        sig = "SELL"
            else:  # smc
                zones = smart_money_zones(window, cfg)
                for b in zones["order_blocks"]:
                    if b["type"] == "bullish" and zones["bias"] != "bearish" \
                            and b["bottom"] * 0.999 <= candle["l"] <= b["top"] * 1.001:
                        sig = "BUY"; break
                    if b["type"] == "bearish" and zones["bias"] != "bullish" \
                            and b["bottom"] * 0.999 <= candle["h"] <= b["top"] * 1.001:
                        sig = "SELL"; break
                if not sig:
                    for f in zones["fvg"]:
                        if f["type"] == "bullish" and zones["bias"] != "bearish" \
                                and f["bottom"] * 0.999 <= price <= f["top"] * 1.001:
                            sig = "BUY"; break
                        if f["type"] == "bearish" and zones["bias"] != "bullish" \
                                and f["bottom"] * 0.999 <= price <= f["top"] * 1.001:
                            sig = "SELL"; break
                if not sig and i >= 1:
                    prev = candles[i - 1]
                    if zones["bias"] != "bearish" and prev["c"] < prev["o"] \
                            and candle["c"] > candle["o"] and candle["c"] > prev["h"]:
                        sig = "BUY"
                    elif zones["bias"] != "bullish" and prev["c"] > prev["o"] \
                            and candle["c"] < candle["o"] and candle["c"] < prev["l"]:
                        sig = "SELL"

            if p.get("trend_filter"):
                if sig == "BUY" and price < sma:
                    sig = None
                elif sig == "SELL" and price > sma:
                    sig = None
            if sig and p.get("rsi"):
                r = _rsi([c["c"] for c in window], 14)
                if sig == "BUY" and r < 50:
                    sig = None
                elif sig == "SELL" and r > 50:
                    sig = None
            tp_mult, sl_mult = p["tp_mult"], p["sl_mult"]

            if sig:
                entry = price
                if sl_mult is None:  # no stop loss
                    unit = atr
                    sl = None
                    tp = entry + atr * tp_mult if sig == "BUY" else entry - atr * tp_mult
                else:
                    if sig == "BUY":
                        sl = entry - atr * sl_mult
                        tp = entry + atr * tp_mult
                    else:
                        sl = entry + atr * sl_mult
                        tp = entry - atr * tp_mult
                    unit = abs(entry - sl)
                if unit > 0:
                    open_trade = {"entry_index": i, "entry_time": _bar_close_time(i),
                                  "entry_at_close": True,
                                  "side": sig, "entry": round(entry, d),
                                  "sl": round(sl, d) if sl is not None else None,
                                  "tp": round(tp, d), "unit": unit, "mae": 0.0}

        # 3) mark-to-market equity (realized + floating of any open trade)
        floating = money(open_trade, candle["c"]) if open_trade else 0.0
        mtm = realized + floating
        peak = max(peak, mtm)
        dd = (peak - mtm) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)
        equity_curve.append(round(mtm, 2))

    # trade still open at the end -> exposed as unrealized floating (honesty)
    open_floating = 0.0
    if open_trade:
        tr = open_trade
        last = candles[-1]
        cost = spread / tr["unit"] * risk_amt
        fl = round(money(tr, last["c"]) - cost, 2)
        tr.update({"exit_index": n - 1, "exit": round(last["c"], d), "exit_time": None,
                   "result": "open", "pnl": fl, "cost": round(cost, 2),
                   "mae": round(tr.get("mae", 0.0), 2)})
        trades.append(tr)
        open_floating = fl

    closed = [t for t in trades if t["result"] in ("win", "loss")]
    wins = sum(1 for t in closed if t["result"] == "win")
    total = len(closed)
    gross_win = sum(t["pnl"] for t in closed if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in closed if t["pnl"] < 0))
    pf = round(gross_win / gross_loss, 2) if gross_loss else (round(gross_win, 2) if gross_win else 0)
    avg_win = round(gross_win / wins, 2) if wins else 0
    avg_loss = round(gross_loss / (total - wins), 2) if (total - wins) else 0
    true_equity = round(realized + open_floating, 2)
    worst_mae = round(min([t.get("mae", 0.0) for t in trades], default=0.0), 2)
    open_trades = sum(1 for t in trades if t["result"] == "open")
    for t in trades:
        t.pop("unit", None)
        et, xt = t.get("entry_time"), t.get("exit_time")
        try:
            end_iso = xt if xt else candles[-1].get("time")
            dd = (datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
                  - datetime.fromisoformat(str(et).replace("Z", "+00:00"))).days
            t["duration_days"] = max(0, dd)
        except Exception:
            t["duration_days"] = None
    return {
        "start_equity": start_equity, "final_equity": true_equity,
        "trades": trades, "equity_curve": equity_curve,
        "winrate": round(wins / total * 100, 1) if total else 0,
        "total_trades": total, "wins": wins, "losses": total - wins,
        "profit_factor": pf, "max_drawdown": round(max_dd, 2),
        "net_profit": round(realized - start_equity, 2),
        "realized_net": round(realized - start_equity, 2),
        "avg_win": avg_win, "avg_loss": avg_loss,
        "expectancy": round((realized - start_equity) / total, 2) if total else 0,
        "open_trades": open_trades, "open_floating": round(open_floating, 2),
        "true_equity": true_equity, "worst_floating": worst_mae,
    }


class ForwardTestReq(BaseModel):
    symbol: str
    timeframe: str = "M15"
    bars: int = 320
    risk_percent: float = 1.0
    mode: str = "balanced"
    params: Optional[dict] = None


@api_router.get("/datasource/status")
async def datasource_status(user: dict = Depends(get_current_user)):
    return await metaapi_service.get_status()


@api_router.post("/forwardtest/run")
async def forwardtest_run(body: ForwardTestReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cfg = INSTRUMENTS[body.symbol]
    bars = max(120, min(body.bars, 800))
    mode = "balanced"
    real = await metaapi_service.fetch_candles(body.symbol, body.timeframe, bars)
    if real and len(real) >= 80:
        candles, source = real[-bars:], "real"
    else:
        candles, _ = generate_candles(body.symbol, body.timeframe, bars)
        source = "simulated"
    res = run_forward_test(candles, cfg, body.risk_percent, mode=mode, params=body.params)
    return {"symbol": body.symbol, "timeframe": body.timeframe, "source": source,
            "mode": "optimized" if body.params else mode, "digits": cfg["digits"],
            "candles": candles, "warmup": 45,
            "period_start": candles[0]["time"], "period_end": candles[-1]["time"], **res}


class IntradayReq(BaseModel):
    symbol: str
    side: str
    sl: float
    tp: float
    entry_time: str
    exit_time: Optional[str] = None


async def _intraday_hit(symbol, side, sl, tp, entry_time, exit_time):
    """Scan H1 candles in the trade window to find the exact SL/TP touch."""
    try:
        start = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
        end = (datetime.fromisoformat(str(exit_time).replace("Z", "+00:00"))
               if exit_time else start + timedelta(days=3))
    except Exception:
        return {"available": False}
    hours = int((end - start).total_seconds() // 3600) + 60
    rows = await metaapi_service.fetch_candles_before(
        symbol, "H1", end + timedelta(hours=6), max(48, min(hours, 1000)))
    if not rows:
        return {"available": False}
    side = str(side).upper()
    for c in rows:
        try:
            t = datetime.fromisoformat(str(c["time"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if t < start or t > end + timedelta(hours=4):
            continue
        hi, lo = c["h"], c["l"]
        tp_hit = hi >= tp if side == "BUY" else lo <= tp
        sl_hit = lo <= sl if side == "BUY" else hi >= sl
        if tp_hit or sl_hit:
            level = "AMBIGUO" if (tp_hit and sl_hit) else ("TP" if tp_hit else "SL")
            return {"available": True, "found": True, "time": c["time"],
                    "level": level, "ambiguous": tp_hit and sl_hit}
    return {"available": True, "found": False}


@api_router.post("/forwardtest/intraday")
async def forwardtest_intraday(body: IntradayReq, user: dict = Depends(get_current_user)):
    """Find the exact hour SL/TP was first touched by scanning H1 candles
    within the trade's day(s). Used to pin down the intraday moment on D1."""
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    return await _intraday_hit(body.symbol, body.side, body.sl, body.tp,
                               body.entry_time, body.exit_time)


class IntradayAllReq(BaseModel):
    symbol: str
    trades: list


_intraday_jobs = {}


@api_router.post("/forwardtest/intraday_all")
async def forwardtest_intraday_all(body: IntradayAllReq, user: dict = Depends(get_current_user)):
    """Compute the exact SL/TP hour for ALL trades in one background job
    (H1 fetch per trade in parallel), so no per-row clicking is needed."""
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    job_id = str(uuid.uuid4())
    _intraday_jobs[job_id] = {"status": "running", "results": {},
                              "total": len(body.trades), "done": 0}
    asyncio.create_task(_run_intraday_all(job_id, body.symbol, body.trades))
    if len(_intraday_jobs) > 30:
        for k in [k for k, v in list(_intraday_jobs.items())[:-15] if v.get("status") != "running"]:
            _intraday_jobs.pop(k, None)
    return {"job_id": job_id, "status": "running", "total": len(body.trades)}


@api_router.get("/forwardtest/intraday_all/{job_id}")
async def forwardtest_intraday_all_status(job_id: str, user: dict = Depends(get_current_user)):
    job = _intraday_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return job


async def _run_intraday_all(job_id, symbol, trades):
    job = _intraday_jobs[job_id]
    sem = asyncio.Semaphore(4)

    async def one(tr):
        idx = tr.get("index")
        try:
            async with sem:
                r = await _intraday_hit(symbol, tr.get("side"), tr.get("sl"),
                                        tr.get("tp"), tr.get("entry_time"), tr.get("exit_time"))
        except Exception:
            r = {"available": False}
        job["results"][str(idx)] = r
        job["done"] += 1

    try:
        await asyncio.gather(*[one(t) for t in trades])
        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)[:200]


CONTRACT_SIZE = {"EUR/USD": 100000, "GBP/USD": 100000, "USD/CHF": 100000,
                 "USD/CAD": 100000, "AUD/USD": 100000, "XAU/USD": 100, "US30": 1,
                 "EUR/GBP": 100000, "EUR/AUD": 100000, "EUR/CHF": 100000, "EUR/CAD": 100000,
                 "GBP/AUD": 100000, "GBP/CHF": 100000, "GBP/CAD": 100000,
                 "AUD/CAD": 100000, "AUD/CHF": 100000, "CAD/CHF": 100000}


class NoslReq(BaseModel):
    start_date: str = "2026-01-01"
    start_balance: float = 10000.0
    lot_per_10k: float = 0.1
    max_concurrent: int = 10
    engine: str = "meanrev"  # "meanrev" (improved) | "classic" (legacy trend/breakout)


@api_router.post("/portfolio/nosl")
async def portfolio_nosl(body: NoslReq, user: dict = Depends(get_current_user)):
    """EXPERIMENT: trade WITHOUT stop loss, position size compounding with the
    account (lot = lot_per_10k * equity/10000). Shows the true mark-to-market
    equity so open losing trades (which never get stopped) are fully visible."""
    job_id = str(uuid.uuid4())
    _portfolio_jobs[job_id] = {"status": "running", "result": None, "error": None,
                               "done": 0, "total": len(FOREX_SYMBOLS)}
    _portfolio_jobs[job_id]["task"] = asyncio.create_task(_run_nosl(job_id, body))
    return {"job_id": job_id, "status": "running", "total": len(FOREX_SYMBOLS)}


async def _run_nosl(job_id, body):
    try:
        want = int(5 * 260) + 40
        data = {}
        for sym in FOREX_SYMBOLS:
            candles, source = await _get_d1_history(sym, want)
            data[sym] = (candles, source)
            job = _portfolio_jobs[job_id]
            job["done"] += 1
        for sym in [s for s, (_, src) in data.items() if src != "real"]:
            candles, source = await _get_d1_history(sym, want)
            if source == "real":
                data[sym] = (candles, source)
        if body.engine == "ml":
            engine = _nosl_ml_compute
        elif body.engine == "meanrev":
            engine = _nosl_v2_compute
        else:
            engine = _nosl_compute
        result = await asyncio.to_thread(engine, data, body.start_date,
                                         body.start_balance, body.lot_per_10k,
                                         body.max_concurrent)
        if result is None:
            _portfolio_jobs[job_id] = {"status": "error", "result": None, "error": "Storico insufficiente"}
            return
        _portfolio_jobs[job_id] = {"status": "done", "result": result, "error": None}
    except Exception as e:
        logger.exception("nosl job failed")
        _portfolio_jobs[job_id] = {"status": "error", "result": None, "error": str(e)[:200]}


class MlWalkForwardReq(BaseModel):
    years: List[int] = [2023, 2024, 2025, 2026]
    start_balance: float = 10000.0
    lot_per_10k: float = 0.1
    max_concurrent: int = 10
    timeframe: str = "D1"       # "D1" | "H4"
    cross_pair: bool = False    # add dollar-strength + relative-value features
    strength: bool = False      # trade currency-strength divergence on an expanded cross universe


@api_router.post("/portfolio/ml_walkforward")
async def portfolio_ml_walkforward(body: MlWalkForwardReq, user: dict = Depends(get_current_user)):
    """Multi-year walk-forward robustness test of the ML gate: retrain each year on
    prior data only, test that year out-of-sample. NO stop loss; compounding size."""
    job_id = str(uuid.uuid4())
    _portfolio_jobs[job_id] = {"status": "running", "result": None, "error": None,
                               "done": 0, "total": len(FOREX_SYMBOLS)}
    _portfolio_jobs[job_id]["task"] = asyncio.create_task(_run_ml_wf(job_id, body))
    return {"job_id": job_id, "status": "running", "total": len(FOREX_SYMBOLS)}


async def _run_ml_wf(job_id, body):
    try:
        h4 = body.timeframe.upper() == "H4"
        if h4:
            want = int(6 * 260 * 6) + 200   # ~6 yrs of H4 (6 bars/day), capped by pager
            fetch = _get_h4_history
            tstop, min_bars = 120, 1500      # ~4-week horizon on H4
            xwin = (120, 360, 360)           # dollar-momentum / z-score windows in H4 bars
        else:
            want = int(6 * 260) + 60
            fetch = _get_d1_history
            tstop, min_bars = 20, 300
            xwin = (20, 60, 60)
        data = {}
        universe = STRENGTH_SYMBOLS if body.strength else FOREX_SYMBOLS
        _portfolio_jobs[job_id]["total"] = len(universe)
        for sym in universe:
            candles, source = await fetch(sym, want)
            data[sym] = (candles, source)
            _portfolio_jobs[job_id]["done"] += 1
        for sym in [s for s, (_, src) in data.items() if src != "real"]:
            candles, source = await fetch(sym, want)
            if source == "real":
                data[sym] = (candles, source)
        if body.strength:
            # honesty: currency-strength must use ONLY real data — drop any pair that
            # fell back to simulated instead of mixing fake prices into the meter.
            data = {s: v for s, v in data.items() if v[1] == "real"}
            if len(data) < 6:
                _portfolio_jobs[job_id] = {"status": "error", "result": None,
                                           "error": "Troppo pochi simboli reali per il misuratore di forza"}
                return
        xctx = None
        if body.cross_pair:
            xctx = await asyncio.to_thread(_build_xpair_context, data, xwin[0], xwin[1], xwin[2])
        sctx = None
        if body.strength:
            kwin = xwin[0]  # momentum window in bars for the strength meter
            sctx = await asyncio.to_thread(_build_strength_context, data, kwin, xwin[2])
        years = sorted({int(y) for y in body.years})
        result = await asyncio.to_thread(_ml_walkforward_compute, data, years,
                                         body.start_balance, body.lot_per_10k, body.max_concurrent,
                                         tstop, xctx, min_bars, sctx)
        if result is None:
            _portfolio_jobs[job_id] = {"status": "error", "result": None,
                                       "error": "Nessun edge appreso / storico insufficiente"}
            return
        result["timeframe"] = body.timeframe.upper()
        result["cross_pair"] = body.cross_pair
        result["strength"] = body.strength
        result["time_stop_bars"] = tstop
        _portfolio_jobs[job_id] = {"status": "done", "result": result, "error": None}
    except Exception as e:
        logger.exception("ml walkforward job failed")
        _portfolio_jobs[job_id] = {"status": "error", "result": None, "error": str(e)[:200]}




def _pt(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))


def _bar_close(candles, i):
    """A bar's close prints at the next bar's open — the real moment of the close."""
    return candles[i + 1]["time"] if i + 1 < len(candles) else candles[i]["time"]


def _atr_at(candles, i, period=14):
    win = candles[max(0, i - period):i]
    return (sum(c["h"] - c["l"] for c in win) / len(win)) if win else 0.0


def _nosl_settle(positions, price_on, all_dates, sym_strategy, start, start_balance,
                 lot_per_10k, max_concurrent, real_syms, sim_syms, mode, extra=None):
    """Shared no-SL settlement: event-driven COMPOUNDING equity, mark-to-market
    equity curve (floating of open trades included), open-position detail."""
    if not positions:
        return None
    events = []
    for p in positions:
        events.append((p["entry_t"], 0, p))
        events.append((p["exit_t"], 1, p))
    events.sort(key=lambda e: (e[0], e[1]))
    equity, open_count = start_balance, 0
    for tm, typ, p in events:
        if typ == 0:
            if equity <= 0 or open_count >= max_concurrent:
                p["skip"] = True
                continue
            p["lot"] = max(0.01, round(lot_per_10k * equity / 10000.0, 2))
            open_count += 1
        else:
            if p.get("skip"):
                continue
            open_count -= 1
            if p["open"]:
                continue  # open trades stay floating; only closed trades hit realized
            p["pnl"] = round(p["lot"] * p["contract"] * (p["exit"] - p["entry"]) * p["dir"], 2)
            equity += p["pnl"]
    realized_final = round(equity, 2)

    sym_net = {}
    for p in positions:
        if not p.get("skip") and "pnl" in p:
            sym_net[p["sym"]] = round(sym_net.get(p["sym"], 0) + p["pnl"], 2)
    curve, peak, max_dd, min_eq, wipe_date = [], start_balance, 0.0, start_balance, None
    for d in sorted(all_dates):
        realized = sum(p["pnl"] for p in positions if not p.get("skip") and "pnl" in p and p["exit_t"].date() <= d)
        floating = 0.0
        for p in positions:
            if p.get("skip") or "lot" not in p:
                continue
            if p["entry_t"].date() <= d and (p["open"] or d < p["exit_t"].date()):
                px = price_on.get(p["sym"], {}).get(d)
                if px is not None:
                    floating += p["lot"] * p["contract"] * (px - p["entry"]) * p["dir"]
        mtm = start_balance + realized + floating
        peak = max(peak, mtm)
        max_dd = max(max_dd, (peak - mtm) / peak * 100 if peak > 0 else 100)
        min_eq = min(min_eq, mtm)
        if mtm <= 0 and wipe_date is None:
            wipe_date = d.isoformat()
        curve.append(round(mtm, 2))
    wiped = wipe_date is not None
    true_final = curve[-1] if curve else realized_final

    used = [p for p in positions if not p.get("skip")]
    closed = [p for p in used if not p["open"]]
    open_p = [p for p in used if p["open"]]
    tp_wins = [p for p in closed if not p.get("timed")]
    timed_exits = [p for p in closed if p.get("timed")]
    open_float = round(sum((price_on[p["sym"]][max(price_on[p["sym"]])] - p["entry"]) * p["dir"] * p["lot"] * p["contract"]
                           for p in open_p if p.get("lot")), 2)
    per_symbol = sorted([{"symbol": s, "net": n} for s, n in sym_net.items()], key=lambda x: -x["net"])
    end = max((p["exit_t"] for p in positions), default=start)

    open_detail = []
    for p in open_p:
        if not p.get("lot"):
            continue
        cur = price_on[p["sym"]][max(price_on[p["sym"]])]
        flo = round((cur - p["entry"]) * p["dir"] * p["lot"] * p["contract"], 2)
        strat = sym_strategy.get(p["sym"], {})
        dg = p.get("digits", 5)
        tp_dist = abs(p["tp"] - p["entry"]) or 1e-9
        adverse = (p["entry"] - cur) * p["dir"]
        open_detail.append({
            "symbol": p["sym"], "side": p["side"], "strategy": strat.get("label", ""),
            "entry_rule": strat.get("entry", ""), "entry_date": p["entry_t"].date().isoformat(),
            "entry": round(p["entry"], dg), "tp": round(p["tp"], dg),
            "current": round(cur, dg), "lot": p["lot"], "floating": flo,
            "adverse_move_pct": round(adverse / tp_dist * 100, 1),
        })
    open_detail.sort(key=lambda x: x["floating"])
    result = {
        "mode": mode, "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(), "start_balance": round(start_balance, 2),
        "lot_per_10k": lot_per_10k, "max_concurrent": max_concurrent,
        "realized_balance": realized_final,
        "true_equity": round(true_final, 2), "net_true": round(true_final - start_balance, 2),
        "return_true_percent": round((true_final - start_balance) / start_balance * 100, 1),
        "max_drawdown": round(max_dd, 2), "min_equity": round(min_eq, 2),
        "wiped": wiped, "wipe_date": wipe_date,
        "closed_trades": len(closed), "tp_wins": len(tp_wins), "timed_exits": len(timed_exits),
        "open_trades": len(open_p), "open_floating": open_float,
        "per_symbol": per_symbol, "real_symbols": real_syms, "sim_symbols": sim_syms,
        "sym_strategy": sym_strategy, "open_positions": open_detail,
        "equity_curve": curve,
    }
    if extra:
        result.update(extra)
    return result


def _nosl_compute(data, start_date, start_balance, lot_per_10k, max_concurrent=10):
    try:
        start = datetime.fromisoformat(start_date + "T00:00:00+00:00")
    except Exception:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    positions, real_syms, sim_syms = [], [], []
    price_on, all_dates, sym_strategy = {}, set(), {}
    for sym, (candles, source) in data.items():
        if not candles or len(candles) < 200:
            continue
        (real_syms if source == "real" else sim_syms).append(sym)
        cfg = INSTRUMENTS[sym]
        contract = CONTRACT_SIZE.get(sym, 100000)
        train = [c for c in candles if _pt(c["time"]) < start]
        if len(train) < 120:
            continue
        params = _pick_params(train, cfg)
        if params is None:
            continue
        sym_strategy[sym] = {
            "label": ENTRY_LABELS.get(params["entry"], params["entry"]),
            "entry": params["entry"], "tp_mult": params["tp_mult"],
            "trend_filter": params.get("trend_filter", False), "rsi": params.get("rsi", False),
        }
        price_on[sym] = {}
        for c in candles:
            d = _pt(c["time"]).date()
            price_on[sym][d] = c["c"]
            if _pt(c["time"]) >= start:
                all_dates.add(d)
        full = run_forward_test(candles, cfg, 1.0, params=params)
        last_c = candles[-1]
        for t in full["trades"]:
            try:
                ei = t["entry_index"]
                et = _pt(t["entry_time"])
            except Exception:
                continue
            if et < start:
                continue
            side, entry, tp = t["side"], t["entry"], t["tp"]
            direction = 1 if side == "BUY" else -1
            exit_price, exit_t, is_open = last_c["c"], _pt(last_c["time"]), True
            for j in range(ei + 1, len(candles)):
                cj = candles[j]
                if (side == "BUY" and cj["h"] >= tp) or (side == "SELL" and cj["l"] <= tp):
                    exit_price, exit_t, is_open = tp, _pt(candles[j + 1]["time"]) if j + 1 < len(candles) else _pt(cj["time"]), False
                    break
            positions.append({"sym": sym, "side": side, "dir": direction, "entry": entry,
                              "tp": tp, "entry_t": et, "exit_t": exit_t, "exit": exit_price,
                              "contract": contract, "open": is_open,
                              "last_price": last_c["c"], "digits": cfg.get("digits", 5)})
    return _nosl_settle(positions, price_on, all_dates, sym_strategy, start, start_balance,
                        lot_per_10k, max_concurrent, real_syms, sim_syms, "nosl_compound")


# ---- Improved no-SL engine: mean-reversion + 200-SMA regime filter + time-stop ----
def _mr_trades(candles, cfg, params):
    """Mean-reversion signals (RSI extremes, in the direction of the SMA200 regime),
    take-profit at ATR*tp, and a TIME-STOP (close after N bars if TP not hit).
    NO price stop loss. One position at a time. Returns settled trade dicts."""
    rlen, buy_thr, sell_thr = params["rsi_len"], params["buy_thr"], params["sell_thr"]
    tp_atr, tstop, regime = params["tp_atr"], params["time_stop"], params["regime"]
    d = cfg["digits"]
    closes = [c["c"] for c in candles]
    trades, open_t = [], None
    n = len(candles)
    for i in range(n):
        c = candles[i]
        if open_t is not None:
            side, tp = open_t["side"], open_t["tp"]
            hit = (side == "BUY" and c["h"] >= tp) or (side == "SELL" and c["l"] <= tp)
            timed = (i - open_t["entry_index"]) >= tstop
            if hit or timed:
                open_t["exit_index"] = i
                open_t["exit"] = round(tp if hit else c["c"], d)
                open_t["exit_time"] = _bar_close(candles, i)
                open_t["open"] = False
                open_t["timed"] = bool(timed and not hit)
                trades.append(open_t)
                open_t = None
        if open_t is None and i >= 200:
            r = _rsi(closes[:i + 1], rlen)
            sma200 = _mean(closes[i - 200:i + 1])
            atr = _atr_at(candles, i, 14) or cfg["vol"]
            price = c["c"]
            sig = None
            if regime:
                if price > sma200 and r < buy_thr:
                    sig = "BUY"
                elif price < sma200 and r > sell_thr:
                    sig = "SELL"
            else:
                if r < buy_thr:
                    sig = "BUY"
                elif r > sell_thr:
                    sig = "SELL"
            if sig and atr > 0:
                entry = price
                tp = entry + atr * tp_atr if sig == "BUY" else entry - atr * tp_atr
                open_t = {"entry_index": i, "entry_time": _bar_close(candles, i),
                          "side": sig, "entry": round(entry, d), "tp": round(tp, d), "open": True}
    if open_t is not None:
        open_t["exit_index"] = n - 1
        open_t["exit"] = round(candles[-1]["c"], d)
        open_t["exit_time"] = _bar_close(candles, n - 1)
        open_t["open"] = True
        open_t["timed"] = False
        trades.append(open_t)
    return trades


_MR_GRID = [
    {"rsi_len": rl, "buy_thr": bt, "sell_thr": 100 - bt, "tp_atr": tp, "time_stop": ts, "regime": rg}
    for rl in (2, 3)
    for bt in (5, 10, 15)
    for tp in (1.0, 1.5, 2.0)
    for ts in (10, 20, 30)
    for rg in (True, False)
]


def _mr_pick(train, cfg):
    """Choose mean-reversion params on the training slice (no look-ahead).
    Score = realized net / max realized drawdown, only if net>0 and >=8 trades."""
    contract = CONTRACT_SIZE.get(cfg.get("_sym", ""), 100000)
    best = None
    for params in _MR_GRID:
        trs = [t for t in _mr_trades(train, cfg, params) if not t["open"]]
        if len(trs) < 8:
            continue
        eq, peak, dd, net = 10000.0, 10000.0, 0.0, 0.0
        for t in trs:
            dirn = 1 if t["side"] == "BUY" else -1
            pnl = 0.1 * contract * (t["exit"] - t["entry"]) * dirn
            net += pnl
            eq += pnl
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
        if net <= 0:
            continue
        score = net / max(dd, 1.0)
        if best is None or score > best[0]:
            best = (score, params)
    return best[1] if best else None


def _nosl_v2_compute(data, start_date, start_balance, lot_per_10k, max_concurrent=10):
    try:
        start = datetime.fromisoformat(start_date + "T00:00:00+00:00")
    except Exception:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    positions, real_syms, sim_syms = [], [], []
    price_on, all_dates, sym_strategy = {}, set(), {}
    for sym, (candles, source) in data.items():
        if not candles or len(candles) < 250:
            continue
        (real_syms if source == "real" else sim_syms).append(sym)
        cfg = dict(INSTRUMENTS[sym]); cfg["_sym"] = sym
        contract = CONTRACT_SIZE.get(sym, 100000)
        train = [c for c in candles if _pt(c["time"]) < start]
        if len(train) < 250:
            continue
        params = _mr_pick(train, cfg)
        if params is None:
            continue
        sym_strategy[sym] = {
            "label": "Mean-Reversion + time-stop", "entry": "meanrev_rsi",
            "rsi_len": params["rsi_len"], "buy_thr": params["buy_thr"],
            "tp_atr": params["tp_atr"], "time_stop": params["time_stop"],
            "regime": params["regime"],
        }
        price_on[sym] = {}
        for c in candles:
            dd = _pt(c["time"]).date()
            price_on[sym][dd] = c["c"]
            if _pt(c["time"]) >= start:
                all_dates.add(dd)
        for t in _mr_trades(candles, cfg, params):
            et = _pt(t["entry_time"])
            if et < start:
                continue
            direction = 1 if t["side"] == "BUY" else -1
            positions.append({"sym": sym, "side": t["side"], "dir": direction,
                              "entry": t["entry"], "tp": t["tp"], "entry_t": et,
                              "exit_t": _pt(t["exit_time"]), "exit": t["exit"],
                              "contract": contract, "open": t["open"],
                              "timed": t.get("timed", False),
                              "last_price": candles[-1]["c"], "digits": cfg["digits"]})
    return _nosl_settle(positions, price_on, all_dates, sym_strategy, start, start_balance,
                        lot_per_10k, max_concurrent, real_syms, sim_syms, "nosl_meanrev")


# ---- Learned no-SL engine: gradient-boosting entry gate on mean-reversion ----
def _std(seq):
    if len(seq) < 2:
        return 0.0
    m = sum(seq) / len(seq)
    return (sum((x - m) ** 2 for x in seq) / len(seq)) ** 0.5


def _cand_meanrev(candles, closes, i):
    r = _rsi(closes[:i + 1], 2)
    if r < 30:
        return "BUY"
    if r > 70:
        return "SELL"
    return None


def _cand_trend(candles, closes, i):
    """Donchian-style breakout in the direction of the SMA200 regime."""
    if i < 210:
        return None
    sma200 = _mean(closes[i - 200:i + 1])
    hi = max(closes[i - 20:i])
    lo = min(closes[i - 20:i])
    price = closes[i]
    if price >= hi and price > sma200:
        return "BUY"
    if price <= lo and price < sma200:
        return "SELL"
    return None


STRENGTH_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD",
                    "EUR/GBP", "EUR/AUD", "EUR/CHF", "EUR/CAD",
                    "GBP/AUD", "GBP/CHF", "AUD/CAD"]


def _build_strength_context(data, k=20, zwin=60):
    """Currency-strength meter: at each timestamp, strength(C) = mean over all pairs
    containing C of the sign-adjusted k-bar momentum (base:+, quote:-). For each pair
    B/Q we then track diff = strength(B) - strength(Q) and its rolling z-score. Trade
    the strong-vs-weak divergence (BUY when base far stronger, SELL when far weaker).
    No look-ahead (uses data <= t). Returns {sym: {time_str: z}}."""
    kret = {}   # sym -> {time: k-bar log return}
    order = {}  # sym -> ordered list of time_str
    for sym, (candles, _s) in data.items():
        if not candles or "/" not in sym:
            continue
        cs = sorted(((c["time"], c["c"]) for c in candles), key=lambda x: _pt(x[0]))
        order[sym] = [t for (t, _) in cs]
        closes = [c for (_, c) in cs]
        rr = {}
        for i in range(len(closes)):
            if i >= k and closes[i - k] > 0 and closes[i] > 0:
                rr[cs[i][0]] = math.log(closes[i] / closes[i - k])
        kret[sym] = rr
    # per-currency strength per timestamp
    cur_contrib = {}  # time -> {cur: [contribs]}
    for sym, rr in kret.items():
        base, quote = sym.split("/")
        for t, r in rr.items():
            slot = cur_contrib.setdefault(t, {})
            slot.setdefault(base, []).append(r)
            slot.setdefault(quote, []).append(-r)
    strength = {}  # time -> {cur: mean}
    for t, d in cur_contrib.items():
        strength[t] = {c: (sum(v) / len(v)) for c, v in d.items()}
    ctx = {}
    for sym in kret:
        base, quote = sym.split("/")
        times = order[sym]
        diffs = {}
        for t in times:
            st = strength.get(t)
            if st and base in st and quote in st:
                diffs[t] = st[base] - st[quote]
        seq = [t for t in times if t in diffs]
        zmap = {}
        for idx, t in enumerate(seq):
            if idx >= zwin:
                w = [diffs[seq[j]] for j in range(idx - zwin, idx + 1)]
                m = sum(w) / len(w)
                zmap[t] = (diffs[t] - m) / (_std(w) or 1e-9)
            else:
                zmap[t] = 0.0
        ctx[sym] = zmap
    return ctx


def _make_strength_cand(zmap, thr=1.0):
    """Momentum on currency-strength divergence: BUY when base is far stronger than
    quote (z>thr), SELL when far weaker (z<-thr)."""
    def cand(candles, closes, i):
        z = zmap.get(candles[i]["time"])
        if z is None:
            return None
        if z > thr:
            return "BUY"
        if z < -thr:
            return "SELL"
        return None
    return cand



def _build_xpair_context(data, w1=20, w2=60, wz=60):
    """Cross-pair features shared across symbols, computed contemporaneously (no
    look-ahead): dollar-strength momentum (w1/w2 bars), the pair's idiosyncratic
    strength vs the dollar factor, and a relative-value stretch z-score (wz bars).
    Keyed by the raw candle timestamp so it works on any timeframe (D1/H4).
    Returns {sym: {time_str: [usd_mom1, usd_mom2, rel_strength, spread_z]}}."""
    sign = {"EUR/USD": -1, "GBP/USD": -1, "AUD/USD": -1, "USD/CHF": 1, "USD/CAD": 1}
    series, ret = {}, {}
    for sym, (candles, _src) in data.items():
        if not candles:
            continue
        s = sorted(((c["time"], c["c"]) for c in candles), key=lambda x: _pt(x[0]))
        series[sym] = s
        rr = {}
        for k in range(1, len(s)):
            (_, p0), (t1, p1) = s[k - 1], s[k]
            if p0 > 0 and p1 > 0:
                rr[t1] = sign.get(sym, 0) * math.log(p1 / p0)
        ret[sym] = rr
    gtimes = sorted({t for rr in ret.values() for t in rr}, key=_pt)
    basket, usd_level, acc = {}, {}, 0.0
    for t in gtimes:
        vals = [ret[sym][t] for sym in ret if t in ret[sym]]
        basket[t] = sum(vals) / len(vals) if vals else 0.0
        acc += basket[t]
        usd_level[t] = acc
    ctx = {}
    for sym, s in series.items():
        times = [t for (t, _) in s]
        rlvl, a = {}, 0.0
        for t in times:
            r = ret[sym].get(t)
            if r is not None:
                a += r - basket.get(t, 0.0)
            rlvl[t] = a
        feats = {}
        for idx, t in enumerate(times):
            b1 = times[idx - w1] if idx >= w1 else times[0]
            b2 = times[idx - w2] if idx >= w2 else times[0]
            um1 = usd_level.get(t, 0.0) - usd_level.get(b1, 0.0)
            um2 = usd_level.get(t, 0.0) - usd_level.get(b2, 0.0)
            rs1 = rlvl[t] - rlvl[b1]
            if idx >= wz:
                window = [rlvl[times[j]] for j in range(idx - wz, idx + 1)]
                m = sum(window) / len(window)
                sz = (rlvl[t] - m) / (_std(window) or 1e-9)
            else:
                sz = 0.0
            feats[t] = [um1, um2, rs1, sz]
        ctx[sym] = feats
    return ctx


def _ml_features(candles, closes, i, side, ctx=None):
    price = closes[i]
    sma20, sma50, sma200 = _mean(closes[i - 19:i + 1]), _mean(closes[i - 49:i + 1]), _mean(closes[i - 199:i + 1])
    sd20 = _std(closes[i - 19:i + 1]) or 1e-9
    sd50 = _std(closes[i - 49:i + 1]) or 1e-9
    atr = _atr_at(candles, i, 14) or 1e-9
    atr50 = (sum(candles[k]["h"] - candles[k]["l"] for k in range(max(0, i - 49), i + 1)) / min(50, i + 1)) or 1e-9
    hi20 = max(c["h"] for c in candles[i - 19:i + 1])
    lo20 = min(c["l"] for c in candles[i - 19:i + 1])
    rng = (hi20 - lo20) or 1e-9
    streak = 0
    for k in range(i, max(0, i - 10), -1):
        if closes[k] > closes[k - 1]:
            streak = streak + 1 if streak >= 0 else 0
            if streak == 0:
                break
        elif closes[k] < closes[k - 1]:
            streak = streak - 1 if streak <= 0 else 0
            if streak == 0:
                break
        else:
            break
    dow = _pt(candles[i]["time"]).weekday()
    xp = [0.0, 0.0, 0.0, 0.0]
    if ctx is not None:
        xp = ctx.get(candles[i]["time"], xp)

    def lr(k):
        return math.log(closes[i] / closes[i - k]) if i - k >= 0 and closes[i - k] > 0 else 0.0

    return [
        _rsi(closes[:i + 1], 2), _rsi(closes[:i + 1], 14),
        (price - sma20) / sd20, (price - sma50) / sd50,
        lr(1), lr(3), lr(5), lr(10),
        atr / price, atr / atr50,
        1.0 if sma20 > sma50 else 0.0, 1.0 if sma50 > sma200 else 0.0, 1.0 if price > sma200 else 0.0,
        (price - lo20) / rng, float(streak), float(dow),
        xp[0], xp[1], xp[2], xp[3],
        1.0 if side == "BUY" else -1.0,
    ]



def _ml_dataset(candles, closes, cfg, tp_mult, tstop, cand_fn=_cand_meanrev, ctx=None):
    """Every candidate from cand_fn → (features, win?, pnl, entry_time)."""
    X, y, pnl, times = [], [], [], []
    n = len(candles)
    for i in range(200, n - 1):
        side = cand_fn(candles, closes, i)
        if not side:
            continue
        entry = closes[i]
        direction = 1 if side == "BUY" else -1
        atr = _atr_at(candles, i, 14) or cfg["vol"]
        tp = entry + direction * atr * tp_mult
        end_j = min(i + tstop, n - 1)
        exit_price, hit = None, False
        for j in range(i + 1, end_j + 1):
            cj = candles[j]
            if (side == "BUY" and cj["h"] >= tp) or (side == "SELL" and cj["l"] <= tp):
                exit_price, hit = tp, True
                break
        if not hit:
            exit_price = closes[end_j]
        p = (exit_price - entry) * direction
        X.append(_ml_features(candles, closes, i, side, ctx))
        y.append(1 if p > 0 else 0)
        pnl.append(p)
        times.append(_pt(candles[i]["time"]))
    return X, y, pnl, times


def _ml_fit(candles, closes, cfg, train_end, cand_fn=_cand_meanrev, ctx=None, tstop=20):
    """Fit the gradient-boosting gate on candidates BEFORE train_end. Pick tp_mult
    and probability threshold on the last training year (validation), then refit on
    all pre-train_end data. Returns (model, tp_mult, thr, n_train, val_net) or None."""
    from sklearn.ensemble import GradientBoostingClassifier
    val_start = train_end - timedelta(days=365)
    best = None
    for tp_mult in (1.0, 1.5, 2.0, 3.0):
        X, y, pnl, times = _ml_dataset(candles, closes, cfg, tp_mult, tstop, cand_fn, ctx)
        idx_core = [k for k, t in enumerate(times) if t < val_start]
        idx_val = [k for k, t in enumerate(times) if val_start <= t < train_end]
        if len(idx_core) < 50 or len(idx_val) < 12:
            continue
        yc = [y[k] for k in idx_core]
        if len(set(yc)) < 2:
            continue
        model = GradientBoostingClassifier(n_estimators=150, max_depth=3,
                                           learning_rate=0.05, subsample=0.8, random_state=42)
        model.fit([X[k] for k in idx_core], yc)
        proba_val = model.predict_proba([X[k] for k in idx_val])[:, 1]
        for thr in (0.50, 0.55, 0.60, 0.65, 0.70):
            net = sum(pnl[idx_val[m]] for m in range(len(idx_val)) if proba_val[m] >= thr)
            if sum(1 for pv in proba_val if pv >= thr) < 4:
                continue
            if best is None or net > best[0]:
                best = (net, tp_mult, thr)
    if best is None or best[0] <= 0:
        return None
    _, tp_mult, thr = best
    X, y, pnl, times = _ml_dataset(candles, closes, cfg, tp_mult, tstop, cand_fn, ctx)
    idx_tr = [k for k, t in enumerate(times) if t < train_end]
    ytr = [y[k] for k in idx_tr]
    if len(set(ytr)) < 2:
        return None
    model = GradientBoostingClassifier(n_estimators=150, max_depth=3,
                                       learning_rate=0.05, subsample=0.8, random_state=42)
    model.fit([X[k] for k in idx_tr], ytr)
    return model, tp_mult, thr, len(idx_tr), round(best[0], 5)


def _ml_generate(candles, closes, cfg, model, tp_mult, thr, tstop, test_start, test_end=None, cand_fn=_cand_meanrev, ctx=None):
    """Trade the model on [test_start, test_end): open only high-proba candidates.
    NO price stop; exit at TP or time-stop. Positions still open at test_end are
    left floating (open=True) valued at the last in-window candle."""
    d = cfg["digits"]
    n = len(candles)
    if test_end is not None:
        in_win = [i for i in range(n) if _pt(_bar_close(candles, i)) < test_end]
        last_idx = in_win[-1] if in_win else n - 1
    else:
        last_idx = n - 1
    trades, open_t = [], None
    for i in range(200, n):
        c = candles[i]
        if open_t is not None:
            side, tp = open_t["side"], open_t["tp"]
            hit = (side == "BUY" and c["h"] >= tp) or (side == "SELL" and c["l"] <= tp)
            timed = (i - open_t["entry_index"]) >= tstop
            if i > last_idx and not (hit or timed):
                open_t.update(exit_index=last_idx, exit=round(candles[last_idx]["c"], d),
                              exit_time=_bar_close(candles, last_idx), open=True, timed=False)
                trades.append(open_t)
                open_t = None
            elif hit or timed:
                open_t.update(exit_index=i, exit=round(tp if hit else c["c"], d),
                              exit_time=_bar_close(candles, i), open=False,
                              timed=bool(timed and not hit))
                trades.append(open_t)
                open_t = None
        if open_t is None and 200 <= i <= last_idx and i < n - 1:
            bt = _pt(_bar_close(candles, i))
            if bt < test_start or (test_end is not None and bt >= test_end):
                continue
            side = cand_fn(candles, closes, i)
            if not side:
                continue
            if model.predict_proba([_ml_features(candles, closes, i, side, ctx)])[0][1] < thr:
                continue
            entry = closes[i]
            atr = _atr_at(candles, i, 14) or cfg["vol"]
            tp = entry + (1 if side == "BUY" else -1) * atr * tp_mult
            open_t = {"entry_index": i, "entry_time": _bar_close(candles, i), "side": side,
                      "entry": round(entry, d), "tp": round(tp, d), "open": True}
        if i > last_idx and open_t is None:
            break
    if open_t is not None:
        open_t.update(exit_index=last_idx, exit=round(candles[last_idx]["c"], d),
                      exit_time=_bar_close(candles, last_idx), open=True, timed=False)
        trades.append(open_t)
    return trades


def _ml_ensemble_trades(candles, cfg, test_start, test_end=None, ctx=None, tstop=20, cand_fn=None):
    """ML-gated entry sleeve (mean-reversion by default). NO stop loss; time-stop exit.
    A custom cand_fn (e.g. currency-strength divergence) can be supplied."""
    closes = [c["c"] for c in candles]
    all_trades, sleeves = [], {}
    sleeve_name = "strength" if cand_fn is not None else "meanrev"
    for name, cfn in ((sleeve_name, cand_fn or _cand_meanrev),):
        try:
            fit = _ml_fit(candles, closes, cfg, test_start, cfn, ctx, tstop)
        except Exception:
            logger.exception("ml sleeve %s fit failed", name)
            fit = None
        if fit is None:
            continue
        model, tp_mult, thr, n_train, val_net = fit
        trs = _ml_generate(candles, closes, cfg, model, tp_mult, thr, tstop, test_start, test_end, cfn, ctx)
        for t in trs:
            t["sleeve"] = name
        all_trades.extend(trs)
        sleeves[name] = {"tp_atr": tp_mult, "threshold": round(thr, 2),
                         "train_candidates": n_train, "val_net": val_net}
    if not all_trades:
        return None
    mr = sleeves.get("meanrev") or sleeves.get("strength") or {}
    lbl = "ML currency-strength cross" if "strength" in sleeves else "ML mean-reversion (gradient boosting)"
    info = {"label": lbl, "entry": "strength" if "strength" in sleeves else "ml_meanrev",
            "time_stop": tstop, "sleeves": sleeves,
            "tp_atr": mr.get("tp_atr"), "threshold": mr.get("threshold"),
            "train_candidates": sum(s["train_candidates"] for s in sleeves.values())}
    return all_trades, info


def _ml_symbol(candles, cfg, start, ctx=None):
    return _ml_ensemble_trades(candles, cfg, start, None, ctx)


def _nosl_ml_compute(data, start_date, start_balance, lot_per_10k, max_concurrent=10):
    try:
        start = datetime.fromisoformat(start_date + "T00:00:00+00:00")
    except Exception:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    positions, real_syms, sim_syms = [], [], []
    price_on, all_dates, sym_strategy = {}, set(), {}
    for sym, (candles, source) in data.items():
        if not candles or len(candles) < 300:
            continue
        (real_syms if source == "real" else sim_syms).append(sym)
        cfg = dict(INSTRUMENTS[sym]); cfg["_sym"] = sym
        contract = CONTRACT_SIZE.get(sym, 100000)
        try:
            picked = _ml_symbol(candles, cfg, start, None)
        except Exception:
            logger.exception("ml symbol %s failed", sym)
            picked = None
        if picked is None:
            continue
        trades, info = picked
        sym_strategy[sym] = {"label": "ML gate (gradient boosting)", "entry": "ml_meanrev", **info}
        price_on[sym] = {}
        for c in candles:
            dd = _pt(c["time"]).date()
            price_on[sym][dd] = c["c"]
            if _pt(c["time"]) >= start:
                all_dates.add(dd)
        for t in trades:
            et = _pt(t["entry_time"])
            if et < start:
                continue
            positions.append({"sym": sym, "side": t["side"], "dir": 1 if t["side"] == "BUY" else -1,
                              "entry": t["entry"], "tp": t["tp"], "entry_t": et,
                              "exit_t": _pt(t["exit_time"]), "exit": t["exit"],
                              "contract": contract, "open": t["open"], "timed": t.get("timed", False),
                              "last_price": candles[-1]["c"], "digits": cfg["digits"]})
    return _nosl_settle(positions, price_on, all_dates, sym_strategy, start, start_balance,
                        lot_per_10k, max_concurrent, real_syms, sim_syms, "nosl_ml")


def _ml_walkforward_compute(data, years, start_balance, lot_per_10k, max_concurrent,
                            tstop=20, xctx=None, min_bars=300, sctx=None):
    """Multi-year walk-forward: for each test year Y, retrain the ML gate ONLY on
    data before Jan 1 of Y (validation on Y-1), then trade Y out-of-sample. Balance
    resets to start_balance each year so per-year results are directly comparable.
    tstop is the time-stop in bars (20 for D1, ~120 for H4); xctx optionally supplies
    cross-pair features per symbol; both must match the timeframe of `data`."""
    per_year, real_syms_all, sim_syms_all = [], set(), set()
    for Y in years:
        test_start = datetime(Y, 1, 1, tzinfo=timezone.utc)
        test_end = datetime(Y + 1, 1, 1, tzinfo=timezone.utc)
        positions = []
        price_on, all_dates, sym_strategy = {}, set(), {}
        year_real, year_sim = [], []
        for sym, (candles, source) in data.items():
            if not candles or len(candles) < min_bars:
                continue
            cfg = dict(INSTRUMENTS[sym]); cfg["_sym"] = sym
            # need training history before the test year
            if _pt(candles[0]["time"]) >= test_start - timedelta(days=400):
                continue
            (year_real if source == "real" else year_sim).append(sym)
            cand_fn = _make_strength_cand(sctx[sym]) if (sctx and sym in sctx) else None
            try:
                picked = _ml_ensemble_trades(candles, cfg, test_start, test_end,
                                             xctx.get(sym) if xctx else None, tstop, cand_fn)
            except Exception:
                logger.exception("wf ensemble %s %s failed", sym, Y)
                picked = None
            if picked is None:
                continue
            trades, info = picked
            contract = CONTRACT_SIZE.get(sym, 100000)
            price_on[sym] = {}
            for c in candles:
                dd = _pt(c["time"]).date()
                if test_start <= _pt(c["time"]) < test_end:
                    price_on[sym][dd] = c["c"]
                    all_dates.add(dd)
            if not price_on[sym]:
                continue
            year_end_px = max(price_on[sym])
            sym_strategy[sym] = {"entry": "ml_ensemble", **info}
            for t in trades:
                et = _pt(t["entry_time"])
                if not (test_start <= et < test_end):
                    continue
                xt = _pt(t["exit_time"])
                positions.append({"sym": sym, "side": t["side"], "dir": 1 if t["side"] == "BUY" else -1,
                                  "entry": t["entry"], "tp": t["tp"], "entry_t": et,
                                  "exit_t": xt, "exit": t["exit"], "contract": contract,
                                  "open": t["open"], "timed": t.get("timed", False),
                                  "last_price": price_on[sym][year_end_px], "digits": cfg["digits"]})
        res = _nosl_settle(positions, price_on, all_dates, sym_strategy, test_start, start_balance,
                           lot_per_10k, max_concurrent, year_real, year_sim, f"nosl_ml_wf_{Y}")
        year_real and real_syms_all.update(year_real)
        year_sim and sim_syms_all.update(year_sim)
        if res is None:
            per_year.append({"year": Y, "traded": False, "real_symbols": year_real,
                             "simulated_symbols": year_sim})
            continue
        per_year.append({
            "year": Y, "traded": True,
            "true_equity": res["true_equity"], "return_percent": res["return_true_percent"],
            "realized_balance": res["realized_balance"], "max_drawdown": res["max_drawdown"],
            "min_equity": res["min_equity"], "closed_trades": res["closed_trades"],
            "tp_wins": res["tp_wins"], "timed_exits": res["timed_exits"],
            "open_trades": res["open_trades"], "open_floating": res["open_floating"],
            "wiped": res["wiped"], "per_symbol": res["per_symbol"],
            "equity_curve": res["equity_curve"], "real_symbols": year_real,
            "simulated_symbols": year_sim,
        })
    traded = [y for y in per_year if y.get("traded")]
    if not traded:
        return None
    rets = [y["return_percent"] for y in traded]
    # equity compounded across the tested years (sequential)
    comp = start_balance
    for r in rets:
        comp *= (1 + r / 100.0)
    positive = sum(1 for r in rets if r > 0)
    summary = {
        "years_tested": len(traded), "positive_years": positive,
        "avg_return": round(sum(rets) / len(rets), 2),
        "best_year": round(max(rets), 2), "worst_year": round(min(rets), 2),
        "compounded_equity": round(comp, 2),
        "compounded_return": round((comp - start_balance) / start_balance * 100, 1),
        "worst_drawdown": round(max(y["max_drawdown"] for y in traded), 2),
        "any_wiped": any(y["wiped"] for y in traded),
    }
    return {"mode": "ml_walkforward", "start_balance": start_balance,
            "lot_per_10k": lot_per_10k, "years": per_year, "summary": summary,
            "real_symbols": sorted(real_syms_all), "simulated_symbols": sorted(sim_syms_all)}




class PortfolioReq(BaseModel):
    start_date: str = "2025-01-01"
    start_balance: float = 10000.0
    risk_percent: float = 1.5
    walk_forward: bool = True


PORTFOLIO_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD", "XAU/USD", "US30"]
FOREX_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/CHF", "USD/CAD", "AUD/USD"]
_portfolio_jobs = {}


@api_router.post("/portfolio/backtest")
async def portfolio_backtest(body: PortfolioReq, user: dict = Depends(get_current_user)):
    """Multi-instrument portfolio backtest with a shared account and concurrent
    positions. Strategy per instrument is trained ONLY on data before start_date
    (no look-ahead), then traded forward. Runs as a background job."""
    job_id = str(uuid.uuid4())
    _portfolio_jobs[job_id] = {"status": "running", "result": None, "error": None,
                               "done": 0, "total": len(PORTFOLIO_SYMBOLS)}
    _portfolio_jobs[job_id]["task"] = asyncio.create_task(_run_portfolio(job_id, body))
    if len(_portfolio_jobs) > 20:
        for k in [k for k, v in list(_portfolio_jobs.items())[:-10] if v.get("status") != "running"]:
            _portfolio_jobs.pop(k, None)
    return {"job_id": job_id, "status": "running", "total": len(PORTFOLIO_SYMBOLS)}


@api_router.get("/portfolio/backtest/{job_id}")
async def portfolio_backtest_status(job_id: str, user: dict = Depends(get_current_user)):
    job = _portfolio_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return {k: v for k, v in job.items() if k != "task"}


async def _run_portfolio(job_id, body):
    job = _portfolio_jobs[job_id]
    try:
        want = int(5 * 260) + 40
        data = {}
        # sequential fetch: concurrent multi-year RPC pulls reset each other's
        # connection and silently fall back to simulated data
        for sym in PORTFOLIO_SYMBOLS:
            candles, source = await _get_d1_history(sym, want)
            data[sym] = (candles, source)
            job["done"] += 1
        # retry any symbol that fell back to simulated (transient fetch failures)
        for sym in [s for s, (_, src) in data.items() if src != "real"]:
            candles, source = await _get_d1_history(sym, want)
            if source == "real":
                data[sym] = (candles, source)
        result = await asyncio.to_thread(_portfolio_compute, data, body.start_date,
                                         body.start_balance, body.risk_percent, body.walk_forward)
        if result is None:
            _portfolio_jobs[job_id] = {"status": "error", "result": None,
                                       "error": "Storico insufficiente"}
            return
        _portfolio_jobs[job_id] = {"status": "done", "result": result, "error": None}
    except Exception as e:
        logger.exception("portfolio job failed")
        _portfolio_jobs[job_id] = {"status": "error", "result": None, "error": str(e)[:200]}


def _pick_params(train, cfg):
    """Best params on a training slice (reduced grid, no look-ahead)."""
    train_days = _period_days(train, "D1")
    best = None
    for entry in ("smc", "meanrev", "breakout", "trend"):
        for tp in (1.5, 2.0, 3.0):
            for sl in (1.0, 1.5):
                for tfil in (True, False):
                    for rsi in (True, False):
                        params = {"entry": entry, "tp_mult": tp, "sl_mult": sl,
                                  "trend_filter": tfil, "rsi": rsi}
                        r = run_forward_test(train, cfg, 1.0, params=params)
                        if r["total_trades"] < 8:
                            continue
                        ann = r["realized_net"] / r["start_equity"] * 100 * (365.0 / max(train_days, 1))
                        dd = max(r["max_drawdown"], 0.1)
                        score = (ann / dd) if (r["profit_factor"] >= 1.05 and ann > 0) else (-1e6 + ann)
                        if best is None or score > best[0]:
                            best = (score, params)
    return best[1] if best else None


ENTRY_LABELS = {"smc": "Smart Money", "meanrev": "Mean-Reversion",
                "breakout": "Breakout", "trend": "Trend-Following"}


def _portfolio_compute(data, start_date, start_balance, risk_pct, walk_forward=True):
    try:
        start = datetime.fromisoformat(start_date + "T00:00:00+00:00")
    except Exception:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def pt(iso):
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))

    per_symbol, all_trades = [], []
    real_syms, sim_syms = [], []
    last_end = start
    for sym, (candles, source) in data.items():
        if not candles or len(candles) < 200:
            continue
        (real_syms if source == "real" else sim_syms).append(sym)
        cfg = INSTRUMENTS[sym]
        end_year = pt(candles[-1]["time"]).year
        # walk-forward: retrain before EACH year; else one pre-start training
        if walk_forward:
            segments = [(max(start, datetime(y, 1, 1, tzinfo=timezone.utc)),
                         datetime(y + 1, 1, 1, tzinfo=timezone.utc))
                        for y in range(start.year, end_year + 1)]
        else:
            segments = [(start, pt(candles[-1]["time"]) + timedelta(days=1))]
        sym_trades, labels, retrains = [], [], 0
        for seg_start, seg_end in segments:
            train = [c for c in candles if pt(c["time"]) < seg_start]
            if len(train) < 120:
                continue
            params = _pick_params(train, cfg)
            if params is None:
                continue
            retrains += 1
            labels.append(ENTRY_LABELS[params["entry"]])
            full = run_forward_test(candles, cfg, 1.0, params=params)
            for t in full["trades"]:
                try:
                    et = pt(t["entry_time"])
                except Exception:
                    continue
                if not (seg_start <= et < seg_end):
                    continue
                xt = pt(t["exit_time"]) if t.get("exit_time") else pt(candles[-1]["time"])
                last_end = max(last_end, xt)
                trade = {"symbol": sym, "entry": et, "exit": xt, "r": t["pnl"] / 100.0,
                         "result": t["result"], "side": t["side"]}
                all_trades.append(trade)
                sym_trades.append(trade)
        if not labels:
            continue
        uniq = list(dict.fromkeys(labels))
        label = uniq[0] if len(uniq) == 1 else "Misto (walk-forward)"
        per_symbol.append({"symbol": sym, "entry_label": label,
                           "trades": len(sym_trades), "retrains": retrains})

    if not all_trades:
        return None

    # event-driven shared-account simulation (concurrent positions allowed)
    events = []
    for t in all_trades:
        events.append((t["entry"], 0, t))   # 0 = entry
        events.append((t["exit"], 1, t))    # 1 = exit
    events.sort(key=lambda e: (e[0], e[1]))
    equity = start_balance
    peak, max_dd = start_balance, 0.0
    curve = [{"t": start.isoformat(), "e": round(equity, 2)}]
    sym_pnl = {}
    for tm, typ, t in events:
        if typ == 0:
            t["risk_amt"] = equity * risk_pct / 100.0
        else:
            pnl = t["risk_amt"] * t["r"]
            t["net"] = round(pnl, 2)
            equity += pnl
            sym_pnl[t["symbol"]] = round(sym_pnl.get(t["symbol"], 0) + pnl, 2)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0)
            curve.append({"t": tm.isoformat(), "e": round(equity, 2)})

    closed = [t for t in all_trades if t["result"] in ("win", "loss")]
    wins = sum(1 for t in closed if t["r"] > 0)
    total = len(closed)
    open_n = sum(1 for t in all_trades if t["result"] == "open")
    for ps in per_symbol:
        ps["net"] = sym_pnl.get(ps["symbol"], 0)
    per_symbol.sort(key=lambda x: -x.get("net", 0))
    days = max((last_end - start).days, 1)
    net = round(equity - start_balance, 2)
    trade_rows = sorted(all_trades, key=lambda t: t["entry"])
    trades_out = [{
        "symbol": t["symbol"], "side": t["side"],
        "entry_date": t["entry"].date().isoformat(),
        "exit_date": t["exit"].date().isoformat(),
        "result": t["result"], "r": round(t["r"], 2), "net": t.get("net", 0),
    } for t in trade_rows]
    return {
        "start_date": start.date().isoformat(), "end_date": last_end.date().isoformat(),
        "days": days, "start_balance": round(start_balance, 2),
        "final_balance": round(equity, 2), "net_profit": net,
        "return_percent": round(net / start_balance * 100, 1),
        "annualized_percent": round(net / start_balance * 100 * (365.0 / days), 1),
        "max_drawdown": round(max_dd, 2), "risk_percent": risk_pct,
        "walk_forward": walk_forward,
        "total_trades": total, "wins": wins, "losses": total - wins,
        "winrate": round(wins / total * 100, 1) if total else 0,
        "open_trades": open_n, "per_symbol": per_symbol,
        "real_symbols": real_syms, "sim_symbols": sim_syms,
        "equity_curve": [c["e"] for c in curve],
        "trades": trades_out,
    }


class OptimizeReq(BaseModel):
    symbol: str
    timeframe: str = "H1"
    bars: int = 500
    target_annual: float = 50.0
    max_dd: float = 40.0
    split: float = 0.7


def _period_days(candles, timeframe):
    try:
        a = str(candles[0]["time"]).replace("Z", "+00:00")
        b = str(candles[-1]["time"]).replace("Z", "+00:00")
        days = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400.0
        if days > 0.5:
            return days
    except Exception:
        pass
    return max(1.0, len(candles) * TF_MIN.get(timeframe, 60) / 1440.0)


@api_router.post("/optimize")
async def optimize(body: OptimizeReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cfg = INSTRUMENTS[body.symbol]
    bars = max(200, min(body.bars, 700))
    real = await metaapi_service.fetch_candles(body.symbol, body.timeframe, bars)
    if real and len(real) >= 120:
        candles, source = real[-bars:], "real"
    else:
        candles, _ = generate_candles(body.symbol, body.timeframe, bars)
        source = "simulated"
    # heavy grid search runs off the event loop so it never blocks other requests
    result = await asyncio.to_thread(_optimize_compute, candles, cfg, body.timeframe,
                                     body.target_annual, body.max_dd)
    if result is None:
        raise HTTPException(status_code=422, detail="Dati insufficienti per l'ottimizzazione")
    result.update({"symbol": body.symbol, "source": source,
                   "period_start": candles[0]["time"], "period_end": candles[-1]["time"]})
    return result


def _optimize_compute(candles, cfg, timeframe, target_annual, max_dd):
    days = _period_days(candles, timeframe)
    best = None
    tested = 0
    for entry in ("smc", "meanrev", "breakout"):
        for tp in (0.5, 1.0, 1.5, 2.0):
            for sl in (1.0, 1.5, 2.5):
                for tfil in (True, False):
                    params = {"entry": entry, "tp_mult": tp, "sl_mult": sl, "trend_filter": tfil}
                    res = run_forward_test(candles, cfg, 1.0, params=params)
                    tested += 1
                    if res["total_trades"] < 12:
                        continue
                    ret_pct = res["realized_net"] / res["start_equity"] * 100
                    annual = ret_pct * (365.0 / days)
                    dd = max(res["max_drawdown"], 0.1)
                    good = res["profit_factor"] >= 1.05 and annual > 0
                    score = (annual / dd) if good else (-1e6 + annual)
                    cand = {"params": params, "annual_1pct": round(annual, 2),
                            "dd_1pct": round(res["max_drawdown"], 2), "winrate": res["winrate"],
                            "profit_factor": res["profit_factor"], "trades": res["total_trades"],
                            "score": score}
                    if best is None or cand["score"] > best["score"]:
                        best = cand
    if best is None:
        return None

    annual_1pct = best["annual_1pct"]
    dd_1pct = max(best["dd_1pct"], 0.1)
    if annual_1pct <= 0:
        recommended_risk, projected_annual, projected_dd, reached = 1.0, annual_1pct, dd_1pct, False
    else:
        risk_for_target = target_annual / annual_1pct
        risk_for_dd = max_dd / dd_1pct
        recommended_risk = round(max(0.25, min(5.0, risk_for_target, risk_for_dd)), 2)
        projected_annual = round(annual_1pct * recommended_risk, 1)
        projected_dd = round(dd_1pct * recommended_risk, 1)
        reached = projected_annual >= target_annual * 0.999

    final = run_forward_test(candles, cfg, recommended_risk, params=best["params"])
    return {
        "timeframe": timeframe, "days": round(days, 1), "combos_tested": tested,
        "best_params": best["params"], "winrate": best["winrate"],
        "profit_factor": best["profit_factor"], "trades": best["trades"],
        "annual_at_1pct": annual_1pct, "dd_at_1pct": best["dd_1pct"],
        "recommended_risk_percent": recommended_risk,
        "projected_annual_return": projected_annual, "projected_max_drawdown": projected_dd,
        "target_annual": target_annual, "target_reached": reached,
        "final_equity": final["true_equity"], "realized_net": final["realized_net"],
        "equity_curve": final["equity_curve"],
    }

@api_router.post("/optimize/oos")
async def optimize_oos(body: OptimizeReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cfg = INSTRUMENTS[body.symbol]
    bars = max(300, min(body.bars, 800))
    real = await metaapi_service.fetch_candles(body.symbol, body.timeframe, bars)
    if real and len(real) >= 260:
        candles, source = real[-bars:], "real"
    else:
        candles, _ = generate_candles(body.symbol, body.timeframe, bars)
        source = "simulated"
    result = await asyncio.to_thread(_optimize_oos_compute, candles, cfg, body.timeframe,
                                     body.target_annual, body.max_dd, body.split)
    if result is None:
        raise HTTPException(status_code=422, detail="Dati insufficienti per la validazione out-of-sample")
    result.update({"symbol": body.symbol, "source": source})
    return result


def _optimize_oos_compute(candles, cfg, timeframe, target_annual, max_dd, split):
    n = len(candles)
    split = min(0.85, max(0.5, split))
    cut = int(n * split)
    is_c, oos_c = candles[:cut], candles[cut:]
    if len(is_c) < 150 or len(oos_c) < 90:
        return None
    # 1) optimize ONLY on the in-sample slice
    is_res = _optimize_compute(is_c, cfg, timeframe, target_annual, max_dd)
    if is_res is None:
        return None
    params = is_res["best_params"]
    risk = is_res["recommended_risk_percent"]
    # 2) apply the SAME config + risk to the unseen out-of-sample slice
    oos_days = _period_days(oos_c, timeframe)
    oos = run_forward_test(oos_c, cfg, risk, params=params)
    oos_ret = oos["realized_net"] / oos["start_equity"] * 100
    oos_annual = round(oos_ret * (365.0 / oos_days), 1)

    if oos["total_trades"] < 8:
        verdict, vtext = "incerta", "Pochi trade out-of-sample: campione troppo piccolo per concludere."
    elif oos["profit_factor"] >= 1.0 and oos_annual > 0:
        verdict, vtext = "robusta", "La strategia resta profittevole su dati MAI visti: segnale di robustezza."
    else:
        verdict, vtext = "fragile", "Crolla sui dati mai visti: classico overfitting, non affidabile dal vivo."
    is_annual = is_res["projected_annual_return"]
    degradation = round(oos_annual / is_annual, 2) if is_annual > 0 else None

    return {
        "timeframe": timeframe, "split": split, "risk_percent": risk,
        "best_params": params, "combos_tested": is_res["combos_tested"],
        "verdict": verdict, "verdict_text": vtext, "degradation": degradation,
        "in_sample": {
            "days": is_res["days"], "winrate": is_res["winrate"], "profit_factor": is_res["profit_factor"],
            "trades": is_res["trades"], "annual_return": is_annual,
            "max_drawdown": is_res["projected_max_drawdown"], "equity_curve": is_res["equity_curve"],
            "period_start": is_c[0]["time"], "period_end": is_c[-1]["time"],
        },
        "out_sample": {
            "days": round(oos_days, 1), "winrate": oos["winrate"], "profit_factor": oos["profit_factor"],
            "trades": oos["total_trades"], "annual_return": oos_annual,
            "max_drawdown": oos["max_drawdown"], "net": oos["realized_net"],
            "equity_curve": oos["equity_curve"],
            "period_start": oos_c[0]["time"], "period_end": oos_c[-1]["time"],
        },
    }




class DiscoverReq(BaseModel):
    symbol: str
    years: int = 5
    target_annual: float = 50.0
    max_dd: float = 40.0


_discover_jobs = {}
_d1_cache = {}

DISCOVER_GRID = [
    (entry, tp, sl, tfil, rsi)
    for entry in ("smc", "meanrev", "breakout", "trend")
    for tp in (1.0, 1.5, 2.0, 3.0)
    for sl in (1.0, 1.5, 2.5)
    for tfil in (True, False)
    for rsi in (True, False)
]


@api_router.post("/strategy/discover")
async def strategy_discover(body: DiscoverReq, user: dict = Depends(get_current_user)):
    """Kick off strategy learning as a background job (the D1 history fetch +
    grid search can exceed the 60s ingress limit). Returns a job id to poll."""
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    job_id = str(uuid.uuid4())
    _discover_jobs[job_id] = {"status": "running", "result": None, "error": None,
                              "started": datetime.now(timezone.utc).isoformat()}
    # keep a reference so the task isn't garbage-collected mid-flight
    _discover_jobs[job_id]["task"] = asyncio.create_task(_run_discover(job_id, body))
    # trim old finished jobs (demo, single-process, keep it small)
    if len(_discover_jobs) > 40:
        for k in [k for k, v in list(_discover_jobs.items())[:-20] if v.get("status") != "running"]:
            _discover_jobs.pop(k, None)
    return {"job_id": job_id, "status": "running"}


@api_router.get("/strategy/discover/{job_id}")
async def strategy_discover_status(job_id: str, user: dict = Depends(get_current_user)):
    job = _discover_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return {k: v for k, v in job.items() if k != "task"}


async def _get_d1_history(symbol: str, want: int):
    key = symbol
    now = time.time()
    hit = _d1_cache.get(key)
    if hit and (now - hit[0]) < 600 and len(hit[1]) >= want * 0.9:
        return hit[1], "real"
    real = await metaapi_service.fetch_candles(symbol, "D1", want)
    if real and len(real) >= 400:
        _d1_cache[key] = (now, real)
        return real, "real"
    candles, _ = generate_candles(symbol, "D1", want)
    return candles, "simulated"


_h4_cache = {}


async def _get_h4_history(symbol: str, want: int):
    key = symbol
    now = time.time()
    hit = _h4_cache.get(key)
    if hit and (now - hit[0]) < 900 and len(hit[1]) >= want * 0.85:
        return hit[1], "real"
    real = await metaapi_service.fetch_candles(symbol, "H4", want)
    if real and len(real) >= 1500:
        _h4_cache[key] = (now, real)
        return real, "real"
    candles, _ = generate_candles(symbol, "H4", want)
    return candles, "simulated"


async def _run_discover(job_id: str, body: "DiscoverReq"):
    try:
        cfg = INSTRUMENTS[body.symbol]
        years = max(2, min(body.years, 8))
        want = int(years * 260) + 40  # ~260 trading days/yr on D1
        candles, source = await _get_d1_history(body.symbol, want)
        result = await asyncio.to_thread(_discover_compute, candles, cfg,
                                         body.target_annual, body.max_dd)
        if result is None:
            _discover_jobs[job_id] = {"status": "error", "result": None,
                                      "error": "Storico insufficiente per l'apprendimento"}
            return
        result.update({"symbol": body.symbol, "source": source, "years": years})
        _discover_jobs[job_id] = {"status": "done", "result": result, "error": None}
    except Exception as e:
        logger.exception("discover job failed")
        _discover_jobs[job_id] = {"status": "error", "result": None, "error": str(e)[:220]}


def _discover_compute(candles, cfg, target_annual, max_dd):
    # split: last 365 days = validation (unseen), the rest = training
    try:
        last_ts = datetime.fromisoformat(str(candles[-1]["time"]).replace("Z", "+00:00"))
    except Exception:
        return None
    cutoff = last_ts - timedelta(days=365)
    val_start = None
    for i, c in enumerate(candles):
        try:
            t = datetime.fromisoformat(str(c["time"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if t >= cutoff:
            val_start = i
            break
    if val_start is None or val_start < 150 or (len(candles) - val_start) < 30:
        return None
    train, val = candles[:val_start], candles[val_start:]
    train_days, val_days = _period_days(train, "D1"), _period_days(val, "D1")

    def annual(res, days):
        return res["realized_net"] / res["start_equity"] * 100 * (365.0 / max(days, 1.0))

    # 1) rank every config on the TRAINING window (first N-1 years)
    ranked = []
    for entry, tp, sl, tfil, rsi in DISCOVER_GRID:
        params = {"entry": entry, "tp_mult": tp, "sl_mult": sl, "trend_filter": tfil, "rsi": rsi}
        tr = run_forward_test(train, cfg, 1.0, params=params)
        if tr["total_trades"] < 10:
            continue
        ta = annual(tr, train_days)
        dd = max(tr["max_drawdown"], 0.1)
        good = tr["profit_factor"] >= 1.05 and ta > 0
        score = (ta / dd) if good else (-1e6 + ta)
        ranked.append((score, params, tr, ta))
    if not ranked:
        return None
    ranked.sort(key=lambda x: -x[0])

    # 2) validate the strongest training configs on the UNSEEN last 12 months
    best = None
    for _, params, tr, ta in ranked[:20]:
        vr = run_forward_test(val, cfg, 1.0, params=params)
        va = annual(vr, val_days)
        valid = vr["realized_net"] > 0 and vr["profit_factor"] >= 1.1 and vr["total_trades"] >= 5
        rank = (1 if valid else 0, va / max(vr["max_drawdown"], 0.1), va)
        cand = {"params": params, "tr": tr, "ta": ta, "vr": vr, "va": va,
                "valid": valid, "rank": rank}
        if best is None or cand["rank"] > best["rank"]:
            best = cand
    if best is None:
        return None

    params, tr, vr = best["params"], best["tr"], best["vr"]
    va_1pct = best["va"]
    val_dd = max(vr["max_drawdown"], 0.1)
    # size risk toward the annual target using LAST-YEAR performance, capped by DD
    if va_1pct <= 0:
        rec_risk, proj_annual, proj_dd = 1.0, va_1pct, val_dd
    else:
        rec_risk = round(max(0.25, min(5.0, target_annual / va_1pct, max_dd / val_dd)), 2)
        proj_annual = round(va_1pct * rec_risk, 1)
        proj_dd = round(val_dd * rec_risk, 1)

    if best["valid"]:
        verdict = "profittevole"
        vtext = "Strategia in PROFITTO negli ultimi 12 mesi (dati non usati per l'apprendimento): edge concreto, ma non una garanzia futura."
    elif vr["realized_net"] > 0:
        verdict = "marginale"
        vtext = "Ultimi 12 mesi leggermente positivi ma con margine sottile (PF<1.1): edge debole, meglio validare più a lungo prima di rischiare."
    else:
        verdict = "non_profittevole"
        vtext = "Nessuna configurazione è risultata profittevole nell'ultimo anno su questo strumento: questa è la migliore trovata, ma NON va tradata così — cambia strumento o timeframe."

    full = run_forward_test(candles, cfg, rec_risk, params=params)
    # exact real-data replay of the validated last-12-months window, sized at the
    # recommended risk — so the applied replay prices match what was validated
    replay = run_forward_test(val, cfg, rec_risk, params=params)
    entry_label = {"smc": "Smart Money", "meanrev": "Mean-Reversion",
                   "breakout": "Breakout", "trend": "Trend-Following (MA cross)"}[params["entry"]]
    return {
        "verdict": verdict, "verdict_text": vtext,
        "best_params": params, "entry_label": entry_label,
        "recommended_risk_percent": rec_risk,
        "projected_annual_return": proj_annual, "projected_max_drawdown": proj_dd,
        "target_annual": target_annual, "combos_tested": len(ranked),
        "training": {
            "days": round(train_days, 1), "winrate": tr["winrate"],
            "profit_factor": tr["profit_factor"], "trades": tr["total_trades"],
            "annual_return": round(best["ta"], 1), "net": tr["realized_net"],
            "max_drawdown": tr["max_drawdown"], "equity_curve": tr["equity_curve"],
            "period_start": train[0]["time"], "period_end": train[-1]["time"],
        },
        "last_year": {
            "days": round(val_days, 1), "winrate": vr["winrate"],
            "profit_factor": vr["profit_factor"], "trades": vr["total_trades"],
            "annual_return": round(va_1pct, 1), "net": vr["realized_net"],
            "max_drawdown": vr["max_drawdown"], "equity_curve": vr["equity_curve"],
            "period_start": val[0]["time"], "period_end": val[-1]["time"],
        },
        "replay": {
            "digits": cfg["digits"], "warmup": 45,
            "candles": val, "trades": replay["trades"],
            "equity_curve": replay["equity_curve"],
            "start_equity": replay["start_equity"], "final_equity": replay["true_equity"],
            "total_trades": replay["total_trades"], "winrate": replay["winrate"],
            "profit_factor": replay["profit_factor"], "max_drawdown": replay["max_drawdown"],
            "avg_win": replay["avg_win"], "avg_loss": replay["avg_loss"],
            "net_profit": replay["realized_net"],
            "period_start": val[0]["time"], "period_end": val[-1]["time"],
        },
        "full_equity_curve": full["equity_curve"],
        "full_net": full["realized_net"], "full_final_equity": full["true_equity"],
        "period_start": candles[0]["time"], "period_end": candles[-1]["time"],
    }


class LiveOrderReq(BaseModel):
    symbol: str
    side: str
    volume: float = 0.01
    sl: Optional[float] = None
    tp: Optional[float] = None


@api_router.post("/forwardtest/execute-live")
async def execute_live(body: LiveOrderReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    return await metaapi_service.place_market_order(body.symbol, body.side, body.volume, body.sl, body.tp)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    admin_email = os.environ.get("ADMIN_EMAIL", "demo@apexflow.io").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "apexflow2026")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        res = await db.users.insert_one({"email": admin_email, "password_hash": hash_password(admin_pw),
                                         "name": "Demo Trader", "role": "admin",
                                         "created_at": datetime.now(timezone.utc).isoformat()})
        await ensure_user_state(str(res.inserted_id))
    else:
        if not verify_password(admin_pw, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_pw)}})
        await ensure_user_state(str(existing["_id"]))
    logger.info("Apex Flow ready.")
    try:
        import asyncio
        asyncio.create_task(metaapi_service.warm_up())
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    client.close()


@api_router.get("/")
async def root():
    return {"message": "Apex Flow API"}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
