import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Sparkles, Loader2, Target, TrendingUp, TrendingDown, Layers, Droplets } from "lucide-react";

const BIAS = {
  bullish: { label: "Rialzista", color: "#10B981", Icon: TrendingUp },
  bearish: { label: "Ribassista", color: "#EF4444", Icon: TrendingDown },
  neutral: { label: "Neutrale", color: "#94A3B8", Icon: Target },
};

export default function AiPanel({ symbol, timeframe = "M15", onAnalysis }) {
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);

  const run = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/ai/analysis", { symbol, timeframe });
      setRes(data);
      onAnalysis && onAnalysis(data);
      toast.success("Analisi Smart Money generata");
    } catch (e) {
      toast.error("Errore durante l'analisi AI");
    } finally {
      setLoading(false);
    }
  };

  const a = res?.analysis;
  const bias = BIAS[a?.bias] || BIAS.neutral;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#8B5CF6]" />
          <span className="font-head font-bold text-sm">Analisi Istituzionale AI</span>
        </div>
        <span className="overline">SMC · Claude 4.6</span>
      </div>

      {!res && (
        <div className="text-center py-6">
          <p className="text-xs text-[#94A3B8] mb-4 leading-relaxed">
            Leggi il mercato come le desk istituzionali: order block, fair value gap,
            manipolazione della liquidità e struttura di mercato su <b className="text-white">{symbol}</b>.
          </p>
          <button data-testid="ai-run-analysis-button" onClick={run} disabled={loading}
            className="inline-flex items-center gap-2 bg-[#8B5CF6] hover:bg-[#7C3AED] text-white text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors disabled:opacity-60">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            Genera Analisi Smart Money
          </button>
        </div>
      )}

      {res && (
        <div className="space-y-3 fade-up">
          <div className="flex items-center justify-between">
            <div data-testid="ai-liquidity-bias-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border"
              style={{ borderColor: `${bias.color}55`, background: `${bias.color}15`, color: bias.color }}>
              <bias.Icon className="w-3.5 h-3.5" />
              <span className="text-xs font-bold">Bias {bias.label}</span>
            </div>
            <div className="text-right">
              <div className="overline">Confidence</div>
              <div className="font-mono font-bold text-lg" style={{ color: bias.color }}>{a.score}%</div>
            </div>
          </div>

          <p className="text-xs text-[#94A3B8] leading-relaxed bg-[#0B0E17] border border-[#1E293B] rounded-lg p-3">
            {a.narrative}
          </p>

          {a.setup && (
            <div className="rounded-lg border border-[#334155] bg-[#0B0E17] p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="overline">Setup Operativo</span>
                <span className={`text-xs font-bold ${a.setup.direction === "BUY" ? "text-up" : "text-down"}`}>
                  {a.setup.direction} · RR {a.setup.rr}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-y-1.5 gap-x-3 font-mono text-xs">
                <Row label="Entry" val={a.setup.entry} color="#F8FAFC" />
                <Row label="Stop Loss" val={a.setup.sl} color="#EF4444" />
                <Row label="TP 1" val={a.setup.tp1} color="#10B981" />
                <Row label="TP 2" val={a.setup.tp2} color="#10B981" />
                <Row label="TP 3" val={a.setup.tp3} color="#10B981" />
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <div data-testid="ai-order-block-card" className="rounded-lg border border-[#F59E0B]/30 bg-[#F59E0B]/5 p-2.5">
              <div className="flex items-center gap-1.5 mb-1"><Layers className="w-3 h-3 text-[#F59E0B]" />
                <span className="text-[10px] font-mono text-[#F59E0B]">ORDER BLOCK</span></div>
              <div className="text-sm font-bold">{res.zones?.order_blocks?.length || 0}</div>
              <div className="text-[10px] text-[#64748B]">zone attive</div>
            </div>
            <div className="rounded-lg border border-[#0EA5E9]/30 bg-[#0EA5E9]/5 p-2.5">
              <div className="flex items-center gap-1.5 mb-1"><Droplets className="w-3 h-3 text-[#0EA5E9]" />
                <span className="text-[10px] font-mono text-[#0EA5E9]">LIQUIDITÀ</span></div>
              <div className="font-mono text-[11px]">B {res.zones?.liquidity?.buy_side}</div>
              <div className="font-mono text-[11px]">S {res.zones?.liquidity?.sell_side}</div>
            </div>
          </div>

          {a.key_levels?.length > 0 && (
            <ul className="space-y-1">
              {a.key_levels.map((k, i) => (
                <li key={i} className="text-[11px] text-[#94A3B8] flex items-start gap-1.5">
                  <span className="text-[#8B5CF6] mt-0.5">▸</span> {k}
                </li>
              ))}
            </ul>
          )}

          <button data-testid="ai-rerun-button" onClick={run} disabled={loading}
            className="w-full flex items-center justify-center gap-2 text-xs text-[#94A3B8] hover:text-white bg-[#131A24] hover:bg-[#1A2332] border border-[#334155] py-2 rounded-lg transition-colors">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Rigenera analisi
          </button>
        </div>
      )}
    </div>
  );
}

function Row({ label, val, color }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[#64748B]">{label}</span>
      <span style={{ color }}>{val}</span>
    </div>
  );
}
