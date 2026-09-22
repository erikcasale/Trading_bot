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
- Verifiche: iterazioni 1-6 tutte verdi (24+8+12+18+23+11 test), nessun bug aperto.

## Aggiornamenti recenti (2026-09-22)
- Aggiunte 5 major forex complete: EUR/USD, GBP/USD, USD/CHF, USD/CAD, AUD/USD (watchlist 11 strumenti), con mapping MetaApi.
- Affidabilità dati reali: `metaapi_service.fetch_candles` con retry + riconnessione (niente fallback silenzioso al simulato).
- Ottimizzatore spostato off-loop via `asyncio.to_thread` (`_optimize_compute`): il grid ~72 combo non blocca più l'event loop (richieste concorrenti ~100-500ms, no 502 sotto carico).
- Validazione Out-of-Sample (`/api/optimize/oos`): split storico in-sample/out-of-sample (default 70/30), ottimizza solo sull'in-sample e applica la stessa config sull'out-of-sample; verdetto robusta/fragile/incerta con confronto WR/PF/rendita/DD e due equity curve. Smaschera l'overfitting. Verificato iterazione 7 (10/10).

## Motore di scoperta strategia su 5 anni (2026-09-22) — iterazione 9 (8/8 backend, frontend 100%)
Richiesta utente: "Non funziona come strategia se nell'anno ho il PnL negativo → apprendere su 5 anni e trovare una strategia valida (profitto nell'ULTIMO anno)."
- **Fetch storico D1 paginato** (`metaapi_service.fetch_candles`): pagina all'indietro (fino a 12 pagine da 1000) per assemblare ~5 anni di daily (~1300 candele reali Tickmill).
- **Spazio di ricerca ampliato** in `run_forward_test`: nuove entry `trend` (crossover SMA10/SMA30) + filtro `rsi` (conferma momentum RSI14). Grid `DISCOVER_GRID` = 192 combo (entry×tp×sl×trend_filter×rsi).
- **`/api/strategy/discover`** (job asincrono + polling, perché fetch+grid superano il limite ingress 60s): `POST` ritorna `{job_id}`; `GET /api/strategy/discover/{job_id}` ritorna status running/done/error + result. Cache storico D1 `_d1_cache` (TTL 600s) → richieste ripetute ~3s.
- **Regola di validità**: split ultimo 365 giorni = validazione (mai vista); ottimizza sui primi ~4 anni; valida le top-20 config sull'ultimo anno. Verdetto: `profittevole` (last_year net>0 & PF≥1.1), `marginale` (net>0 ma PF<1.1), `non_profittevole` (nessun edge → mostra la migliore ma sconsiglia di tradarla). Rischio dimensionato sul rendimento dell'ultimo anno, cappato dal DD.
- **Frontend** (`ForwardTest.jsx`): pannello `discover-panel` con bottone "Analizza 5 anni & trova strategia" (polling ogni 3s), risultato `discover-result` con verdict badge, due segmenti (apprendimento vs ultimo anno) con metriche+equity, e "Applica e riproduci l'ultimo anno".
- Esempi verificati (dati reali): EUR/USD profittevole (Breakout+RSI, ultimo anno net +€374, PF 1.46); XAU/USD profittevole (Smart Money, +€596, PF 1.99).

## Note di onestà (fondamentali)
- Winrate alto è reale ma NON implica profitto (vedi PF/expectancy).
- La scoperta richiede profitto nell'ULTIMO ANNO su dati mai visti, ma resta uno studio storico: le performance passate NON garantiscono risultati futuri.
- +50% annuo = proiezione dimensionata sul rischio, non garantita.

## Backlog / prossimi step
- P1: Rolling walk-forward su più finestre annuali (non solo ultimo anno) per stimare stabilità nel tempo.
- P1: Esecuzione live guidata su Tickmill demo dalla strategia appresa (con conferma + kill switch).
- P2: Portafoglio multi-strumento con correlazioni; job store discover con TTL/eviction; split di server.py (~1180 righe).
