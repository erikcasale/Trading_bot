import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import Header from "@/components/Header";
import AutoTrader from "@/components/AutoTrader";

export default function Dashboard() {
  const [bot, setBot] = useState(null);
  const [account, setAccount] = useState(null);

  const loadBot = useCallback(() => {
    api.get("/autobot").then((r) => {
      setBot({ status: r.data.running ? "running" : "stopped" });
      setAccount(r.data.account ? { ...r.data.account, real: r.data.connected } : null);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadBot(); const t = setInterval(loadBot, 6000); return () => clearInterval(t); }, [loadBot]);

  const kill = async () => { await api.post("/autobot/stop"); loadBot(); };

  return (
    <div className="min-h-screen bg-[#080B10]">
      <Header botStatus={bot?.status} account={account} onKill={kill} />

      <main className="p-3 sm:p-5 max-w-6xl mx-auto">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="font-head text-2xl sm:text-3xl font-extrabold tracking-tight">Terminale Operativo</h1>
            <p className="text-sm text-[#94A3B8]">Trading automatico · Tickmill MT5 Demo · MetaApi</p>
          </div>
          <span className="overline">Conto Demo · combo D1 auto</span>
        </div>

        <AutoTrader />
      </main>
    </div>
  );
}
