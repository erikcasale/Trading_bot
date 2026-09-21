import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { LineChart, Line, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import { Play, Pause, Loader2, FastForward, Rewind, Radio, Database, TrendingUp, Percent, Activity, Layers } from "lucide-react";

const TIMEFRAMES = ["M5", "M15", "H1", "H4"];
const SPEEDS = [["1×", 1], ["3×", 3], ["6×", 6]];

export default function ForwardTest({ symbol }) {
  const [tf, setTf] = useState("M15");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3);
  const [ds, setDs] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    api.get("/datasource/status").then((r) => setDs(r.data)).catch(() => {});
  }, []);

  useEffect(() => { setRes(null); setPlaying(false); setIdx(0); }, [symbol]);

  const run = async () => {
    setLoading(true); setPlaying(false);
    try {
      const { data } = await api.post("/forwardtest/run", { symbol, timeframe: tf, bars: 320 });
      setRes(data);
      setIdx(data.warmup || 45);
      setPlaying(true);
      toast.success(`Forward-test avviato · dati ${data.source === "real" ? "REALI" : "simulati"}`);
    } catch { toast.error("Errore avvio forward-test"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!res || !playing) return;
    timer.current = setInterval(() => {
      setIdx((i) => {
        const next = i + speed;
        if (next >= res.candles.length - 1) { setPlaying(false); return res.candles.length - 1; }
        return next;
      });
    }, 120);
    return () => clearInterval(timer.current);
  }, [res, playing, speed]);

  const geo = useMemo(() => {
    if (!res) return null;
    const c = res.candles;
    const step = Math.max(4, Math.floor(1100 / c.length));
    const W = c.length * step, H = 300, pad = 10;
    let min = Math.min(...c.map((x) => x.l)), max = Math.max(...c.map((x) => x.h));
    res.trades.forEach((t) => { [t.sl, t.tp, t.entry].forEach((v) => { min = Math.min(min, v); max = Math.max(max, v); }); });
    const range = max - min || 1;
    const y = (p) => pad + (max - p) / range * (H - pad * 2);
    const x = (i) => i * step + step / 2;
    return { c, W, H, y, x, step, min, max };
  }, [res]);

  const closed = res ? res.trades.filter((t) => t.exit_index <= idx) : [];
  const openT = res ? res.trades.find((t) => t.entry_index <= idx && t.exit_index > idx) : null;
  const wins = closed.filter((t) => t.result === "win").length;
  const wr = closed.length ? Math.round(wins / closed.length * 100) : 0;
  const equity = res ? res.equity_curve[idx] : 0;
  const pnl = res ? +(equity - res.start_equity).toFixed(2) : 0;
  const eqData = res ? res.equity_curve.slice(0, idx + 1).map((e, i) => ({ i, e })) : [];
  const progress = res ? Math.round((idx / (res.candles.length - 1)) * 100) : 0;
  const dig = res?.digits ?? 2;
  const real = res?.source === "real";

  return (
    <div data-testid="forward-test-panel" className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-[#0EA5E9]" />
          <span className="font-head font-bold text-sm">Forward Test · Walk-Forward</span>
          <span className="overline hidden sm:inline">{symbol}</span>
        </div>
        <div className="flex items-center gap-2">
          <span data-testid="forwardtest-source-badge"
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-mono font-bold border ${
              real ? "border-[#10B981]/50 bg-[#10B981]/10 text-[#10B981]"
                   : "border-[#F59E0B]/50 bg-[#F59E0B]/10 text-[#F59E0B]"}`}>
            <Database className="w-3 h-3" />
            {res ? (real ? "DATI REALI TICKMILL" : "DATI SIMULATI") :
              ds?.connected ? "TICKMILL CONNESSO" : "TICKMILL: non connesso"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
          {TIMEFRAMES.map((t) => (
            <button key={t} data-testid={`forwardtest-tf-${t}`} onClick={() => setTf(t)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-mono font-semibold transition-colors ${
                tf === t ? "bg-[#1A2332] text-[#0EA5E9]" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
              {t}
            </button>
          ))}
        </div>
        <button data-testid="forwardtest-run-button" onClick={run} disabled={loading}
          className="inline-flex items-center gap-1.5 bg-[#0EA5E9] hover:bg-[#0284C7] text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          {res ? "Riavvia" : "Avvia Forward-Test"}
        </button>

        {res && (
          <>
            <button data-testid="forwardtest-playpause-button" onClick={() => setPlaying((p) => !p)}
              className="inline-flex items-center gap-1.5 bg-[#131A24] hover:bg-[#1A2332] border border-[#334155] text-[#94A3B8] text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors">
              {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              {playing ? "Pausa" : "Riprendi"}
            </button>
            <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
              <Rewind className="w-3 h-3 text-[#64748B] ml-1" />
              {SPEEDS.map(([lbl, v]) => (
                <button key={v} data-testid={`forwardtest-speed-${v}`} onClick={() => setSpeed(v)}
                  className={`px-2 py-1 rounded-md text-[11px] font-mono font-semibold transition-colors ${
                    speed === v ? "bg-[#1A2332] text-[#0EA5E9]" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
                  {lbl}
                </button>
              ))}
            </div>
            <button data-testid="forwardtest-skip-button" onClick={() => { setPlaying(false); setIdx(res.candles.length - 1); }}
              className="inline-flex items-center gap-1.5 bg-[#131A24] hover:bg-[#1A2332] border border-[#334155] text-[#94A3B8] text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors">
              <FastForward className="w-3.5 h-3.5" /> Salta alla fine
            </button>
          </>
        )}
      </div>

      {!res ? (
        <div className="h-[300px] flex flex-col items-center justify-center text-center text-[#64748B] border border-dashed border-[#1E293B] rounded-lg">
          <Radio className="w-8 h-8 mb-2 opacity-50" />
          <p className="text-xs max-w-md leading-relaxed">
            Il walk-forward "riproduce" le candele una alla volta come fosse tempo reale, applicando la logica
            Smart Money (ingresso su order block/FVG, SL sullo swing, TP verso la liquidità) e mostrando equity e
            trade live. {ds && !ds.connected && <span className="text-[#F59E0B]">Broker non ancora connesso → useremo dati simulati.</span>}
          </p>
        </div>
      ) : (
        <div className="space-y-3 fade-up">
          {/* live stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            <Stat testid="forwardtest-winrate" icon={Percent} label="Win Rate" value={`${wr}%`} color="#10B981" />
            <Stat icon={Layers} label="Trade Chiusi" value={`${closed.length}/${res.total_trades}`} color="#94A3B8" />
            <Stat icon={TrendingUp} label="PnL Corrente" value={`${pnl >= 0 ? "+" : ""}€${pnl}`} color={pnl >= 0 ? "#10B981" : "#EF4444"} />
            <Stat icon={Activity} label="Equity" value={`€${equity.toLocaleString("it-IT")}`} color="#0EA5E9" />
            <Stat icon={Activity} label="Max DD" value={`-${res.max_drawdown}%`} color="#EF4444" />
          </div>

          {/* replay chart */}
          <div className="rounded-lg bg-[#0B0E17] border border-[#1E293B] overflow-hidden">
            <div className="overflow-x-auto">
              <svg viewBox={`0 0 ${geo.W} ${geo.H}`} width="100%" height="300" preserveAspectRatio="none">
                {openT && [["#F8FAFC", openT.entry], ["#EF4444", openT.sl], ["#10B981", openT.tp]].map(([c, p], k) => (
                  <line key={k} x1="0" x2={geo.W} y1={geo.y(p)} y2={geo.y(p)} stroke={c} strokeWidth="0.8" strokeDasharray="5 4" opacity="0.85" />
                ))}
                {geo.c.slice(0, idx + 1).map((k, i) => {
                  const up = k.c >= k.o;
                  const col = up ? "#10B981" : "#EF4444";
                  const bt = geo.y(Math.max(k.o, k.c));
                  const bh = Math.max(1, Math.abs(geo.y(k.o) - geo.y(k.c)));
                  return (
                    <g key={i}>
                      <line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(k.h)} y2={geo.y(k.l)} stroke={col} strokeWidth="0.7" />
                      <rect x={geo.x(i) - geo.step / 2 + 0.5} y={bt} width={Math.max(1.5, geo.step - 1)} height={bh} fill={col} />
                    </g>
                  );
                })}
                {/* entry/exit markers for revealed trades */}
                {res.trades.filter((t) => t.entry_index <= idx).map((t, k) => (
                  <g key={`m${k}`}>
                    <circle cx={geo.x(t.entry_index)} cy={geo.y(t.entry)} r="3"
                      fill={t.side === "BUY" ? "#0EA5E9" : "#F59E0B"} stroke="#0B0E17" strokeWidth="1" />
                    {t.exit_index <= idx && (
                      <circle cx={geo.x(t.exit_index)} cy={geo.y(t.exit)} r="3"
                        fill={t.result === "win" ? "#10B981" : "#EF4444"} stroke="#0B0E17" strokeWidth="1" />
                    )}
                  </g>
                ))}
              </svg>
            </div>
            {/* progress bar */}
            <div className="h-1 bg-[#131A24]">
              <div className="h-full bg-[#0EA5E9] transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>

          {/* equity + log */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div data-testid="forwardtest-equity-chart" className="lg:col-span-2 rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2">
              <div className="overline mb-1 px-1">Equity Curve (live)</div>
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={eqData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <YAxis domain={["dataMin", "dataMax"]} tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false}
                    width={52} tickFormatter={(v) => `€${(v / 1000).toFixed(1)}k`} />
                  <Tooltip contentStyle={{ background: "#131A24", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ display: "none" }} formatter={(v) => [`€${v.toLocaleString("it-IT")}`, "Equity"]} />
                  <Line type="monotone" dataKey="e" stroke={pnl >= 0 ? "#10B981" : "#EF4444"} strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2">
              <div className="overline mb-1 px-1">Trade Log</div>
              <div className="space-y-1 max-h-[120px] overflow-y-auto pr-1">
                {closed.length === 0 && <div className="text-[11px] text-[#64748B] px-1 py-2">Nessun trade chiuso ancora...</div>}
                {closed.slice().reverse().map((t, k) => (
                  <div key={k} className="flex items-center justify-between text-[11px] font-mono px-2 py-1 rounded bg-[#131A24]">
                    <span className={t.side === "BUY" ? "text-up" : "text-down"}>{t.side}</span>
                    <span className={`px-1 rounded text-[10px] font-bold ${t.result === "win" ? "text-up" : "text-down"}`}>
                      {t.result === "win" ? "WIN" : "LOSS"}</span>
                    <span className={t.pnl >= 0 ? "text-up" : "text-down"}>{t.pnl >= 0 ? "+" : ""}€{t.pnl}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <p className="text-[10px] text-[#64748B] leading-relaxed">
            {real ? "Dati storici reali dal broker Tickmill via MetaApi." :
              "⚠️ Dati SIMULATI (MetaApi non ancora connesso al broker). Appena l'account risulterà CONNECTED, il forward-test userà automaticamente i dati reali Tickmill."}
            {" "}Risultati a scopo educativo: le performance passate non garantiscono risultati futuri.
          </p>
        </div>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, color, testid }) {
  return (
    <div data-testid={testid} className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2.5">
      <div className="flex items-center gap-1 mb-1"><Icon className="w-3 h-3" style={{ color }} />
        <span className="overline">{label}</span></div>
      <div className="font-mono text-base font-bold" style={{ color }}>{value}</div>
    </div>
  );
}
