import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import Header from "@/components/Header";
import Watchlist from "@/components/Watchlist";
import CandleChart from "@/components/CandleChart";
import AiPanel from "@/components/AiPanel";
import BotPanel from "@/components/BotPanel";
import BacktestPanel from "@/components/BacktestPanel";
import ForwardTest from "@/components/ForwardTest";
import PositionsTable from "@/components/PositionsTable";

export default function Dashboard() {
  const [symbol, setSymbol] = useState("EUR/USD");
  const [bot, setBot] = useState(null);
  const [account, setAccount] = useState(null);
  const [posKey, setPosKey] = useState(0);
  const [setup, setSetup] = useState(null);

  const selectSymbol = (s) => { setSymbol(s); setSetup(null); };
  const handleAnalysis = (d) =>
    setSetup(d?.analysis?.setup ? { ...d.analysis.setup, symbol: d.symbol } : null);

  const loadBot = useCallback(() => {
    api.get("/bot").then((r) => { setBot(r.data.bot); setAccount(r.data.account); }).catch(() => {});
  }, []);

  useEffect(() => { loadBot(); }, [loadBot]);

  const kill = async () => { await api.post("/bot/stop"); loadBot(); };

  return (
    <div className="min-h-screen bg-[#080B10]">
      <Header botStatus={bot?.status} account={account} onKill={kill} />

      <main className="p-3 sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h1 className="font-head text-2xl sm:text-3xl font-extrabold tracking-tight">Terminale Operativo</h1>
            <p className="text-sm text-[#94A3B8]">Smart Money Flow · Multi-asset · Motore Claude Sonnet 4.6</p>
          </div>
          <span className="overline">Conto Demo · Tickmill Real: <span className="text-[#F59E0B]">Pending</span></span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 md:gap-4">
          <div className="lg:col-span-3 xl:col-span-2">
            <Watchlist selected={symbol} onSelect={selectSymbol} />
          </div>

          <div className="lg:col-span-6 xl:col-span-7 space-y-4">
            <CandleChart symbol={symbol} setup={setup} />
            <BacktestPanel symbol={symbol} />
          </div>

          <div className="lg:col-span-3 space-y-4">
            <AiPanel symbol={symbol} onAnalysis={handleAnalysis} />
            <BotPanel bot={bot} onRefresh={loadBot} />
          </div>

          <div className="lg:col-span-12">
            <ForwardTest symbol={symbol} />
          </div>

          <div className="lg:col-span-12">
            <PositionsTable refreshKey={posKey} onChange={() => { loadBot(); setPosKey((k) => k + 1); }} />
          </div>
        </div>

        <p className="text-[11px] text-[#64748B] text-center mt-6 max-w-3xl mx-auto leading-relaxed">
          Apex Flow è un ambiente dimostrativo a scopo educativo. Nessun ordine reale viene inviato ad alcun broker.
          Le metriche di winrate e i risultati dei backtest sono simulati: il trading comporta un rischio concreto di
          perdita del capitale e nessun sistema garantisce profitti.
        </p>
      </main>
    </div>
  );
}
