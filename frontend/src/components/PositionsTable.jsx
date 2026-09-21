import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { X } from "lucide-react";

export default function PositionsTable({ refreshKey, onChange }) {
  const [tab, setTab] = useState("active");
  const [data, setData] = useState({ active: [], history: [] });

  const load = () => api.get("/positions").then((r) => setData(r.data)).catch(() => {});

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [refreshKey]);

  const close = async (id) => {
    try {
      const { data: r } = await api.post(`/positions/${id}/close`);
      toast[r.pnl >= 0 ? "success" : "error"](`Posizione chiusa · ${r.pnl >= 0 ? "+" : ""}€${r.pnl}`);
      load(); onChange && onChange();
    } catch { toast.error("Errore chiusura"); }
  };

  const rows = tab === "active" ? data.active : data.history;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-1 p-0.5 rounded-lg bg-[#0B0E17] border border-[#1E293B] w-fit mb-3">
        <Tab id="active" tab={tab} setTab={setTab} label={`Posizioni Attive (${data.active.length})`} />
        <Tab id="history" tab={tab} setTab={setTab} label={`Storico (${data.history.length})`} />
      </div>

      <div className="overflow-x-auto">
        <table data-testid="open-positions-table" className="w-full text-left">
          <thead>
            <tr className="overline border-b border-[#1E293B]">
              <th className="py-2 pr-3 font-normal">Simbolo</th>
              <th className="py-2 px-3 font-normal">Tipo</th>
              <th className="py-2 px-3 font-normal text-right">Lotto</th>
              <th className="py-2 px-3 font-normal text-right">Ingresso</th>
              {tab === "active" && <th className="py-2 px-3 font-normal text-right">Corrente</th>}
              {tab === "active" && <th className="py-2 px-3 font-normal text-right hidden sm:table-cell">SL</th>}
              {tab === "active" && <th className="py-2 px-3 font-normal text-right hidden sm:table-cell">TP</th>}
              {tab === "history" && <th className="py-2 px-3 font-normal text-center">Esito</th>}
              <th className="py-2 px-3 font-normal text-right">PnL</th>
              {tab === "active" && <th className="py-2 pl-3 font-normal text-right">Azioni</th>}
            </tr>
          </thead>
          <tbody className="font-mono text-xs">
            {rows.length === 0 && (
              <tr><td colSpan={9} className="py-8 text-center text-[#64748B] font-sans text-sm">
                Nessuna posizione</td></tr>
            )}
            {rows.map((p, i) => (
              <tr key={p.id} className="border-b border-[#1E293B]/60 hover:bg-[#1A2332] transition-colors">
                <td className="py-2.5 pr-3 font-sans font-semibold text-sm">{p.symbol}</td>
                <td className="py-2.5 px-3">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    p.side === "BUY" ? "bg-[#10B981]/10 text-up" : "bg-[#EF4444]/10 text-down"}`}>{p.side}</span>
                </td>
                <td className="py-2.5 px-3 text-right">{p.lots}</td>
                <td className="py-2.5 px-3 text-right">{p.entry}</td>
                {tab === "active" && <td className="py-2.5 px-3 text-right">{p.current}</td>}
                {tab === "active" && <td className="py-2.5 px-3 text-right text-down hidden sm:table-cell">{p.sl || "—"}</td>}
                {tab === "active" && <td className="py-2.5 px-3 text-right text-up hidden sm:table-cell">{p.tp || "—"}</td>}
                {tab === "history" && (
                  <td className="py-2.5 px-3 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                      p.result === "win" ? "bg-[#10B981]/10 text-up" : "bg-[#EF4444]/10 text-down"}`}>
                      {p.result === "win" ? "WIN" : "LOSS"}</span>
                  </td>
                )}
                <td className={`py-2.5 px-3 text-right font-semibold ${p.pnl >= 0 ? "text-up" : "text-down"}`}>
                  {p.pnl >= 0 ? "+" : ""}€{p.pnl}
                </td>
                {tab === "active" && (
                  <td className="py-2.5 pl-3 text-right">
                    <button data-testid={`close-position-button-${i}`} onClick={() => close(p.id)}
                      className="inline-flex items-center gap-1 text-[10px] text-[#EF4444] hover:bg-[#EF4444]/10 border border-[#EF4444]/40 rounded px-2 py-1 transition-colors">
                      <X className="w-3 h-3" /> Chiudi
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tab({ id, tab, setTab, label }) {
  return (
    <button data-testid={`positions-tab-${id}`} onClick={() => setTab(id)}
      className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
        tab === id ? "bg-[#1A2332] text-white" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
      {label}
    </button>
  );
}
