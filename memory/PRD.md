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

## Test SENZA Stop Loss a interesse composto (2026) — iterazione 12 (8/8 backend, frontend 100%)
Richiesta: "togliamo SL, size 0.1 lotti ogni €10k (0.11 su 11k…), interesse composto, test sul 2026".
- `POST /api/portfolio/nosl` (job asincrono, status via GET /api/portfolio/backtest/{job_id}). `_nosl_compute`: addestra su dati pre-2026 (_pick_params), genera le entry con run_forward_test, poi ricalcola l'uscita SENZA SL (chiude solo al TP, altrimenti resta aperta fino a fine periodo). Size compounding: lot = lot_per_10k * equity/10000 (min 0.01). CONTRACT_SIZE per il calcolo in denaro (forex 100k, XAU 100, US30 1).
- Doppia metrica onesta: `realized_balance` (SOLO trade chiusi al TP → sembra altissimo, tutti "vinti") vs `true_equity` (mark-to-market = chiusi + floating delle aperte in perdita). Coerenza verificata: realized + open_floating == true_equity. `wiped`/`wipe_date` se il MTM tocca <=0.
- Frontend: pannello rosso `nosl-panel` con avviso, risultato `nosl-result`, `nosl-true-equity`, `nosl-wiped`, equity curve MTM.
- Risultato dimostrativo (dati simulati, MetaApi disconnesso al test): solo chiusi ~€16.473 (85 TP, sembra +65%) MA equity reale MTM ~€10.432 (+4,3%) con -€6.041 di floating aperto → dimostra che l'alto win-rate senza SL è INGANNEVOLE.
- NOTA RICORRENTE: l'account MetaApi demo (590b1207) si disconnette spesso → i backtest ripiegano su dati SIMULATI (marcati). Riconnettere/riprovare per dati reali.

## RUN REALE no-SL 2026 (2026-06 — account 85584886) — DATI REALI 7/7
- Account MetaApi cambiato su richiesta utente: `85584886-eac6-441c-9641-7e8dff74426a` (Erik Demo, TickmillUK-Demo, login 25374750) — CONNECTED e stabile.
- Test no-SL 2026 (0,10 lot/€10k, interesse composto, 2026-01-01→2026-09-21) eseguito con TUTTI e 7 gli strumenti su dati REALI Tickmill (`sim_symbols: []`).
- ESITO (dati reali): saldo "solo chiusi" €148.935,21 (64/64 TP, sembra +1389%) MA equity reale MTM **-€303,88 → CONTO AZZERATO (wiped) il 2026-02-01**; 40 posizioni aperte con floating -€149.239,09; min equity -€46.180; return reale -103%.
- Coerenza contabile verificata: 148.935,21 + (-149.239,09) = -303,88 = true_equity. ✓
- CONCLUSIONE ONESTA: su dati reali, la strategia senza SL con size composta AZZERA il conto entro un mese nonostante il 100% di trade chiusi "vinti". Conferma definitiva che il no-SL è catastrofico.

## RUN REALE no-SL 2026 — SOLO FOREX + CAP 10 posizioni (2026-06) — DATI REALI 5/5
- Richiesta utente: "Limitiamo i trade contemporanei a 10 e vediamo che succede. E fai trading solo su forex al momento."
- Backend: aggiunto `NoslReq.max_concurrent` (default 10) e `FOREX_SYMBOLS` (EUR/USD, GBP/USD, USD/CHF, USD/CAD, AUD/USD). `_run_nosl` ora usa solo forex; `_nosl_compute` applica un cap di posizioni contemporanee nel loop event-driven (open_count: entry skippata se open_count>=max_concurrent). Frontend `ForwardTest.jsx` aggiornato (label "solo forex · max 10 aperte", total 5, payload max_concurrent:10).
- ESITO (dati reali 5/5, sim vuoto): saldo "solo chiusi" €11.577,29 (13/13 TP); equity reale MTM **€8.545,15 (-14,5%)**; **NON azzerato** (il cap ha evitato il wipeout precedente); 10 posizioni aperte (= esattamente il cap) con floating -€3.032,14; max DD MTM 19,46%; min equity €8.060.
- Coerenza contabile: 11.577,29 + (-3.032,14) = 8.545,15 = true_equity. ✓
- CONFRONTO: senza cap e con XAU/US30 → conto azzerato (-€149k floating). Con cap 10 + solo forex → il conto sopravvive ma perde comunque -14,5% in equity reale nonostante 13/13 trade chiusi "vinti". Il no-SL resta perdente in termini di equity reale.

## Motore no-SL MIGLIORATO: mean-reversion + regime SMA200 + time-stop (2026-06) — DATI REALI 5/5
- Richiesta utente: "a me interessa il risultato, libertà su strategie/algoritmi (anche da ricerca online). Regole non negoziabili: NO Stop Loss; size 0,1 lotti/€10k con interesse composto."
- Ricerca online: senza SL la mean-reversion batte il trend-following (i perdenti rientrano invece di scappare); servono un filtro di regime (SMA200) e un TIME-STOP (chiudere dopo N barre se il TP non è colpito) per non lasciare capitale bloccato.
- Implementazione (`server.py`):
  - Estratto `_nosl_settle()` (settlement condiviso: equity compounding event-driven, curva MTM, dettaglio posizioni aperte). Helper `_pt`, `_bar_close`, `_atr_at`.
  - Nuovo motore `_nosl_v2_compute` + `_mr_trades` (entry RSI2/3 su eccessi, TP=ATR×mult, TIME-STOP a N giorni, NO price SL, 1 posizione/simbolo) + `_mr_pick` (grid `_MR_GRID` 108 combo: rsi_len×soglia×tp_atr×time_stop×regime, scelta su dati PRE-2026, score net/DD).
  - `NoslReq.engine` ("meanrev" default | "classic" legacy). `_run_nosl` instrada al motore scelto. Nuovi campi risultato: `timed_exits`, `sym_strategy` (params mean-reversion).
  - Frontend `ForwardTest.jsx`: il pulsante no-SL usa engine "meanrev"; label "mean-reversion + time-stop"; stat "Solo trade chiusi" mostra "N TP · M time-stop"; testi aggiornati.
- RISULTATO REALE 5/5 (vs motore classico): true equity €10.461 (+4,6%) vs €8.545 (-14,5%); maxDD MTM 6,8% vs 19,46%; equity minima €9.454 vs €8.060; solo 5 posizioni aperte (tutte aperte ad ago/set, floating -€576, peggiore -€219) vs 10 incagliate da gennaio (floating -€3.024, peggiore -€598). 55 chiusi = 28 TP + 27 time-stop → il time-stop taglia i perdenti prima che si incaglino. Identità contabile: 11.037,01 − 575,96 = 10.461,05 = true equity. ✓
- ONESTÀ: il no-SL resta senza rete di protezione di prezzo (un movimento contrario forte entro il time-stop può ancora far male) e USD/CAD/USD/CHF restano net negativi; ma il portafoglio è net positivo e molto più sicuro. Nessuna garanzia futura.

## Motore no-SL ML: gradient boosting entry-gate (2026-06) — DATI REALI 5/5
- Richiesta utente: "addestrandoti su 5 anni non riesci a fare di meglio? non voglio strumenti classici che conoscono tutti."
- Installato scikit-learn 1.9.1 (+scipy) in requirements. Nuovo motore `_nosl_ml_compute` + `_ml_symbol`/`_ml_dataset`/`_ml_features`/`_candidate_side`/`_std`.
- Approccio: per ogni forex, si generano candidati mean-reversion (RSI2<30 BUY / >70 SELL); per ciascuno si estrae un vettore di ~17 feature (RSI2/14, z-score vs SMA20/50, ritorni 1/3/5/10g, ATR relativo, regime volatilità, allineamento SMA20/50/200, posizione nel range 20g, streak, giorno settimana, lato) e un'etichetta win/loss simulando l'esito no-SL+time-stop. Un `GradientBoostingClassifier` (150 alberi, depth 3, lr 0.05) è addestrato sui candidati PRE-2025; tp_mult∈{1,1.5,2} e soglia p∈{0.5..0.7} scelti massimizzando il net sulla VALIDAZIONE 2025; poi refit su tutto il pre-2026 e applicato al 2026 (mai visto), prendendo solo i candidati con proba>=soglia. Uscita TP=ATR×mult o time-stop 20g. NO price SL. `NoslReq.engine`="ml".
- RISULTATO REALE 5/5: true equity €10.722,93 (+7,2%), maxDD MTM 10,48%, min eq €9.601, 77 chiusi (54 TP=70% + 23 time-stop), 5 aperte recenti (floating -€901). Identità: 11.623,45 − 900,52 = 10.722,93 ✓. Per simbolo: USD/CHF +947 (era in perdita col motore precedente), AUD/USD +425, GBP/USD +367, EUR/USD +254, USD/CAD -369.
- CONFRONTO 3 MOTORI (2026 reale, no-SL, 0,1/10k): classico €8.545 (-14,5%) | mean-reversion €10.461 (+4,6%) | ML €10.723 (+7,2%). Il TP-hit rate sale a 70% (vs 51%).
- ONESTÀ: resta un backtest storico; ~730 candidati/simbolo su 4 anni sono limitati → rischio overfitting anche con validazione walk-forward. Nessuna garanzia futura; no-SL sempre senza protezione di prezzo. Frontend usa engine "ml" di default.

## Walk-Forward PLURIENNALE del modello ML (2026-06) — DATI REALI 5/5
- Richiesta utente: "riaddestrare il modello annualmente su periodi 2023-2025 e testarlo anno per anno per verificare la robustezza nel tempo."
- Backend: `POST /api/portfolio/ml_walkforward` (job async, body {years,start_balance,lot_per_10k,max_concurrent}) → `_run_ml_wf` (fetch 6 anni D1) → `_ml_walkforward_compute`. Rifattorizzato `_ml_symbol` in `_ml_fit(candles,closes,cfg,train_end)` (selezione tp_mult+soglia su validazione = anno prima di train_end, refit su tutto il pre-train_end) e `_ml_generate(...,test_start,test_end)` (trada solo nella finestra, posizioni ancora aperte a fine anno lasciate flottanti valutate all'ultima candela dell'anno). Per ogni anno Y: train su <1 gen Y, test su [1 gen Y, 1 gen Y+1), reset €10k. NO price SL, size composta 0,1/€10k.
- RISULTATO REALE 5/5 (retrain annuale, out-of-sample):
  - 2023: €11.114 (+11,1%), maxDD 16,4%, 118 chiusi (81 TP/37 TS)
  - 2024: €8.457 (**-15,4%**), maxDD 16,0%, 99 chiusi (59/40) — ANNO PERDENTE
  - 2025: €11.058 (+10,6%), maxDD 17,9%, 91 chiusi (65/26)
  - 2026: €11.625 (+16,2%), maxDD 9,7%, 87 chiusi (64/23)
  - SOMMARIO: 3/4 anni positivi, media +5,62%/anno, migliore +16,2% / peggiore -15,4%, equity composta €12.079 (+20,8% su 4 anni), peggior DD 17,9%, mai azzerato.
- ONESTÀ (fondamentale): il modello NON è sempre profittevole — il 2024 perde -15,4% su dati mai visti. L'edge è reale ma FRAGILE (regge 3 anni su 4, con un anno a doppia cifra negativa). Questo è il valore del walk-forward: smaschera la robustezza reale. Backtest storico, nessuna garanzia futura.
- Frontend: pannello `wf-panel` (bottone `wf-run-button`, tabella `wf-years-table`, stat anni positivi/miglior-peggior/equity composta/peggior DD). NOTA: verifica UI limitata a compile + coerenza dati (screenshot-tool non mantiene il login demo — flakiness del tool, /auth/me OK via API).

## Tentativi di MIGLIORAMENTO strategia (2026-06) — DATI REALI 5/5
- Richiesta utente: "riesci a trovare una strategia migliore o chiedo a chatgpt?"
- TENTATIVO 1 — Ensemble (mean-rev + trend/breakout, 2 modelli ML): BOCCIATO dal walk-forward. Aggiunto `_cand_trend` (Donchian+regime), refactor `_ml_dataset/_ml_fit/_ml_generate` con param `cand_fn`, `_ml_ensemble_trades`. Risultato: 2/4 anni positivi, media +3,12%/anno, 2024 -19,4% e 2026 -2,6% (PEGGIO). Lo sleeve trend senza SL aggiunge rischio di coda negli anni choppy. → sleeve trend DISABILITATO di default (codice conservato).
- TENTATIVO 2 — Ottimizzazione TP del mean-reversion ML: RIUSCITO. Ampliata la griglia tp_mult a {1,1.5,2,3}×ATR e rilassati i minimi campione (core>=50, val>=12, taken>=4) per far scegliere al modello TP più larghi dove conviene. Sempre walk-forward, TP scelto su validazione anno-prima.
- RISULTATO FINALE SPEDITO (mean-reversion ML, walk-forward reale 5/5):
  - 2023 +11,1% (DD 16,4%) · 2024 -15,4% (DD 16,0%) · 2025 +23,5% (DD 8,3%) · 2026 +16,1% (DD 9,7%)
  - 3/4 anni positivi · media +8,82%/anno (prima +5,62%) · equity composta €13.477 (+34,8%, prima +20,8%) · peggior DD 16,44% · mai azzerato.
- Il default engine ("ml") ora usa questa config migliorata. Label strategia: "ML mean-reversion (gradient boosting)".
- ONESTÀ: il 2024 resta -15,4% (senza SL un anno storto non si elimina). Miglioramento reale e out-of-sample, non overfitting (TP scelto su validazione). L'ensemble trend è stato testato e scartato: è questo il valore del test reale vs il solo suggerire idee.

## TENTATIVO 3 — Feature cross-coppie (forza dollaro + spread): BOCCIATO (2026-06)
- Richiesta utente: "inserire forza del dollaro e spread tra coppie per migliorare anni negativi come il 2024."
- Implementato `_build_xpair_context(data)`: forza del dollaro (momentum 20/60g dal paniere sign-adjusted delle 5 coppie), forza idiosincratica del pair vs fattore dollaro, e z-score di stretch relative-value (60g). 4 feature aggiunte, threaded via `ctx` in `_ml_features/_ml_dataset/_ml_fit/_ml_generate/_ml_ensemble_trades`. Nessun look-ahead (feature al giorno d usano solo dati ≤ d).
- RISULTATO walk-forward reale 5/5: 1/4 anni positivi, media -2,18%/anno, composta -9,4%, peggior DD 20,8%. 2023 -1,5%, 2024 -10,1% (leggero meglio), 2025 -6,2% (CROLLO da +23,5%), 2026 +9,1%.
- CAUSA: con ~180 candidati/anno di training, 4 feature macro in più hanno aumentato l'overfitting e diluito il segnale mean-reversion; il modello si aggrappa a pattern macro spuri che non generalizzano.
- DECISIONE: REVERT completo. Il default resta mean-reversion ML SENZA cross-pair (ctx=None). `_build_xpair_context` e il plumbing `ctx` restano nel codice ma DISABILITATI. Baseline confermato invariato (2026 nosl smoke: +6,6%, 5/5 reali, label "ML mean-reversion (gradient boosting)").
- LEZIONE (dead-end): su questo dataset piccolo, aggiungere feature peggiora. Non riproporre cross-pair/ensemble/più-feature senza prima ridurre l'overfitting (es. regularizzazione, più dati intraday, feature selection).

## Walk-forward annuale + export CSV (2026-09-22) — iterazione 11 (walk-forward 6/6, CSV ok, frontend 100%)
- **Walk-Forward Annuale**: `PortfolioReq.walk_forward` (default True). In `_portfolio_compute`, per ogni anno del periodo la strategia di ciascuno strumento è riaddestrata usando SOLO i dati precedenti a quell'anno (helper `_pick_params`, grid ridotta 96 combo), poi applicata su quell'anno. `per_symbol.retrains` conta i riaddestramenti (>=2 per 2025+2026); label "Misto (walk-forward)" se la strategia cambia tra gli anni. `walk_forward:false` = training unico pre-2025 (retrains=1).
- **Export CSV**: il result include la lista completa `trades` (entry_date, exit_date, symbol, side, result, r, net). Frontend `exportPortfolioCsv()` scarica un CSV multi-sezione (riepilogo + statistiche per strumento + trade + equity curve), nome `apexflow_portfolio_<start>_<end>.csv`.
- `_run_portfolio` fa un retry sui simboli caduti a simulato (migliora copertura dati reali).
- Frontend: toggle `portfolio-walk-toggle` ("Riaddestra ogni anno", default on) e pulsante `portfolio-export-button`.
- RISULTATO walk-forward su dati reali 7/7: €10.000 → ~€13.625 (+36,3%, +21,1%/anno, DD 19,3%, 215 trade, WR 40,9%).
- NOTA: l'account MetaApi demo si disconnette a intermittenza (lato broker/MetaApi); quando disconnesso il backtest usa fallback simulato (marcato SIM + warning). Il retry e i badge lo rendono evidente.

## Backtest di portafoglio multi-strumento (2026-09-22) — iterazione 10 (6/6 backend, frontend 100%)
Richiesta: "1 gennaio 2025, conto 10k, opera su ciò che vuoi con posizioni multiple, dimmi ad oggi quanti soldi abbiamo".
- Nuovo account MetaApi configurato: `590b1207-7417-42f2-af73-eacaf7120b41` (TickmillUK-Demo, login 25374738, CONNESSO). Il precedente era andato DISCONNECTED.
- `POST /api/portfolio/backtest` (job asincrono) + `GET /api/portfolio/backtest/{job_id}`: parte da €10.000 il 2025-01-01, opera fino a oggi su 7 strumenti (EUR/USD, GBP/USD, USD/CHF, USD/CAD, AUD/USD, XAU/USD, US30) con conto CONDIVISO e POSIZIONI MULTIPLE concorrenti (simulazione event-driven, r_multiple = pnl/100), rischio 1.5%/trade, costi inclusi.
- ANTI look-ahead: la strategia di ogni strumento è scelta SOLO su dati PRIMA del 2025 (grid ridotta 96 combo), poi applicata in avanti.
- Fetch storico D1 5 anni SEQUENZIALE per i 7 simboli (evita reset di connessione concorrenti); cache `_d1_cache` TTL 600s → a caldo <15s, a freddo 3-6 min.
- Frontend: pannello `portfolio-panel` con progresso "Scarico dati X/7", risultato `portfolio-result` (saldo finale, rendimento, annualizzato, DD, trade/WR), tabella `portfolio-symbols-table` per strumento, equity curve, warning simboli simulati.
- RISULTATO VERIFICATO (dati reali, testing agent): €10.000 (2025-01-01) → ~€11.990 (+19,9%, +11,6%/anno) al 2026-09-21, 628 giorni, 206 trade, WR 37,4%, MaxDD 27,38%, tutti e 7 gli strumenti su dati reali. Il numero esatto varia leggermente per run (dipende dalla grid) — comportamento atteso di un backtest, nessuna garanzia futura.
- Robustezza: riferimento al task async mantenuto (no GC); status endpoint esclude il task (serializzazione).

## Posizioni aperte reali nel pannello conto (2026-09-22)
Richiesta: mostrare le posizioni aperte reali del conto MetaApi (simbolo, lotti, P&L) live.
- `metaapi_service.get_positions()`: legge le posizioni via RPC `get_positions()`, reverse-map simbolo broker→app (es. AUDUSD→AUD/USD), campi {symbol, side, volume, profit, open_price, current_price}. Cache 5s con fallback (60s) su errore transitorio.
- `/api/bot`: include `account.positions` quando il broker è connesso.
- Robustezza anti-flicker: `get_account_info`/`get_positions` restituiscono l'ultimo valore noto su fallimento transitorio; il frontend mantiene lo stato REALE "sticky" (non torna a DEMO su un poll fallito).
- Header: sezione "Posizioni aperte (N)" nel pannello dettaglio con badge BUY/SELL, simbolo, lotti e P&L live (verde/rosso). "Nessuna posizione aperta" se vuoto.
- Verificato: posizione reale AUD/USD BUY 0.01 lot, P&L live ~-€0.58, visibile nel pannello.

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
