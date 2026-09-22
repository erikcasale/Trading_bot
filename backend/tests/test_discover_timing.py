import sys, os, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
import metaapi_service
import server


async def main():
    t0 = time.time()
    candles = await metaapi_service.fetch_candles("EUR/USD", "D1", 1340)
    t1 = time.time()
    print(f"fetch: {t1-t0:.1f}s, candles={len(candles) if candles else None}")
    if not candles:
        return
    print("range", candles[0]["time"][:10], "->", candles[-1]["time"][:10])
    cfg = server.INSTRUMENTS["EUR/USD"]
    t2 = time.time()
    res = server._discover_compute(candles, cfg, 50.0, 40.0)
    t3 = time.time()
    print(f"compute: {t3-t2:.1f}s")
    print("verdict", res["verdict"], "combos", res["combos_tested"])
    print("params", res["best_params"])
    print("TRAIN annual", res["training"]["annual_return"], "PF", res["training"]["profit_factor"], "trades", res["training"]["trades"])
    print("LASTYR annual", res["last_year"]["annual_return"], "PF", res["last_year"]["profit_factor"], "net", res["last_year"]["net"], "trades", res["last_year"]["trades"])
    print("rec_risk", res["recommended_risk_percent"], "proj", res["projected_annual_return"])


asyncio.run(main())
