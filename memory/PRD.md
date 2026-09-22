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

## P&L live, dettaglio conto e orari intraday batch (2026-09-22)
Tre miglioramenti (verificati curl + screenshot):
1. **P&L Live Conto**: header mostra il P&L aperto reale accanto all'equity (es. "€9.999,22 -€0,78 REALE"), aggiornato ogni 6s via polling `/api/bot`. Se MetaApi non fornisce `profit`, si calcola come equity−balance.
2. **Dettaglio Conto**: clic sull'equity apre un pannello (`account-detail-panel`) con Saldo, Equity, P&L aperto, Margine libero, Margine usato, Leva (1:30), Valuta (EUR). `get_account_info()` espone anche `margin`; chiusura al clic esterno.
3. **Precisione su Tutti**: pulsante "Calcola tutti gli orari" (solo D1) avvia `POST /api/forwardtest/intraday_all` (job asincrono, Semaphore(4), H1 per trade in parallelo) e popola l'ora esatta SL/TP di TUTTI i trade in un colpo (~12s per 18 trade). `_intraday_hit()` helper condiviso col singolo endpoint. Frontend fa polling ogni 2s con progresso "Calcolo X/Y".

## Equity reale nell'header (2026-09-22)
Richiesta: sostituire il saldo demo fisso ($175k) con l'equity vera del conto MetaApi.
- `metaapi_service.get_account_info()`: legge balance/equity/currency/margin/leverage/profit via RPC `get_account_information()` (cache 8s).
- `/api/bot`: se il broker è connesso, sovrascrive l'account con equity/balance/valuta reali e flag `real:true`.
- Header: mostra l'equity reale con simbolo valuta (es. €9.999,15) e badge verde **REALE** (icona verde); fallback badge **DEMO** ambra se il broker non è connesso.
- Verificato: conto demo €10.000, equity €9.999,15 EUR, leva 30.

## Miglioramenti verifica trade (2026-09-22)
Quattro migliorie richieste dall'utente, implementate e verificate (curl + screenshot):
1. **Precisione Intraday**: endpoint `POST /api/forwardtest/intraday` scarica le candele H1 nel/i giorno/i del trade e trova l'ORA ESATTA del primo tocco SL/TP (es. SL toccato alle 15:00 del 16/07). `metaapi_service.fetch_candles_before()` per il fetch su intervallo. Frontend: pulsante orologio "intraday" per riga che mostra "·HH:MM TP/SL" (o "SL/TP?" se ambiguo nella stessa candela).
2. **Nessun Prezzo Finto**: durante il warm-up della connessione (broker configurato ma prezzi non ancora pronti) watchlist e ticker mostrano "connessione…" invece di valori simulati. `metaapi_service` traccia `_real_symbols`; symbol source ∈ {real, simulated, warming}. Simboli mai reali (BTC/ETH su Tickmill demo) mostrano badge "SIM".
3. **Link MT5**: pulsante copia per riga → copia "SYMBOL YYYY-MM-DD" negli appunti per incollarlo in MT5.
4. **Colonna Durata**: `duration_days` per trade (giorni tra entrata e uscita), nuova colonna "Durata" (es. 6g, 14g).

## Correzione orari trade su D1 (2026-09-22)
Problema riportato: "gli orari dei trade non tornano, a quell'ora il prezzo non era a quel valore".
Causa: su timeframe giornaliero (D1) mostravamo `entry_time`/`exit_time` = timestamp di APERTURA della candela (ora broker es. 21:00/22:00 UTC), ma:
- l'ENTRATA avviene al CLOSE della candela (~24h dopo l'apertura mostrata);
- l'USCITA SL/TP viene toccata in un momento qualsiasi INTRADAY, non all'apertura.
Fix (verificato curl + screenshot):
- `run_forward_test`: `_bar_close_time(i)` = apertura della candela successiva (= istante reale del close). `entry_time` ora = close time (verificato: segnale 14/07 → entrata 15/07). Flag `entry_at_close` e `intrabar` sui trade.
- Frontend `ForwardTest.jsx`: su D1 mostra SOLO la data con etichette "·chiusura" (entrata) e "·intraday" (uscita) + nota esplicativa e footer "confronta date/prezzi nel tuo MT5".
Nota: la finestra "a freddo" dopo un reload backend mostra prezzi simulati per ~20s finché `warm_up` non completa (solo in dev/hot-reload).

## Prezzi live/candele REALI ovunque (2026-09-22)
Problema riportato: "i dati non coincidono, e neanche il prezzo attuale".
Causa: watchlist/ticker, grafico dashboard e analisi AI usavano ancora `generate_candles()` (tutto simulato, base fissa es. 1.0850) — solo forward-test/scoperta erano reali.
Fix (verificati via curl + screenshot):
- `metaapi_service.get_prices()`: prezzi live bid/ask via RPC `get_symbol_price` (cache 6s, timeout 3s/simbolo, paralleli). `get_daily_refs()`: chiusura D1 precedente per il change% (parallelo, cache 300s, lock anti-stacking). `cached_daily_refs()` non bloccante.
- `warm_up()` all'avvio riscalda connessione + cache prezzi/refs → primo caricamento veloce.
- `/api/market/watchlist`: prezzi reali + change%, con badge `source` per simbolo; non blocca sui refs (li popola in background).
- `/api/market/candles` e `/api/ai/analysis`: usano `_get_candles()` → candele reali MetaApi (fallback simulato marcato).
- Steady-state watchlist ~3s/poll. BTC/USDT ed ETH/USDT non esistono su Tickmill demo → restano `simulated` (marcati).
- Valori reali confermati (22/09/2026): EUR/USD ~1.1458, XAU/USD ~4312, US30 ~52040, NVDA ~227, AAPL ~339.

## Fix prezzi simulati (2026-09-22)
Problema riportato: i prezzi dei trade non combaciavano con i dati reali.
Causa: **fallback silenzioso a dati simulati** su connessione MetaApi "a freddo" (dopo un restart del backend il primo fetch andava in timeout → `generate_candles` con base fissa 1.0850 e timestamp `now()`, prezzi finti).
Fix:
- `metaapi_service.warm_up()` chiamata all'avvio (`startup`) stabilisce subito la connessione RPC → il primo fetch è già reale (verificato: forward-test D1 subito dopo restart = `source: real`).
- La scoperta ora include `replay`: il replay ESATTO degli ultimi 12 mesi su dati reali (candele+trade+equity) dimensionato al rischio consigliato. Il pulsante "Applica e riproduci l'ultimo anno" usa questi dati embedded → i prezzi combaciano al 100% con la finestra validata (niente seconda fetch con finestra diversa).
- Avviso rosso `discover-simulated-warning` in UI quando `source != 'real'`.
Nota: le candele D1 Tickmill aprono all'orario server broker (~22:00 UTC = mezzanotte GMT+2/+3): confrontare in MT5 con lo stesso fuso.

## Backlog / prossimi step
- P1: Rolling walk-forward su più finestre annuali (non solo ultimo anno) per stimare stabilità nel tempo.
- P1: Esecuzione live guidata su Tickmill demo dalla strategia appresa (con conferma + kill switch).
- P2: Portafoglio multi-strumento con correlazioni; job store discover con TTL/eviction; split di server.py (~1180 righe).
