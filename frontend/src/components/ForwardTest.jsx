import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { LineChart, Line, YAxis, ResponsiveContainer, Tooltip } from "recharts";
import { Play, Pause, Loader2, FastForward, Rewind, Radio, Database, TrendingUp, Percent, Activity, Layers, CalendarRange, AlertTriangle, Target, Brain, CheckCircle2, XCircle } from "lucide-react";

const PERIODS = [
  ["Settimana", "M15", 480],
  ["Mese", "H1", 500],
  ["Trimestre", "H4", 540],
  ["Anno", "D1", 365],
];
const SPEEDS = [["1×", 1], ["3×", 3], ["6×", 6]];

const fmtDate = (iso, withTime = true) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso).slice(0, 16);
  const p = (n) => String(n).padStart(2, "0");
  const base = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return withTime ? `${base} ${p(d.getHours())}:${p(d.getMinutes())}` : base;
};

export default function ForwardTest({ symbol }) {
  const [period, setPeriod] = useState("Trimestre");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3);
  const [ds, setDs] = useState(null);
  const [opt, setOpt] = useState(null);
  const [optLoading, setOptLoading] = useState(false);
  const [oos, setOos] = useState(null);
  const [oosLoading, setOosLoading] = useState(false);
  const [disc, setDisc] = useState(null);
  const [discLoading, setDiscLoading] = useState(false);
  const discPoll = useRef(null);
  const timer = useRef(null);

  useEffect(() => { api.get("/datasource/status").then((r) => setDs(r.data)).catch(() => {}); }, []);
  useEffect(() => {
    setRes(null); setPlaying(false); setIdx(0); setOpt(null); setOos(null); setDisc(null);
    if (discPoll.current) clearInterval(discPoll.current);
  }, [symbol]);
  useEffect(() => () => { if (discPoll.current) clearInterval(discPoll.current); }, []);

  const runDiscover = async () => {
    setDiscLoading(true); setDisc(null);
    if (discPoll.current) clearInterval(discPoll.current);
    try {
      const { data } = await api.post("/strategy/discover", { symbol, years: 5, target_annual: 50 });
      const jobId = data.job_id;
      let ticks = 0;
      discPoll.current = setInterval(async () => {
        ticks += 1;
        try {
          const { data: st } = await api.get(`/strategy/discover/${jobId}`);
          if (st.status === "done") {
            clearInterval(discPoll.current); setDisc(st.result); setDiscLoading(false);
            const v = st.result.verdict;
            toast[v === "profittevole" ? "success" : v === "marginale" ? "message" : "error"](
              `Strategia: ${v.toUpperCase()} nell'ultimo anno`);
          } else if (st.status === "error" || ticks > 60) {
            clearInterval(discPoll.current); setDiscLoading(false);
            toast.error(st.error || "Apprendimento non riuscito");
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch { setDiscLoading(false); toast.error("Impossibile avviare l'apprendimento"); }
  };

  const applyDiscovered = async () => {
    if (!disc || !disc.replay) return;
    setPlaying(false); setPeriod("Anno");
    // replay the EXACT real-data last-12-months window used in validation
    const r = disc.replay;
    setRes({
      symbol, timeframe: "D1", source: disc.source, mode: "optimized",
      digits: r.digits, warmup: r.warmup, candles: r.candles, trades: r.trades,
      equity_curve: r.equity_curve, start_equity: r.start_equity,
      total_trades: r.total_trades, winrate: r.winrate, profit_factor: r.profit_factor,
      max_drawdown: r.max_drawdown, avg_win: r.avg_win, avg_loss: r.avg_loss,
      net_profit: r.net_profit, period_start: r.period_start, period_end: r.period_end,
    });
    setIdx(r.warmup || 45); setPlaying(true);
    toast.success(`Replay ultimo anno · dati ${disc.source === "real" ? "REALI Tickmill" : "SIMULATI"}`);
  };

  const run = async () => {
    setLoading(true); setPlaying(false);
    const [, tf, bars] = PERIODS.find((p) => p[0] === period);
    try {
      const { data } = await api.post("/forwardtest/run", { symbol, timeframe: tf, bars, mode: "balanced" });
      setRes(data);
      setIdx(data.warmup || 45);
      setPlaying(true);
      toast.success(`Forward-test ${period} · dati ${data.source === "real" ? "REALI" : "simulati"}`);
    } catch { toast.error("Errore avvio forward-test"); }
    finally { setLoading(false); }
  };

  const runOptimize = async () => {
    setOptLoading(true); setOpt(null);
    const [, tf, bars] = PERIODS.find((p) => p[0] === period);
    try {
      const { data } = await api.post("/optimize", { symbol, timeframe: tf, bars: Math.max(400, bars), target_annual: 50 });
      setOpt(data);
      toast.success(`Ottimizzazione completata · ${data.combos_tested} config testate`);
    } catch { toast.error("Ottimizzazione non riuscita (dati insufficienti)"); }
    finally { setOptLoading(false); }
  };

  const applyOptimized = async () => {
    if (!opt) return;
    setLoading(true); setPlaying(false);
    const [, tf, bars] = PERIODS.find((p) => p[0] === period);
    try {
      const { data } = await api.post("/forwardtest/run", { symbol, timeframe: tf, bars, params: opt.best_params, risk_percent: opt.recommended_risk_percent });
      setRes(data); setIdx(data.warmup || 45); setPlaying(true);
      toast.success("Config ottimizzata applicata al forward-test");
    } catch { toast.error("Errore"); }
    finally { setLoading(false); }
  };

  const runOos = async () => {
    setOosLoading(true); setOos(null);
    const [, tf] = PERIODS.find((p) => p[0] === period);
    try {
      const { data } = await api.post("/optimize/oos", { symbol, timeframe: tf, bars: 800, split: 0.7, target_annual: 50 });
      setOos(data);
      toast[data.verdict === "robusta" ? "success" : data.verdict === "fragile" ? "error" : "message"](
        `Validazione OOS: strategia ${data.verdict.toUpperCase()}`);
    } catch { toast.error("Validazione OOS non riuscita (dati insufficienti)"); }
    finally { setOosLoading(false); }
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
    const step = Math.max(3, Math.floor(1100 / c.length));
    const W = c.length * step, H = 300, pad = 10;
    let min = Math.min(...c.map((x) => x.l)), max = Math.max(...c.map((x) => x.h));
    res.trades.forEach((t) => { [t.sl, t.tp, t.entry].forEach((v) => { min = Math.min(min, v); max = Math.max(max, v); }); });
    const range = max - min || 1;
    const y = (p) => pad + (max - p) / range * (H - pad * 2);
    const x = (i) => i * step + step / 2;
    return { c, W, H, y, x, step, min, max };
  }, [res]);

  const clampIdx = res ? Math.min(idx, res.candles.length - 1) : 0;
  const closed = res ? res.trades.filter((t) => t.exit_index <= clampIdx && t.result !== "open") : [];
  const openT = res ? res.trades.find((t) => t.entry_index <= clampIdx && t.exit_index > clampIdx) : null;
  const wins = closed.filter((t) => t.result === "win").length;
  const wr = closed.length ? Math.round(wins / closed.length * 100) : 0;
  const equity = res ? (res.equity_curve[clampIdx] ?? res.start_equity) : 0;
  const pnl = res ? +(equity - res.start_equity).toFixed(2) : 0;
  const eqData = res ? res.equity_curve.slice(0, clampIdx + 1).map((e, i) => ({ i, e })) : [];
  const progress = res ? Math.round((clampIdx / (res.candles.length - 1)) * 100) : 0;
  const dig = res?.digits ?? 2;
  const real = res?.source === "real";
  const profitable = res ? res.profit_factor >= 1 : false;

  return (
    <div data-testid="forward-test-panel" className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-[#0EA5E9]" />
          <span className="font-head font-bold text-sm">Forward Test · Walk-Forward</span>
          <span className="overline hidden sm:inline">{symbol}</span>
        </div>
        <span data-testid="forwardtest-source-badge"
          className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-mono font-bold border ${
            real ? "border-[#10B981]/50 bg-[#10B981]/10 text-[#10B981]"
                 : "border-[#F59E0B]/50 bg-[#F59E0B]/10 text-[#F59E0B]"}`}>
          <Database className="w-3 h-3" />
          {res ? (real ? "DATI REALI TICKMILL" : "DATI SIMULATI") :
            ds?.connected ? "TICKMILL CONNESSO" : "TICKMILL: non connesso"}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {/* periodo */}
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
          {PERIODS.map(([label]) => (
            <button key={label} data-testid={`forwardtest-period-${label}`} onClick={() => setPeriod(label)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors ${
                period === label ? "bg-[#1A2332] text-[#0EA5E9]" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
              {label}
            </button>
          ))}
        </div>
        {/* modalità */}
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-[#10B981]/10 border border-[#10B981]/30 text-[10px] font-mono font-bold text-[#10B981]">
          <Database className="w-3 h-3" /> COSTI REALI INCLUSI
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

      {/* Strategy discovery — learn on 5y, validate on last 12 months */}
      <div data-testid="discover-panel" className="mb-3 rounded-lg border border-[#0EA5E9]/40 bg-[#0EA5E9]/5 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-[#0EA5E9]" />
            <span className="font-head font-bold text-sm">Apprendi Strategia · 5 anni</span>
            <span className="overline">D1 · valida sull'ULTIMO ANNO · {symbol}</span>
          </div>
          <button data-testid="discover-run-button" onClick={runDiscover} disabled={discLoading}
            className="inline-flex items-center gap-1.5 bg-[#0EA5E9] hover:bg-[#0284C7] text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
            {discLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Brain className="w-3.5 h-3.5" />}
            {discLoading ? "Apprendimento in corso…" : "Analizza 5 anni & trova strategia"}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-[#94A3B8] leading-relaxed">
          Analizza <b className="text-white">~5 anni</b> di grafico giornaliero Tickmill, cerca la logica migliore
          (Smart Money, Mean-Reversion, Breakout, Trend-Following + filtro RSI) sui primi 4 anni, poi la <b className="text-white">verifica sugli ultimi 12 mesi mai visti</b>.
          Una strategia è valida solo se resta <b className="text-[#10B981]">in profitto nell'ultimo anno</b>.
          {discLoading && <span className="text-[#0EA5E9]"> Può richiedere fino a ~40s (scarico storico + ricerca).</span>}
        </p>

        {disc && (
          <div data-testid="discover-result" className="mt-3 space-y-2 fade-up">
            {disc.source !== "real" && (
              <div data-testid="discover-simulated-warning" className="flex items-start gap-2 text-[11px] text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/40 rounded-lg p-2.5 leading-relaxed">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span><b>Attenzione: dati SIMULATI.</b> Il broker Tickmill non era raggiungibile durante l'analisi, quindi i prezzi qui sotto NON sono reali e non combaciano con MT5. Riprova tra poco: appena la connessione è pronta i dati diventano reali.</span>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <span data-testid="discover-verdict-badge"
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-bold border ${
                  disc.verdict === "profittevole" ? "border-[#10B981]/50 bg-[#10B981]/10 text-[#10B981]"
                  : disc.verdict === "marginale" ? "border-[#F59E0B]/50 bg-[#F59E0B]/10 text-[#F59E0B]"
                  : "border-[#EF4444]/50 bg-[#EF4444]/10 text-[#EF4444]"}`}>
                {disc.verdict === "profittevole" ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {disc.verdict === "profittevole" ? "PROFITTEVOLE (ultimo anno)"
                  : disc.verdict === "marginale" ? "MARGINALE" : "NESSUN EDGE (ultimo anno)"}
              </span>
              <span className="text-[11px] font-mono text-[#94A3B8]">
                {fmtDate(disc.period_start, false)} → {fmtDate(disc.period_end, false)} · {disc.combos_tested} config testate ({disc.source === "real" ? "dati reali" : "simulati"})
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-[#94A3B8]">
              <span>Strategia: <b className="text-white">{disc.entry_label}</b></span>
              <span>TP <b className="text-[#10B981]">{disc.best_params.tp_mult}·ATR</b></span>
              <span>SL <b className="text-[#EF4444]">{disc.best_params.sl_mult}·ATR</b></span>
              <span>Trend: <b className="text-white">{disc.best_params.trend_filter ? "ON" : "OFF"}</b></span>
              <span>RSI: <b className="text-white">{disc.best_params.rsi ? "ON" : "OFF"}</b></span>
              <span>Rischio/trade: <b className="text-[#F59E0B]">{disc.recommended_risk_percent}%</b></span>
              <span>Proiezione annua: <b className={disc.projected_annual_return >= 0 ? "text-up" : "text-down"}>{disc.projected_annual_return >= 0 ? "+" : ""}{disc.projected_annual_return}%</b></span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {[["Apprendimento (primi 4 anni)", disc.training, "#0EA5E9"],
                ["Ultimo anno (mai visto)", disc.last_year, disc.last_year.net > 0 ? "#10B981" : "#EF4444"]].map(([label, seg, col], k) => (
                <div key={k} data-testid={`discover-seg-${k}`} className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="overline" style={{ color: col }}>{label}</span>
                    <span className="text-[10px] font-mono text-[#64748B]">{fmtDate(seg.period_start, false)} → {fmtDate(seg.period_end, false)}</span>
                  </div>
                  <div className="grid grid-cols-5 gap-1 font-mono text-[11px] mb-1">
                    <Mini label="WR" value={`${seg.winrate}%`} />
                    <Mini label="PF" value={seg.profit_factor} color={seg.profit_factor >= 1 ? "#10B981" : "#EF4444"} />
                    <Mini label="Annua" value={`${seg.annual_return}%`} color={seg.annual_return >= 0 ? "#10B981" : "#EF4444"} />
                    <Mini label="Net" value={`€${seg.net}`} color={seg.net >= 0 ? "#10B981" : "#EF4444"} />
                    <Mini label="Trade" value={seg.trades} />
                  </div>
                  <ResponsiveContainer width="100%" height={70}>
                    <LineChart data={seg.equity_curve.map((e, i) => ({ i, e }))}>
                      <YAxis domain={["dataMin", "dataMax"]} hide />
                      <Line type="monotone" dataKey="e" stroke={col} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>

            <div className={`flex items-start gap-2 text-[11px] rounded-lg p-2.5 leading-relaxed border ${
              disc.verdict === "profittevole" ? "text-[#10B981] bg-[#10B981]/5 border-[#10B981]/30"
              : disc.verdict === "marginale" ? "text-[#F59E0B] bg-[#F59E0B]/5 border-[#F59E0B]/30"
              : "text-[#EF4444] bg-[#EF4444]/8 border-[#EF4444]/40"}`}>
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{disc.verdict_text} La logica è stata scelta SOLO sui primi 4 anni e verificata, senza modifiche, sull'ultimo anno. Le performance passate non garantiscono risultati futuri.</span>
            </div>

            {disc.verdict !== "non_profittevole" && (
              <button data-testid="discover-apply-button" onClick={applyDiscovered} disabled={loading}
                className="inline-flex items-center gap-1.5 bg-[#10B981] hover:bg-[#059669] text-[#05130D] text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
                {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                Applica e riproduci l'ultimo anno
              </button>
            )}
          </div>
        )}
      </div>

      {/* Optimizer — target +50% annual */}
      <div className="mb-3 rounded-lg border border-[#8B5CF6]/30 bg-[#8B5CF6]/5 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-[#8B5CF6]" />
            <span className="font-head font-bold text-sm">Ottimizzatore Rendita</span>
            <span className="overline">obiettivo +50% annuo · {symbol}</span>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="optimizer-run-button" onClick={runOptimize} disabled={optLoading}
              className="inline-flex items-center gap-1.5 bg-[#8B5CF6] hover:bg-[#7C3AED] text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
              {optLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Target className="w-3.5 h-3.5" />}
              Trova la migliore config
            </button>
            <button data-testid="optimizer-oos-button" onClick={runOos} disabled={oosLoading}
              className="inline-flex items-center gap-1.5 bg-[#131A24] hover:bg-[#1A2332] border border-[#8B5CF6]/50 text-[#8B5CF6] text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
              {oosLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CalendarRange className="w-3.5 h-3.5" />}
              Validazione Out-of-Sample
            </button>
          </div>
        </div>

        {opt && (
          <div className="mt-3 space-y-2 fade-up">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
              <Stat icon={TrendingUp} testid="optimizer-projected-annual" label="Rendita Annua Proiettata"
                value={`${opt.projected_annual_return >= 0 ? "+" : ""}${opt.projected_annual_return}%`}
                color={opt.projected_annual_return >= 0 ? "#10B981" : "#EF4444"} />
              <Stat icon={Activity} label="Max DD Proiettato" value={`-${opt.projected_max_drawdown}%`} color="#EF4444" />
              <Stat icon={Percent} label="Win Rate" value={`${opt.winrate}%`} color="#10B981" />
              <Stat icon={Activity} label="Profit Factor" value={opt.profit_factor} color="#0EA5E9" />
              <Stat icon={Layers} label="Operazioni" value={opt.trades} color="#94A3B8" />
              <Stat icon={Target} label="Rischio/Trade" value={`${opt.recommended_risk_percent}%`} color="#F59E0B" />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-[#94A3B8]">
              <span>Config: <b className="text-white">{{ smc: "Smart Money", meanrev: "Mean-Reversion", breakout: "Breakout" }[opt.best_params.entry]}</b></span>
              <span>TP <b className="text-[#10B981]">{opt.best_params.tp_mult}·ATR</b></span>
              <span>SL <b className="text-[#EF4444]">{opt.best_params.sl_mult}·ATR</b></span>
              <span>Filtro trend: <b className="text-white">{opt.best_params.trend_filter ? "ON" : "OFF"}</b></span>
              <span className="text-[#64748B]">· {opt.combos_tested} config testate su {opt.days}g ({opt.source === "real" ? "dati reali" : "simulati"})</span>
            </div>
            <div className="flex items-start gap-2 text-[11px] text-[#F59E0B] bg-[#F59E0B]/5 border border-[#F59E0B]/30 rounded-lg p-2.5 leading-relaxed">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Questa è la config che <b>storicamente</b> avrebbe reso di più su ~{opt.days} giorni, dimensionando il rischio
                al {opt.recommended_risk_percent}% per trade. La rendita annua è una <b>proiezione</b> ottenuta annualizzando un
                periodo breve: c'è forte rischio di <b>overfitting</b> (ottimo sul passato, non garantito sul futuro). Nessun sistema
                garantisce +50% annuo. Usalo come studio, non come promessa.
              </span>
            </div>
            <button data-testid="optimizer-apply-button" onClick={applyOptimized} disabled={loading}
              className="inline-flex items-center gap-1.5 bg-[#10B981] hover:bg-[#059669] text-[#05130D] text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
              {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Applica e riproduci nel forward-test
            </button>
          </div>
        )}

        {oos && (
          <div data-testid="oos-result" className="mt-3 pt-3 border-t border-[#8B5CF6]/20 space-y-2 fade-up">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-head font-bold text-sm">Validazione Walk-Forward</span>
              <span data-testid="oos-verdict-badge"
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-bold border ${
                  oos.verdict === "robusta" ? "border-[#10B981]/50 bg-[#10B981]/10 text-[#10B981]"
                  : oos.verdict === "fragile" ? "border-[#EF4444]/50 bg-[#EF4444]/10 text-[#EF4444]"
                  : "border-[#F59E0B]/50 bg-[#F59E0B]/10 text-[#F59E0B]"}`}>
                {oos.verdict === "robusta" ? "ROBUSTA" : oos.verdict === "fragile" ? "FRAGILE (overfitting)" : "INCERTA"}
              </span>
              {oos.degradation != null && (
                <span className="text-[11px] font-mono text-[#94A3B8]">rendita OOS/IS: <b className={oos.degradation >= 0.5 ? "text-up" : "text-down"}>{oos.degradation}×</b></span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {[["In-Sample (studio)", oos.in_sample, "#0EA5E9"], ["Out-of-Sample (mai visto)", oos.out_sample, oos.verdict === "fragile" ? "#EF4444" : "#10B981"]].map(([label, seg, col], k) => (
                <div key={k} className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="overline" style={{ color: col }}>{label}</span>
                    <span className="text-[10px] font-mono text-[#64748B]">{fmtDate(seg.period_start, false)} → {fmtDate(seg.period_end, false)}</span>
                  </div>
                  <div className="grid grid-cols-5 gap-1 font-mono text-[11px] mb-1">
                    <Mini label="WR" value={`${seg.winrate}%`} />
                    <Mini label="PF" value={seg.profit_factor} color={seg.profit_factor >= 1 ? "#10B981" : "#EF4444"} />
                    <Mini label="Annua" value={`${seg.annual_return}%`} color={seg.annual_return >= 0 ? "#10B981" : "#EF4444"} />
                    <Mini label="DD" value={`-${seg.max_drawdown}%`} color="#EF4444" />
                    <Mini label="Trade" value={seg.trades} />
                  </div>
                  <ResponsiveContainer width="100%" height={70}>
                    <LineChart data={seg.equity_curve.map((e, i) => ({ i, e }))}>
                      <YAxis domain={["dataMin", "dataMax"]} hide />
                      <Line type="monotone" dataKey="e" stroke={col} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>

            <div className={`flex items-start gap-2 text-[11px] rounded-lg p-2.5 leading-relaxed border ${
              oos.verdict === "robusta" ? "text-[#10B981] bg-[#10B981]/5 border-[#10B981]/30"
              : oos.verdict === "fragile" ? "text-[#EF4444] bg-[#EF4444]/8 border-[#EF4444]/40"
              : "text-[#F59E0B] bg-[#F59E0B]/5 border-[#F59E0B]/30"}`}>
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                {oos.verdict_text} La config è stata scelta SOLO sul periodo di studio ({oos.in_sample.days}g) e poi applicata,
                <b> senza modifiche</b>, al periodo mai visto ({oos.out_sample.days}g). Se i due risultati divergono molto, è
                overfitting: bello sul passato, inaffidabile sul futuro. È così che si smaschera il mito del "98% winrate".
              </span>
            </div>
          </div>
        )}
      </div>

      {!res ? (
        <div className="h-[280px] flex flex-col items-center justify-center text-center text-[#64748B] border border-dashed border-[#1E293B] rounded-lg">
          <Radio className="w-8 h-8 mb-2 opacity-50" />
          <p className="text-xs max-w-md leading-relaxed">
            Riproduce le candele una alla volta come fosse tempo reale, applicando la strategia Smart Money con
            <b className="text-[#94A3B8]"> costi reali inclusi</b>. Scegli il <b className="text-[#94A3B8]">periodo</b> (fino a
            "Anno" su candele giornaliere), poi avvia: vedrai equity, trade con date e statistiche live al netto dei costi.
            {" "}{ds && !ds.connected && <span className="text-[#F59E0B]">Broker non connesso → dati simulati.</span>}
          </p>
        </div>
      ) : (
        <div className="space-y-3 fade-up">
          {/* date range */}
          <div className="flex items-center gap-2 text-[11px] font-mono text-[#94A3B8]">
            <CalendarRange className="w-3.5 h-3.5 text-[#0EA5E9]" />
            Periodo testato: <b className="text-white">{fmtDate(res.period_start, false)}</b> → <b className="text-white">{fmtDate(res.period_end, false)}</b>
            <span className="text-[#64748B]">· {res.candles.length} candele {res.timeframe}</span>
          </div>

          {/* live stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            <Stat testid="forwardtest-winrate" icon={Percent} label="Win Rate" value={`${wr}%`} color="#10B981" />
            <Stat icon={Layers} label="Trade" value={`${closed.length}/${res.total_trades}`} color="#94A3B8" />
            <Stat icon={TrendingUp} label="PnL" value={`${pnl >= 0 ? "+" : ""}€${pnl}`} color={pnl >= 0 ? "#10B981" : "#EF4444"} />
            <Stat icon={Activity} label="Profit Factor" value={res.profit_factor} color={profitable ? "#10B981" : "#EF4444"} />
            <Stat icon={Activity} label="Max DD" value={`-${res.max_drawdown}%`} color="#EF4444" />
            <Stat icon={TrendingUp} label="Media W/L" value={`${res.avg_win}/${res.avg_loss}`} color="#F59E0B" />
          </div>

          {/* costs-included note */}
          <div className="flex items-start gap-2 text-[11px] text-[#94A3B8] bg-[#0B0E17] border border-[#1E293B] rounded-lg p-2.5 leading-relaxed">
            <Database className="w-4 h-4 shrink-0 mt-0.5 text-[#10B981]" />
            <span>
              Ogni operazione include i <b className="text-white">costi reali</b> (spread + commissione + slippage stimati per {symbol}):
              i numeri qui sono al netto dei costi, quindi credibili. Un Profit Factor
              <b className={profitable ? " text-[#10B981]" : " text-[#EF4444]"}> {res.profit_factor}</b> {profitable
                ? "sopra 1 significa che il sistema supera i costi su questo periodo."
                : "sotto 1 significa che dopo i costi questo periodo è in perdita: è la realtà da cui partire."}
            </span>
          </div>

          {/* replay chart */}
          <div className="rounded-lg bg-[#0B0E17] border border-[#1E293B] overflow-hidden">
            <div className="overflow-x-auto">
              <svg viewBox={`0 0 ${geo.W} ${geo.H}`} width="100%" height="300" preserveAspectRatio="none">
                {openT && [["#F8FAFC", openT.entry], ["#EF4444", openT.sl], ["#10B981", openT.tp]].map(([c, p], k) => (
                  <line key={k} x1="0" x2={geo.W} y1={geo.y(p)} y2={geo.y(p)} stroke={c} strokeWidth="0.8" strokeDasharray="5 4" opacity="0.85" />
                ))}
                {geo.c.slice(0, clampIdx + 1).map((k, i) => {
                  const up = k.c >= k.o;
                  const col = up ? "#10B981" : "#EF4444";
                  const bt = geo.y(Math.max(k.o, k.c));
                  const bh = Math.max(1, Math.abs(geo.y(k.o) - geo.y(k.c)));
                  return (
                    <g key={i}>
                      <line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(k.h)} y2={geo.y(k.l)} stroke={col} strokeWidth="0.7" />
                      <rect x={geo.x(i) - geo.step / 2 + 0.4} y={bt} width={Math.max(1.2, geo.step - 0.8)} height={bh} fill={col} />
                    </g>
                  );
                })}
                {res.trades.filter((t) => t.entry_index <= clampIdx).map((t, k) => (
                  <g key={`m${k}`}>
                    <circle cx={geo.x(t.entry_index)} cy={geo.y(t.entry)} r="2.6"
                      fill={t.side === "BUY" ? "#0EA5E9" : "#F59E0B"} stroke="#0B0E17" strokeWidth="1" />
                    {t.exit_index <= clampIdx && (
                      <circle cx={geo.x(t.exit_index)} cy={geo.y(t.exit)} r="2.6"
                        fill={t.result === "win" ? "#10B981" : "#EF4444"} stroke="#0B0E17" strokeWidth="1" />
                    )}
                  </g>
                ))}
              </svg>
            </div>
            <div className="h-1 bg-[#131A24]">
              <div className="h-full bg-[#0EA5E9] transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>

          {/* equity */}
          <div data-testid="forwardtest-equity-chart" className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2">
            <div className="overline mb-1 px-1">Equity Curve (live)</div>
            <ResponsiveContainer width="100%" height={130}>
              <LineChart data={eqData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <YAxis domain={["dataMin", "dataMax"]} tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false}
                  width={56} tickFormatter={(v) => `€${(v / 1000).toFixed(2)}k`} />
                <Tooltip contentStyle={{ background: "#131A24", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ display: "none" }} formatter={(v) => [`€${v.toLocaleString("it-IT")}`, "Equity"]} />
                <Line type="monotone" dataKey="e" stroke={pnl >= 0 ? "#10B981" : "#EF4444"} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* full trades table for manual verification */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="overline">Registro Operazioni · verifica manuale ({res.trades.length})</span>
              <span className="text-[10px] font-mono text-[#64748B]">orari = ora server broker (MT5)</span>
            </div>
            {(res.timeframe === "D1" || res.timeframe === "D") && (
              <div data-testid="forwardtest-d1-note" className="flex items-start gap-1.5 text-[10px] text-[#64748B] mb-1.5 leading-relaxed">
                <Activity className="w-3 h-3 shrink-0 mt-0.5" />
                <span>Timeframe <b className="text-[#94A3B8]">giornaliero (D1)</b>: l'<b className="text-[#94A3B8]">entrata è alla chiusura</b> della candela (prezzo esatto). SL/TP vengono toccati <b className="text-[#94A3B8]">in un momento qualsiasi della giornata</b>: mostriamo solo la <b className="text-[#94A3B8]">data</b>, l'orario intraday non è determinabile su D1.</span>
              </div>
            )}
            <div className="rounded-lg border border-[#1E293B] bg-[#0B0E17] overflow-x-auto">
              <table data-testid="forwardtest-trades-table" className="w-full text-left">
                <thead>
                  <tr className="overline border-b border-[#1E293B]">
                    <th className="py-2 px-2 font-normal">#</th>
                    <th className="py-2 px-2 font-normal">Lato</th>
                    <th className="py-2 px-2 font-normal">Entrata</th>
                    <th className="py-2 px-2 font-normal text-right">Prezzo In</th>
                    <th className="py-2 px-2 font-normal">Uscita</th>
                    <th className="py-2 px-2 font-normal text-right">Prezzo Out</th>
                    <th className="py-2 px-2 font-normal text-right hidden sm:table-cell">SL</th>
                    <th className="py-2 px-2 font-normal text-right hidden sm:table-cell">TP</th>
                    <th className="py-2 px-2 font-normal text-center">Esito</th>
                    <th className="py-2 px-2 font-normal text-right">PnL</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[11px]">
                  {res.trades.map((t, i) => (
                    <tr key={i} className={`border-b border-[#1E293B]/50 hover:bg-[#131A24] ${t.exit_index <= clampIdx ? "" : "opacity-40"}`}>
                      <td className="py-1.5 px-2 text-[#64748B]">{i + 1}</td>
                      <td className={`py-1.5 px-2 font-bold ${t.side === "BUY" ? "text-up" : "text-down"}`}>{t.side}</td>
                      <td className="py-1.5 px-2 text-[#94A3B8]">
                        {fmtDate(t.entry_time, !(res.timeframe === "D1" || res.timeframe === "D"))}
                        {(res.timeframe === "D1" || res.timeframe === "D") && <span className="text-[#475569]"> ·chiusura</span>}
                      </td>
                      <td className="py-1.5 px-2 text-right">{t.entry}</td>
                      <td className="py-1.5 px-2 text-[#94A3B8]">
                        {t.result === "open" ? "—" : fmtDate(t.exit_time, !(res.timeframe === "D1" || res.timeframe === "D"))}
                        {t.intrabar && (res.timeframe === "D1" || res.timeframe === "D") && <span className="text-[#475569]"> ·intraday</span>}
                      </td>
                      <td className="py-1.5 px-2 text-right">{t.exit}</td>
                      <td className="py-1.5 px-2 text-right text-down hidden sm:table-cell">{t.sl}</td>
                      <td className="py-1.5 px-2 text-right text-up hidden sm:table-cell">{t.tp}</td>
                      <td className="py-1.5 px-2 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          t.result === "win" ? "bg-[#10B981]/10 text-up"
                          : t.result === "open" ? "bg-[#F59E0B]/10 text-[#F59E0B]"
                          : "bg-[#EF4444]/10 text-down"}`}>
                          {t.result === "win" ? "WIN" : t.result === "open" ? "APERTO" : "LOSS"}</span>
                      </td>
                      <td className={`py-1.5 px-2 text-right font-semibold ${t.pnl >= 0 ? "text-up" : "text-down"}`}>
                        {t.pnl >= 0 ? "+" : ""}€{t.pnl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[10px] text-[#64748B] leading-relaxed">
            {real ? "Dati storici reali dal broker Tickmill via MetaApi — puoi confrontare le date/prezzi direttamente nel tuo MT5." :
              "⚠️ Dati SIMULATI. Appena l'account MetaApi risulta CONNECTED il forward-test usa i dati reali Tickmill."}
            {" "}Risultati a scopo educativo: le performance passate non garantiscono risultati futuri.
          </p>
        </div>
      )}
    </div>
  );
}

function Mini({ label, value, color }) {
  return (
    <div className="text-center">
      <div className="overline">{label}</div>
      <div className="font-bold" style={{ color: color || "#F8FAFC" }}>{value}</div>
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
