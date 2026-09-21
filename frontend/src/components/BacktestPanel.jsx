import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Play, Loader2, TrendingUp, Percent, Activity, Layers } from "lucide-react";

const PERIODS = [["1M", "1 Mese"], ["6M", "6 Mesi"], ["1Y", "1 Anno"], ["3Y", "3 Anni"]];

export default function BacktestPanel({ symbol }) {
  const [period, setPeriod] = useState("6M");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);

  const run = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/backtest", { symbol, period });
      setRes(data);
      toast.success(`Backtest completato · Winrate ${data.winrate}%`);
    } catch { toast.error("Errore backtest"); }
    finally { setLoading(false); }
  };

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#10B981]" />
          <span className="font-head font-bold text-sm">Simulatore & Runner Backtest</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
            {PERIODS.map(([v, l]) => (
              <button key={v} data-testid={`backtest-period-${v}`} onClick={() => setPeriod(v)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors ${
                  period === v ? "bg-[#1A2332] text-[#10B981]" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
                {l}
              </button>
            ))}
          </div>
          <button data-testid="backtest-run-button" onClick={run} disabled={loading}
            className="inline-flex items-center gap-1.5 bg-[#10B981] hover:bg-[#059669] text-[#05130D] text-xs font-bold px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Esegui
          </button>
        </div>
      </div>

      {!res ? (
        <div className="h-[220px] flex flex-col items-center justify-center text-center text-[#64748B] border border-dashed border-[#1E293B] rounded-lg">
          <Activity className="w-8 h-8 mb-2 opacity-50" />
          <p className="text-xs">Esegui un backtest su <b className="text-[#94A3B8]">{symbol}</b> per vedere equity curve e metriche.</p>
        </div>
      ) : (
        <div className="space-y-4 fade-up">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            <Stat testid="backtest-winrate-stat" icon={Percent} label="Win Rate" value={`${res.winrate}%`} color="#10B981" />
            <Stat icon={TrendingUp} label="Profit Factor" value={res.profit_factor} color="#0EA5E9" />
            <Stat icon={Activity} label="Max Drawdown" value={`-${res.max_drawdown}%`} color="#EF4444" />
            <Stat icon={Layers} label="Operazioni" value={res.total_trades} color="#94A3B8" />
            <Stat icon={TrendingUp} label="Profitto Netto" value={`+€${res.net_profit.toLocaleString("it-IT")}`} color="#10B981" />
          </div>

          <div data-testid="backtest-equity-chart" className="rounded-lg border border-[#1E293B] bg-[#0B0E17] p-2">
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={res.equity_curve} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10B981" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#10B981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 4" stroke="#1E293B" vertical={false} />
                <XAxis dataKey="t" tick={{ fill: "#64748B", fontSize: 10 }} axisLine={{ stroke: "#1E293B" }} tickLine={false} />
                <YAxis tick={{ fill: "#64748B", fontSize: 10 }} axisLine={false} tickLine={false} width={54}
                  tickFormatter={(v) => `€${(v / 1000).toFixed(0)}k`} domain={["dataMin", "dataMax"]} />
                <Tooltip contentStyle={{ background: "#131A24", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#94A3B8" }} formatter={(v) => [`€${v.toLocaleString("it-IT")}`, "Equity"]} />
                <Area type="monotone" dataKey="equity" stroke="#10B981" strokeWidth={2} fill="url(#eq)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="overline mb-2">Forward-Testing Live Log</div>
            <div className="space-y-1 max-h-[130px] overflow-y-auto">
              {res.log.map((l, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] font-mono px-2.5 py-1.5 rounded bg-[#0B0E17] border border-[#1E293B]">
                  <span className="text-[#64748B]">{l.time}</span>
                  <span className="text-[#94A3B8]">{l.symbol}</span>
                  <span className={l.side === "BUY" ? "text-up" : "text-down"}>{l.side}</span>
                  <span className={`px-1.5 rounded text-[10px] font-bold ${l.result === "win" ? "text-up" : "text-down"}`}>
                    {l.result === "win" ? "WIN" : "LOSS"}
                  </span>
                  <span className={l.pnl >= 0 ? "text-up" : "text-down"}>{l.pnl >= 0 ? "+" : ""}€{l.pnl}</span>
                </div>
              ))}
            </div>
          </div>

          <p className="text-[10px] text-[#64748B] leading-relaxed">
            ⚠️ Risultati <b className="text-[#94A3B8]">simulati</b> su dati demo. Le performance passate non
            garantiscono risultati futuri.
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
