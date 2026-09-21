import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Bot, Power, ShieldAlert, Gauge, Layers3, Zap } from "lucide-react";

export default function BotPanel({ bot, onRefresh }) {
  const [cfg, setCfg] = useState({ winrate_filter: 98, max_drawdown: 1.5, risk_percent: 1.0, max_open_trades: 3, lot_mode: "dynamic" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (bot) setCfg({
      winrate_filter: bot.winrate_filter, max_drawdown: bot.max_drawdown,
      risk_percent: bot.risk_percent, max_open_trades: bot.max_open_trades, lot_mode: bot.lot_mode,
    });
  }, [bot]);

  const running = bot?.status === "running";

  const toggle = async () => {
    try {
      const { data } = await api.post("/bot/toggle");
      toast[data.status === "running" ? "success" : "message"](
        data.status === "running" ? "Bot ATTIVO — esecuzione automatica avviata" : "Bot in pausa");
      onRefresh();
    } catch { toast.error("Errore"); }
  };

  const emergency = async () => {
    try { await api.post("/bot/stop"); toast.error("BLOCCO DI EMERGENZA attivato"); onRefresh(); }
    catch { toast.error("Errore"); }
  };

  const save = async (next) => {
    setSaving(true);
    try { await api.put("/bot", next); onRefresh(); }
    catch { toast.error("Errore salvataggio"); }
    finally { setSaving(false); }
  };

  const update = (key, val) => { const next = { ...cfg, [key]: val }; setCfg(next); save(next); };

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-[#0EA5E9]" />
          <span className="font-head font-bold text-sm">Bot Trading Automatico</span>
        </div>
        <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold ${
          running ? "border-[#10B981]/50 bg-[#10B981]/10 text-[#10B981]" : "border-[#334155] text-[#64748B]"}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-[#10B981] pulse-dot" : "bg-[#64748B]"}`} />
          {running ? "IN ESECUZIONE" : "IN PAUSA"}
        </div>
      </div>

      <button data-testid="bot-status-toggle" onClick={toggle}
        className={`w-full flex items-center justify-center gap-2 font-semibold py-2.5 rounded-lg transition-colors mb-3 ${
          running ? "bg-[#131A24] border border-[#334155] text-[#94A3B8] hover:bg-[#1A2332]"
                  : "bg-[#10B981] hover:bg-[#059669] text-[#05130D]"}`}>
        <Power className="w-4 h-4" /> {running ? "Metti in Pausa" : "Avvia Bot"}
      </button>

      <div className="space-y-3">
        <Field icon={Gauge} label="Filtro Winrate Target" testid="bot-winrate-filter"
          value={cfg.winrate_filter} suffix="%" min={80} max={99}
          onChange={(v) => update("winrate_filter", v)} />
        <Field icon={ShieldAlert} label="Max Drawdown" testid="risk-management-max-drawdown"
          value={cfg.max_drawdown} suffix="%" step={0.1} min={0.5} max={10}
          onChange={(v) => update("max_drawdown", v)} />
        <Field icon={Zap} label="Rischio per Trade" testid="risk-management-lot-input"
          value={cfg.risk_percent} suffix="%" step={0.1} min={0.1} max={5}
          onChange={(v) => update("risk_percent", v)} />
        <Field icon={Layers3} label="Max Trade Aperti" testid="risk-management-max-trades"
          value={cfg.max_open_trades} min={1} max={10}
          onChange={(v) => update("max_open_trades", v)} />
      </div>

      <div className="flex items-center justify-between mt-3 px-2.5 py-2 rounded-lg bg-[#0B0E17] border border-[#1E293B]">
        <span className="text-[11px] text-[#64748B]">Broker Gateway</span>
        <span className="text-[11px] font-mono text-[#F59E0B]">Tickmill ECN Demo · 2ms</span>
      </div>

      <button data-testid="bot-emergency-stop-button" onClick={emergency}
        className="w-full flex items-center justify-center gap-2 mt-3 bg-[#EF4444]/10 hover:bg-[#EF4444]/20 border border-[#EF4444]/50 text-[#EF4444] font-bold py-2.5 rounded-lg transition-colors">
        <ShieldAlert className="w-4 h-4" /> BLOCCO DI EMERGENZA
      </button>
      {saving && <div className="text-[10px] text-[#64748B] text-center mt-2 font-mono">salvataggio...</div>}
    </div>
  );
}

function Field({ icon: Icon, label, value, onChange, suffix, step = 1, min, max, testid }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 overline mb-1">
        <Icon className="w-3 h-3" /> {label}
      </label>
      <div className="flex items-center gap-2">
        <input data-testid={testid} type="number" value={value} step={step} min={min} max={max}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="flex-1 bg-[#0B0E17] border border-[#1E293B] rounded-lg px-3 py-1.5 font-mono text-sm outline-none focus:border-[#0EA5E9] transition-colors" />
        {suffix && <span className="font-mono text-xs text-[#64748B] w-6">{suffix}</span>}
      </div>
    </div>
  );
}
