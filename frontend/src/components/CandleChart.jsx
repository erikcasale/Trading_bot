import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Loader2 } from "lucide-react";

const TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1"];

export default function CandleChart({ symbol }) {
  const [tf, setTf] = useState("M15");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ov, setOv] = useState({ ob: true, fvg: true, liq: true });
  const prevPrice = useRef(null);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const load = () => api.get(`/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}`)
      .then((r) => {
        if (!alive) return;
        if (prevPrice.current != null) {
          if (r.data.price > prevPrice.current) setFlash("up");
          else if (r.data.price < prevPrice.current) setFlash("down");
          setTimeout(() => alive && setFlash(""), 600);
        }
        prevPrice.current = r.data.price;
        setData(r.data);
        setLoading(false);
      }).catch(() => setLoading(false));
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, [symbol, tf]);

  const geo = useMemo(() => {
    if (!data) return null;
    const c = data.candles;
    const W = c.length * 9, H = 360, pad = 8;
    const lows = c.map((x) => x.l), highs = c.map((x) => x.h);
    let min = Math.min(...lows), max = Math.max(...highs);
    if (data.zones?.liquidity) {
      min = Math.min(min, data.zones.liquidity.sell_side);
      max = Math.max(max, data.zones.liquidity.buy_side);
    }
    const range = max - min || 1;
    const y = (p) => pad + (max - p) / range * (H - pad * 2);
    const x = (i) => i * 9 + 4;
    return { c, W, H, y, x, min, max, range };
  }, [data]);

  const dig = data?.digits ?? 2;

  return (
    <div data-testid="candlestick-chart-container" className="card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-baseline gap-3">
          <h3 className="font-head text-lg font-bold">{symbol}</h3>
          <span data-testid="chart-live-price"
            className={`font-mono text-lg font-semibold px-1.5 rounded ${flash === "up" ? "flash-up text-up" : flash === "down" ? "flash-down text-down" : ""}`}>
            {data ? data.price : "—"}
          </span>
          {data?.zones && (
            <span className="text-[11px] font-mono text-[#94A3B8] hidden sm:inline">{data.zones.structure}</span>
          )}
        </div>
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
          {TIMEFRAMES.map((t) => (
            <button key={t} data-testid={`chart-tf-${t}`} onClick={() => setTf(t)}
              className={`px-2 py-1 rounded-md text-[11px] font-mono font-semibold transition-colors ${
                tf === t ? "bg-[#1A2332] text-[#0EA5E9]" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 mb-2">
        {[["ob", "Order Blocks", "#F59E0B"], ["fvg", "Fair Value Gap", "#8B5CF6"], ["liq", "Liquidità", "#0EA5E9"]].map(([k, label, col]) => (
          <button key={k} data-testid={`chart-toggle-${k}`} onClick={() => setOv((s) => ({ ...s, [k]: !s[k] }))}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium border transition-colors ${
              ov[k] ? "border-[#334155] bg-[#131A24]" : "border-[#1E293B] opacity-50"}`}>
            <span className="w-2 h-2 rounded-sm" style={{ background: col }} /> {label}
          </button>
        ))}
      </div>

      <div className="relative rounded-lg bg-[#0B0E17] border border-[#1E293B] overflow-hidden">
        {loading && !data ? (
          <div className="h-[360px] flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-[#0EA5E9]" />
          </div>
        ) : geo && (
          <div className="overflow-x-auto">
            <svg viewBox={`0 0 ${geo.W} ${geo.H}`} width="100%" height="360" preserveAspectRatio="none"
                 style={{ minWidth: "100%" }}>
              {/* grid lines */}
              {[0.25, 0.5, 0.75].map((f) => (
                <line key={f} x1="0" x2={geo.W} y1={geo.H * f} y2={geo.H * f} stroke="#1E293B" strokeWidth="0.5" strokeDasharray="3 4" />
              ))}

              {/* Order blocks */}
              {ov.ob && data.zones?.order_blocks?.map((b, i) => (
                <rect key={`ob${i}`} x={geo.x(b.i)} y={geo.y(b.type === "bullish" ? b.top : b.top)}
                  width={geo.W - geo.x(b.i)} height={Math.abs(geo.y(b.bottom) - geo.y(b.top))}
                  fill={b.type === "bullish" ? "rgba(245,158,11,0.12)" : "rgba(245,158,11,0.10)"}
                  stroke="rgba(245,158,11,0.5)" strokeWidth="0.7" strokeDasharray="2 2" />
              ))}
              {/* FVG */}
              {ov.fvg && data.zones?.fvg?.map((f, i) => (
                <rect key={`fvg${i}`} x={geo.x(f.i)} y={geo.y(f.top)}
                  width={geo.W - geo.x(f.i)} height={Math.abs(geo.y(f.bottom) - geo.y(f.top))}
                  fill="rgba(139,92,246,0.12)" stroke="rgba(139,92,246,0.45)" strokeWidth="0.7" />
              ))}
              {/* Liquidity lines */}
              {ov.liq && data.zones?.liquidity && (
                <>
                  <line x1="0" x2={geo.W} y1={geo.y(data.zones.liquidity.buy_side)} y2={geo.y(data.zones.liquidity.buy_side)}
                    stroke="#0EA5E9" strokeWidth="0.8" strokeDasharray="5 4" opacity="0.7" />
                  <line x1="0" x2={geo.W} y1={geo.y(data.zones.liquidity.sell_side)} y2={geo.y(data.zones.liquidity.sell_side)}
                    stroke="#0EA5E9" strokeWidth="0.8" strokeDasharray="5 4" opacity="0.7" />
                </>
              )}

              {/* candles */}
              {geo.c.map((k, i) => {
                const up = k.c >= k.o;
                const col = up ? "#10B981" : "#EF4444";
                const bodyTop = geo.y(Math.max(k.o, k.c));
                const bodyH = Math.max(1, Math.abs(geo.y(k.o) - geo.y(k.c)));
                return (
                  <g key={i}>
                    <line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(k.h)} y2={geo.y(k.l)} stroke={col} strokeWidth="0.8" />
                    <rect x={geo.x(i) - 3} y={bodyTop} width="6" height={bodyH} fill={col} />
                  </g>
                );
              })}

              {/* current price line */}
              <line x1="0" x2={geo.W} y1={geo.y(data.price)} y2={geo.y(data.price)}
                stroke="#F8FAFC" strokeWidth="0.5" strokeDasharray="2 3" opacity="0.4" />
            </svg>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-2 text-[10px] font-mono text-[#64748B]">
        <span>Max {data ? geo?.max?.toFixed(dig) : "—"}</span>
        <span>Order Flow Delta · RSI · Volume Profile</span>
        <span>Min {data ? geo?.min?.toFixed(dig) : "—"}</span>
      </div>
    </div>
  );
}
