import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Search } from "lucide-react";

const CAT_LABEL = { crypto: "Crypto", forex: "Forex", stocks: "Azioni" };

export default function Watchlist({ selected, onSelect }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [prev, setPrev] = useState({});

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/market/watchlist").then((r) => {
      if (!alive) return;
      setPrev((p) => { const n = {}; items.forEach((it) => (n[it.symbol] = it.price)); return n; });
      setItems(r.data);
    }).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
    // eslint-disable-next-line
  }, []);

  const filtered = items.filter((i) => i.symbol.toLowerCase().includes(q.toLowerCase()));
  const groups = filtered.reduce((acc, it) => { (acc[it.category] = acc[it.category] || []).push(it); return acc; }, {});

  return (
    <div className="card p-3 h-full">
      <div className="flex items-center justify-between mb-3">
        <span className="overline">Watchlist</span>
        <span className="text-[10px] font-mono text-[#64748B]">{filtered.length} strumenti</span>
      </div>
      <div className="relative mb-3">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#64748B]" />
        <input data-testid="watchlist-search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Cerca..."
          className="w-full bg-[#0B0E17] border border-[#1E293B] rounded-lg pl-8 pr-3 py-2 text-xs outline-none focus:border-[#0EA5E9] transition-colors" />
      </div>

      <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
        {Object.entries(groups).map(([cat, list]) => (
          <div key={cat}>
            <div className="overline mb-1.5 px-1">{CAT_LABEL[cat] || cat}</div>
            <div className="space-y-1">
              {list.map((it) => {
                const up = it.change >= 0;
                const testid = `market-watchlist-item-${it.symbol.replace("/", "").toLowerCase()}`;
                return (
                  <button key={it.symbol} data-testid={testid} onClick={() => onSelect(it.symbol)}
                    className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg border transition-colors ${
                      selected === it.symbol
                        ? "bg-[#1A2332] border-[#0EA5E9]/50"
                        : "bg-transparent border-transparent hover:bg-[#1A2332] hover:border-[#334155]"}`}>
                    <span className="text-sm font-semibold">{it.symbol}</span>
                    <div className="text-right">
                      <div className="font-mono text-xs">{it.price}</div>
                      <div className={`font-mono text-[10px] ${up ? "text-up" : "text-down"}`}>
                        {up ? "+" : ""}{it.change}%
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
