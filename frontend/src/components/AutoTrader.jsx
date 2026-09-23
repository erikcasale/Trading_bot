import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Square, Loader2, RefreshCw, Bot, Wifi, WifiOff, Clock, TrendingUp, TrendingDown, X, Activity, ChevronDown, AlertTriangle, Layers, ShieldOff } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const CUR = { USD: "$", EUR: "€", GBP: "£" };

const money = (v, c = "EUR") => `${CUR[c] || ""}${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtTime = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
};
const SleeveBadge = ({ s }) => (
  <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${s === "strength" ? "bg-[#8B5CF6]/20 text-[#A78BFA]" : "bg-[#0EA5E9]/20 text-[#38BDF8]"}`}>
    {s === "strength" ? "forza" : "mean-rev"}
  </span>
);

export default function AutoTrader() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const poll = useRef(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/autobot"); setData(data); } catch { /* keep last */ }
  }, []);

  useEffect(() => { load(); poll.current = setInterval(load, 5000); return () => clearInterval(poll.current); }, [load]);

  const start = async () => {
    if (!window.confirm("Avviare il bot? Invierà ordini REALI sul tuo conto MT5 demo secondo la strategia combo D1 (nessuno stop di prezzo, solo time-stop).")) return;
    setBusy(true);
    try { await api.post("/autobot/start"); toast.success("Bot avviato — valutazione segnali in corso"); await load(); }
    catch { toast.error("Avvio non riuscito"); } finally { setBusy(false); }
  };
  const stop = async () => {
    setBusy(true);
    try { await api.post("/autobot/stop"); toast("Bot fermato — le posizioni aperte restano"); await load(); }
    catch { toast.error("Stop non riuscito"); } finally { setBusy(false); }
  };
  const runNow = async () => {
    setBusy(true);
    try { await api.post("/autobot/run-now"); toast.success("Ciclo manuale avviato"); setTimeout(load, 1500); }
    catch (e) { toast.error(e?.response?.data?.detail || "Impossibile eseguire il ciclo"); } finally { setBusy(false); }
  };
  const closeTrade = async (pid, sym) => {
    if (!window.confirm(`Chiudere la posizione ${sym} al mercato?`)) return;
    try { await api.post(`/autobot/close/${pid}`); toast.success(`Chiusura ${sym} inviata`); setTimeout(load, 1500); }
    catch (e) { toast.error(e?.response?.data?.detail || "Chiusura non riuscita"); }
  };

  if (!data) return (
    <div className="flex items-center justify-center py-24 text-[#64748B]" data-testid="autobot-loading">
      <Loader2 className="w-5 h-5 animate-spin mr-2" /> Caricamento cockpit…
    </div>
  );

  const { running, strategy, connected, account, last_run, next_run, cycle_status } = data;
  const cur = account?.currency || "EUR";
  const open = data.open_trades || [];
  const closed = data.closed_trades || [];
  const cycling = cycle_status === "running";
  const openPnl = open.reduce((s, p) => s + (p.profit || 0), 0);
  const closedPnl = closed.reduce((s, p) => s + (p.profit || 0), 0);

  return (
    <div className="space-y-4" data-testid="autobot-cockpit">
      {/* Control + status card */}
      <div className="rounded-2xl border border-[#1E293B] bg-gradient-to-br from-[#0F141C] to-[#0B0E17] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center border ${running ? "bg-[#10B981]/10 border-[#10B981]/40" : "bg-[#131A24] border-[#334155]"}`}>
              <Bot className={`w-6 h-6 ${running ? "text-[#10B981]" : "text-[#64748B]"}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-head text-lg font-extrabold tracking-tight">Auto-Trader</h2>
                <span data-testid="autobot-state" className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${running ? "bg-[#10B981]/15 text-[#10B981]" : "bg-[#334155]/40 text-[#64748B]"}`}>
                  {running ? "● ATTIVO" : "○ FERMO"}
                </span>
                {cycling && <span className="inline-flex items-center gap-1 text-[10px] text-[#0EA5E9] font-mono"><Loader2 className="w-3 h-3 animate-spin" />ciclo…</span>}
              </div>
              <p className="text-sm text-[#94A3B8] mt-0.5">{strategy?.name}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[11px] text-[#64748B] font-mono">
                <span className="inline-flex items-center gap-1"><Layers className="w-3 h-3" />{strategy?.pairs} coppie · {strategy?.timeframe}</span>
                <span className="inline-flex items-center gap-1"><ShieldOff className="w-3 h-3 text-[#F59E0B]" />no stop di prezzo</span>
                <span>slot {strategy?.caps?.meanrev} mean-rev / {strategy?.caps?.strength} forza</span>
                <span>time-stop {strategy?.time_stop_days}g · {strategy?.lot_per_10k} lotti/€10k</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {running && (
              <button data-testid="autobot-runnow-button" onClick={runNow} disabled={busy || cycling}
                className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border border-[#334155] text-[#94A3B8] hover:text-white hover:border-[#0EA5E9]/50 transition-colors disabled:opacity-50">
                <RefreshCw className={`w-3.5 h-3.5 ${cycling ? "animate-spin" : ""}`} />Valuta ora
              </button>
            )}
            {running ? (
              <button data-testid="autobot-stop-button" onClick={stop} disabled={busy}
                className="inline-flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-lg bg-[#EF4444]/15 border border-[#EF4444]/50 text-[#EF4444] hover:bg-[#EF4444]/25 transition-colors disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}Ferma bot
              </button>
            ) : (
              <button data-testid="autobot-start-button" onClick={start} disabled={busy || !connected}
                className="inline-flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-lg bg-[#10B981] hover:bg-[#059669] text-white transition-colors disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}Avvia bot
              </button>
            )}
          </div>
        </div>

        {/* Stat strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-4">
          <Stat label="Connessione" testid="autobot-connection"
            value={connected ? "Connesso" : "Offline"}
            icon={connected ? <Wifi className="w-3.5 h-3.5 text-[#10B981]" /> : <WifiOff className="w-3.5 h-3.5 text-[#EF4444]" />}
            cls={connected ? "text-[#10B981]" : "text-[#EF4444]"} />
          <Stat label="Equity conto" testid="autobot-equity" value={money(account?.equity ?? account?.balance, cur)} />
          <Stat label="P&L aperto" testid="autobot-open-pnl" value={`${openPnl >= 0 ? "+" : "-"}${money(Math.abs(openPnl), cur)}`} cls={openPnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"} />
          <Stat label="Posizioni" testid="autobot-open-count" value={`${open.length} / ${strategy?.max_concurrent}`} />
          <Stat label="Ultimo ciclo" testid="autobot-last-run" value={fmtTime(last_run)} icon={<Clock className="w-3.5 h-3.5 text-[#64748B]" />} />
          <Stat label="Prossimo ciclo" testid="autobot-next-run" value={running ? fmtTime(next_run) : "—"} icon={<Clock className="w-3.5 h-3.5 text-[#64748B]" />} />
        </div>

        {!connected && (
          <div className="mt-3 flex items-start gap-2 text-[11px] text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/40 rounded-lg p-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>Broker MetaApi non connesso: impossibile avviare il bot o inviare ordini finché la connessione non è ripristinata.</span>
          </div>
        )}
      </div>

      {/* Open trades */}
      <div className="rounded-2xl border border-[#1E293B] bg-[#0B0E17] overflow-hidden" data-testid="autobot-open-section">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <h3 className="font-head font-bold text-sm inline-flex items-center gap-2"><Activity className="w-4 h-4 text-[#10B981]" />Trade aperti</h3>
          <span className="overline">{open.length} posizioni · {money(account?.equity, cur)} equity</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]" data-testid="autobot-open-table">
            <thead>
              <tr className="text-[#64748B] text-left">
                {["Simbolo", "Lato", "Motore", "Volume", "Ingresso", "Attuale", "TP", "P&L", "Aperta", ""].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {open.length === 0 && (
                <tr><td colSpan={10} className="px-3 py-8 text-center text-[#64748B]" data-testid="autobot-open-empty">
                  {running ? "Nessuna posizione aperta dal bot al momento." : "Bot fermo. Avvialo per far aprire i trade in automatico."}
                </td></tr>
              )}
              {open.map((p, i) => (
                <tr key={i} data-testid={`autobot-open-row-${i}`} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="px-3 py-2 font-semibold text-white">{p.symbol}</td>
                  <td className={`px-3 py-2 font-bold ${p.side === "BUY" ? "text-[#10B981]" : "text-[#EF4444]"}`}>
                    <span className="inline-flex items-center gap-1">{p.side === "BUY" ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}{p.side}</span>
                  </td>
                  <td className="px-3 py-2"><SleeveBadge s={p.sleeve} /></td>
                  <td className="px-3 py-2 font-mono text-[#CBD5E1]">{p.volume}</td>
                  <td className="px-3 py-2 font-mono text-[#94A3B8]">{p.open_price}</td>
                  <td className="px-3 py-2 font-mono text-[#CBD5E1]">{p.current_price}</td>
                  <td className="px-3 py-2 font-mono text-[#A78BFA]">{p.tp || "—"}</td>
                  <td className={`px-3 py-2 font-mono font-bold ${p.profit >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>{p.profit >= 0 ? "+" : "-"}{money(Math.abs(p.profit), cur)}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-[#64748B]">{fmtTime(p.time)}</td>
                  <td className="px-3 py-2">
                    <button data-testid={`autobot-close-${i}`} onClick={() => closeTrade(p.id, p.symbol)}
                      className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-md border border-[#EF4444]/40 text-[#EF4444] hover:bg-[#EF4444]/10 transition-colors">
                      <X className="w-3 h-3" />Chiudi
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Closed trades */}
      <div className="rounded-2xl border border-[#1E293B] bg-[#0B0E17] overflow-hidden" data-testid="autobot-closed-section">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <h3 className="font-head font-bold text-sm inline-flex items-center gap-2"><Layers className="w-4 h-4 text-[#0EA5E9]" />Trade chiusi</h3>
          <span className={`overline ${closedPnl >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>realizzato {closedPnl >= 0 ? "+" : "-"}{money(Math.abs(closedPnl), cur)} · {closed.length} trade</span>
        </div>
        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table className="w-full text-[12px]" data-testid="autobot-closed-table">
            <thead className="sticky top-0 bg-[#0B0E17]">
              <tr className="text-[#64748B] text-left">
                {["Chiusa", "Simbolo", "Lato", "Motore", "Volume", "Prezzo", "P&L netto"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {closed.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-[#64748B]" data-testid="autobot-closed-empty">
                  Nessun trade chiuso di recente sul conto demo.
                </td></tr>
              )}
              {closed.map((p, i) => {
                const sleeve = (p.comment || "").includes("strength") ? "strength" : (p.comment || "").includes("apexflow") ? "meanrev" : null;
                return (
                  <tr key={i} data-testid={`autobot-closed-row-${i}`} className="border-t border-white/5 hover:bg-white/[0.02]">
                    <td className="px-3 py-2 font-mono text-[11px] text-[#94A3B8]">{fmtTime(p.time)}</td>
                    <td className="px-3 py-2 font-semibold text-white">{p.symbol}</td>
                    <td className={`px-3 py-2 font-bold ${p.side === "BUY" ? "text-[#10B981]" : "text-[#EF4444]"}`}>{p.side}</td>
                    <td className="px-3 py-2">{sleeve ? <SleeveBadge s={sleeve} /> : <span className="text-[10px] text-[#64748B]">manuale</span>}</td>
                    <td className="px-3 py-2 font-mono text-[#CBD5E1]">{p.volume}</td>
                    <td className="px-3 py-2 font-mono text-[#94A3B8]">{p.price}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${p.profit >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>{p.profit >= 0 ? "+" : "-"}{money(Math.abs(p.profit), cur)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Activity log */}
      <div className="rounded-2xl border border-[#1E293B] bg-[#0B0E17] overflow-hidden" data-testid="autobot-log-section">
        <button onClick={() => setLogOpen((o) => !o)} data-testid="autobot-log-toggle"
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors">
          <h3 className="font-head font-bold text-sm inline-flex items-center gap-2"><Clock className="w-4 h-4 text-[#64748B]" />Registro attività</h3>
          <ChevronDown className={`w-4 h-4 text-[#64748B] transition-transform ${logOpen ? "rotate-180" : ""}`} />
        </button>
        {logOpen && (
          <div className="px-4 pb-3 max-h-64 overflow-y-auto space-y-1" data-testid="autobot-log-list">
            {(data.log || []).length === 0 && <div className="text-[11px] text-[#64748B] py-2">Nessuna attività registrata.</div>}
            {(data.log || []).map((l, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px] font-mono border-b border-white/5 py-1">
                <span className="text-[#475569] shrink-0">{fmtTime(l.ts)}</span>
                <span className="text-[#CBD5E1]">{l.msg}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="text-[11px] text-[#64748B] text-center max-w-3xl mx-auto leading-relaxed">
        Il bot invia ordini reali sul conto <b className="text-[#F59E0B]">MT5 demo</b> collegato via MetaApi. Strategia combo D1 (mean-reversion + forza valutaria), nessuno stop di prezzo — protezione solo tramite take-profit, time-stop e limite posizioni. I risultati storici del backtest non garantiscono profitti futuri: il trading comporta rischio di perdita del capitale.
      </p>
    </div>
  );
}

const Stat = ({ label, value, icon, cls, testid }) => (
  <div className="rounded-xl bg-[#0B0E17] border border-[#1E293B] px-3 py-2">
    <div className="overline mb-1">{label}</div>
    <div data-testid={testid} className={`text-sm font-mono font-semibold inline-flex items-center gap-1.5 ${cls || "text-white"}`}>
      {icon}{value}
    </div>
  </div>
);
