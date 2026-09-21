# Apex Flow — PRD

## Problema originale (utente, IT)
"App di trading automatico, non retail, metodo sicuro con winrate 98%." Poi: forward-test, dati reali Tickmill, winrate ≥85%, e infine "+50% annuo".
Posizione onesta comunicata: nessun sistema garantisce 98%/85%/+50%. Costruito come terminale DEMO/educativo che mostra la realtà (winrate alto ≠ profitto; overfitting; rischio della coda / no-SL).

## Stack & Architettura
- Backend FastAPI (`/app/backend/server.py`), MongoDB (motor), JWT Bearer (`apex_token` in localStorage).
- Frontend React (CRA+craco, alias `@`), Tailwind, shadcn/ui, recharts, lucide, sonner.
- AI: Claude Sonnet 4.6 via emergentintegrations (analisi Smart Money).
- Dati mercato: simulati server-side + REALI Tickmill via MetaApi (`/app/backend/metaapi_service.py`, fallback automatico a simulato).

## Integrazioni
- MetaApi/Tickmill: account MT5 demo (85584886, TickmillUK-Demo) CONNECTED. `.env`: METAAPI_TOKEN, METAAPI_ACCOUNT_ID. Storico OHLC reale, stato connessione, esecuzione ordini (guarded, /forwardtest/execute-live).
- Claude Sonnet 4.6 (EMERGENT_LLM_KEY).

## Implementato (2026-09-21)
- Auth JWT + account demo (demo@apexflow.io / apexflow2026), dashboard cockpit, watchlist multi-asset, grafico candlestick live con overlay OB/FVG/liquidità.
- Analisi AI Smart Money (Claude) con livelli entry/SL/TP disegnati sul grafico.
- Bot panel (config rischio, kill switch), backtest runner, tabella posizioni.
- Datasource MetaApi: `/api/datasource/status`, fetch candele reali con fallback.
- Forward-test walk-forward (`/api/forwardtest/run`): replay barra-per-barra, modello monetario unificato, equity mark-to-market, date dei trade, preset periodo (Settimana/Mese/Trimestre/Anno=D1/365), tabella operazioni per verifica manuale.
  - Modalità: `balanced` (SMC RR~1.5), `highwinrate` (mean-reversion TP piccolo/SL ampio → WR reale 85-98% ma tail risk), `nosl` (NO stop → illusione ~100% WR smascherata via equity reale/flottante/peggior flottante).
- Ottimizzatore (`/api/optimize`): grid search (entry smc/meanrev/breakout × TP × SL × trend-filter) su dati reali, scoring Calmar (annual/DD, PF≥1.05), annualizzazione, dimensionamento rischio verso target +50% annuo con cap DD; config applicabile al forward-test (params passthrough → mode "optimized"). Avvertenza overfitting in UI.
- Verifiche: iterazioni 1-4 tutte verdi (24 + 8 + 12 + 18 test), nessun bug aperto.

## Note di onestà (fondamentali)
- Winrate alto è reale ma NON implica profitto (vedi PF/expectancy).
- No-SL: equity mark-to-market mostra conto sott'acqua nonostante ~100% WR.
- +50% annuo dell'ottimizzatore = proiezione IN-SAMPLE su finestra breve → rischio overfitting elevato, non garantito.

## Backlog / prossimi step
- P1: Walk-forward out-of-sample (train/test split) per stimare la degradazione reale della config ottimizzata.
- P1: Esecuzione live guidata su Tickmill demo dal setup ottimizzato (con conferma + kill switch).
- P2: Split di server.py in router/servizi (~880 righe).
- P2: Ottimizzatore in executor per non bloccare l'event loop; paginazione storico per periodi multi-anno.
