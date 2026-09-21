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
import uuid
import json
import math
import random
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from bson import ObjectId

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
    "EUR/USD":  {"cat": "forex",  "base": 1.0850,  "vol": 0.0009, "digits": 5},
    "GBP/USD":  {"cat": "forex",  "base": 1.2720,  "vol": 0.0011, "digits": 5},
    "XAU/USD":  {"cat": "forex",  "base": 2340.0,  "vol": 6.5,    "digits": 2},
    "BTC/USDT": {"cat": "crypto", "base": 67500.0, "vol": 480.0,  "digits": 1},
    "ETH/USDT": {"cat": "crypto", "base": 3450.0,  "vol": 34.0,   "digits": 2},
    "NVDA":     {"cat": "stocks", "base": 121.5,   "vol": 1.3,    "digits": 2},
    "AAPL":     {"cat": "stocks", "base": 214.0,   "vol": 1.6,    "digits": 2},
    "US30":     {"cat": "stocks", "base": 39250.0, "vol": 48.0,   "digits": 1},
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
    out = []
    for sym, cfg in INSTRUMENTS.items():
        candles, _ = generate_candles(sym, "M15", 40)
        last = candles[-1]["c"]
        prev = candles[-20]["c"]
        change = (last - prev) / prev * 100 if prev else 0
        out.append({"symbol": sym, "category": cfg["cat"], "price": last,
                    "change": round(change, 2), "digits": cfg["digits"]})
    return out


@api_router.get("/market/candles")
async def candles(symbol: str, timeframe: str = "M15", user: dict = Depends(get_current_user)):
    if symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cnds, cfg = generate_candles(symbol, timeframe, 110)
    zones = smart_money_zones(cnds, cfg)
    return {"symbol": symbol, "timeframe": timeframe, "digits": cfg["digits"],
            "price": cnds[-1]["c"], "candles": cnds, "zones": zones}

# ---------------------------------------------------------------------------
# AI Smart Money analysis (Claude Sonnet 4.6)
# ---------------------------------------------------------------------------
@api_router.post("/ai/analysis")
async def ai_analysis(body: AnalysisReq, user: dict = Depends(get_current_user)):
    if body.symbol not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail="Strumento non trovato")
    cnds, cfg = generate_candles(body.symbol, body.timeframe, 110)
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
