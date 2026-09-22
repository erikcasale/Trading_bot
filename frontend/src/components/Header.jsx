import { useEffect, useState, useRef } from "react";
import { Activity, Power, LogOut, Wallet, ChevronDown } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function Header({ botStatus, account, onKill }) {
  const { user, logout } = useAuth();
  const [ticks, setTicks] = useState([]);
  const [acct, setAcct] = useState(account);
  const [detailOpen, setDetailOpen] = useState(false);
  const detailRef = useRef(null);

  useEffect(() => { setAcct(account); }, [account]);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api.get("/market/watchlist").then((r) => alive && setTicks(r.data)).catch(() => {});
      api.get("/bot").then((r) => alive && r.data?.account && setAcct(r.data.account)).catch(() => {});
    };
    load();
    const t = setInterval(load, 6000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  useEffect(() => {
    const onClick = (e) => { if (detailRef.current && !detailRef.current.contains(e.target)) setDetailOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const isReal = acct?.real === true;
  const equity = acct?.equity ?? acct?.balance ?? 100000;
  const currency = acct?.currency || "USD";
  const curSym = { USD: "$", EUR: "€", GBP: "£" }[currency] || "";
  const profit = acct?.profit ?? 0;
  const fmtMoney = (v) => `${curSym}${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const marquee = [...ticks, ...ticks];

  return (
    <header className="sticky top-0 z-50 bg-[#0F141C]/90 backdrop-blur-md border-b border-[#1E293B]">
      <div className="px-3 sm:px-4 py-2.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-9 h-9 rounded-lg bg-[#0EA5E9]/10 border border-[#0EA5E9]/40 flex items-center justify-center">
            <Activity className="w-5 h-5 text-[#0EA5E9]" />
          </div>
          <div className="leading-none">
            <div className="font-head font-extrabold tracking-tight">Apex Flow</div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] pulse-dot" />
              <span className="text-[10px] font-mono text-[#64748B]">Claude 4.6 Active</span>
            </div>
          </div>
        </div>

        <div className="hidden md:flex flex-1 overflow-hidden mx-2">
          <div className="marquee-track">
            {marquee.map((t, i) => (
              <span key={i} className="inline-flex items-center gap-2 px-4 border-r border-[#1E293B] whitespace-nowrap">
                <span className="text-xs font-semibold text-[#94A3B8]">{t.symbol}</span>
                {t.source === "warming" ? (
                  <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[#0EA5E9]">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#0EA5E9] animate-pulse" />connessione…
                  </span>
                ) : (
                  <>
                    <span className="font-mono text-xs">{t.price}</span>
                    <span className={`font-mono text-[11px] ${t.change >= 0 ? "text-up" : "text-down"}`}>
                      {t.change >= 0 ? "+" : ""}{t.change}%
                    </span>
                  </>
                )}
              </span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div ref={detailRef} className="relative hidden sm:block">
            <button data-testid="account-balance-badge" onClick={() => isReal && setDetailOpen((o) => !o)}
               className={`flex items-center gap-1.5 bg-[#0B0E17] border border-[#1E293B] rounded-lg px-3 py-1.5 transition-colors ${isReal ? "hover:border-[#10B981]/50 cursor-pointer" : "cursor-default"}`}
               title={isReal ? `Equity reale conto MetaApi (${currency}) — clic per dettagli` : "Saldo demo (broker non connesso)"}>
              <Wallet className={`w-3.5 h-3.5 ${isReal ? "text-[#10B981]" : "text-[#F59E0B]"}`} />
              <span data-testid="account-equity-value" className="font-mono text-sm font-semibold">
                {fmtMoney(equity)}
              </span>
              {isReal && (
                <span data-testid="account-pnl-value" className={`font-mono text-[11px] font-semibold ${profit >= 0 ? "text-up" : "text-down"}`}>
                  {profit >= 0 ? "+" : "-"}{fmtMoney(Math.abs(profit))}
                </span>
              )}
              <span className={`text-[10px] font-mono font-bold ${isReal ? "text-[#10B981]" : "text-[#64748B]"}`}>
                {isReal ? "REALE" : "DEMO"}
              </span>
              {isReal && <ChevronDown className={`w-3 h-3 text-[#64748B] transition-transform ${detailOpen ? "rotate-180" : ""}`} />}
            </button>

            {detailOpen && isReal && (
              <div data-testid="account-detail-panel"
                   className="absolute right-0 mt-2 w-60 bg-[#0B0E17] border border-[#1E293B] rounded-xl p-3 shadow-xl z-50 fade-up">
                <div className="overline mb-2 text-[#10B981]">Conto reale · MetaApi</div>
                <div className="space-y-1.5 font-mono text-[11px]">
                  {[["Saldo", fmtMoney(acct?.balance)],
                    ["Equity", fmtMoney(equity)],
                    ["P&L aperto", `${profit >= 0 ? "+" : "-"}${fmtMoney(Math.abs(profit))}`, profit >= 0 ? "text-up" : "text-down"],
                    ["Margine libero", fmtMoney(acct?.free_margin)],
                    ["Margine usato", fmtMoney(acct?.margin)],
                    ["Leva", acct?.leverage ? `1:${acct.leverage}` : "—"],
                    ["Valuta", currency]].map(([k, v, cls]) => (
                    <div key={k} className="flex items-center justify-between">
                      <span className="text-[#64748B]">{k}</span>
                      <span className={cls || "text-[#E2E8F0]"}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button data-testid="header-kill-switch" onClick={onKill}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors border ${
              botStatus === "running"
                ? "bg-[#EF4444]/10 border-[#EF4444]/50 text-[#EF4444] hover:bg-[#EF4444]/20"
                : "bg-[#131A24] border-[#334155] text-[#64748B]"}`}>
            <Power className="w-3.5 h-3.5" /> Kill
          </button>

          <div className="w-8 h-8 rounded-full bg-[#131A24] border border-[#334155] flex items-center justify-center text-xs font-bold text-[#94A3B8]">
            {(user?.name || "T")[0].toUpperCase()}
          </div>
          <button data-testid="logout-button" onClick={logout}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#64748B] hover:text-[#EF4444] hover:bg-[#131A24] transition-colors">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
