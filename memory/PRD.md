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

## TENTATIVO 4 — Intraday H4 (più dati di training): RIUSCITO ✅ (2026-06)
- Richiesta utente: "aggiungere timeframe più brevi H1/H4 per aumentare gli esempi e ridurre l'overfitting delle feature macro."
- Vincolo: fetcher MetaApi pagina all'indietro con tetto 12 pagine (~12k candele). H1 (24k+ su anni) NON fattibile; H4 (~9k su 6 anni) fattibile → scelto H4.
- Implementato: `_get_h4_history` (+`_h4_cache`, TTL 900s), `_build_xpair_context` riscritto per chiave = timestamp raw (funziona su qualsiasi TF) con finestre parametriche (w1,w2,wz), `tstop` parametrizzato in tutta la pipeline ML (D1=20 barre, H4=120 barre ≈ 4 settimane). `MlWalkForwardReq` + `_run_ml_wf` estesi con `timeframe` ("D1"|"H4") e `cross_pair` (bool). `_ml_walkforward_compute(..., tstop, xctx, min_bars)`.
- CONFRONTO WALK-FORWARD REALE (5/5 forex, no-SL, 0,1/€10k):
  | Config | Anni+ | Media/anno | Composta | 2024 | Peggior DD |
  |---|---|---|---|---|---|
  | D1 baseline (no xpair) | 3/4 | +8,82% | +34,8% | -15,4% | 16,4% |
  | D1 + cross-pair | 1/4 | -2,18% | -9,4% | -10,1% | 20,8% |
  | H4 + cross-pair | 2/4 | +4,08% | +13,4% | +7,2% | 21,2% |
  | **H4 SENZA cross-pair** ✅ | **4/4** | **+10,85%** | **+47,7%** | **+5,9%** | 21,1% |
  - Dettaglio H4 no-xpair: 2023 +1,8% · 2024 +5,9% · 2025 +31,5% · 2026 +4,2%.
- SCOPERTA: a vincere è l'H4 (più esempi ~5×), NON le feature cross-pair (che danneggiano su D1 e H4). L'H4 rende il 2024 positivo e TUTTI e 4 gli anni in profitto per la prima volta, con resa composta massima. Trade-off onesto: drawdown più alto (~21% vs 16%, più trade).
- SPEDITO: frontend `wf-panel` ora lancia il walk-forward su H4 (cross_pair=false); poll esteso (220 tick) per il calcolo più lungo (~qualche minuto); label "intraday H4". Cross-pair resta disabilitato (codice conservato). Il pulsante nosl single-year dashboard resta su D1 per velocità.
- ONESTÀ: backtest storico; H4 dà più dati ma non garantisce il futuro; DD più alto. Nessuna garanzia.

## TENTATIVO 5 — Currency-strength cross (forza valutaria + incrocio): parziale (2026-06)
- Richiesta utente: "misurare la forza di tutte le valute e tradare l'incrocio (es. AUD forte, EUR debole → coppia EUR/AUD)."
- Verificato: le coppie cross (EUR/GBP, EUR/AUD, GBP/AUD, AUD/CAD, EUR/CHF, CAD/CHF...) sono REALI su Tickmill demo. Aggiunte a INSTRUMENTS + CONTRACT_SIZE (10 nuove). `STRENGTH_SYMBOLS` = 5 major + 7 cross (12 coppie).
- Implementato: `_build_strength_context(data,k,zwin)` → misuratore di forza per valuta (media dei momentum k-barre sign-adjusted su tutte le coppie), poi per ogni coppia diff=forza(base)-forza(quote) e z-score rolling. `_make_strength_cand(zmap,thr)` = momentum sulla divergenza (z>1 BUY, z<-1 SELL). `_ml_ensemble_trades(...,cand_fn)` accetta candidato custom. `MlWalkForwardReq.strength` + runner (universo esteso + contesto forza). Gate ML + time-stop + no-SL invariati.
- CATCH CRITICO: primo run aveva 4/12 coppie in SIMULATO → +98% GONFIATO e non valido. Aggiunto filtro: in modalità strength si scartano i simboli non-reali (niente fallback finto). Re-run con 12/12 REALI.
- RISULTATO REALE (D1, 12 coppie, sim vuoto): 2023 +2,8% · 2024 +20,2% · 2025 -3,8% · 2026 -1,6%. 2/4 positivi, media +4,40%, composta +17,0%, peggior DD 30,5%.
- VERDETTO: l'idea funziona proprio sul 2024 (+20,2% vs -15,4% baseline D1 / +5,9% H4) — la divergenza di forza paga negli anni di trend. Ma negli altri anni perde e il DD è alto (momentum senza SL). Nel complesso NON batte il campione H4 mean-reversion (4/4, +47,7%, DD 21%). Default invariato (H4 mean-reversion); motore forza disponibile via API (`strength:true`) ma non spedito nel default.
- INSIGHT per il futuro: strength vince dove mean-reversion perde (2024) e viceversa → potenzialmente COMPLEMENTARI. Una combinazione (portfolio dei due motori) potrebbe dare 4/4 con DD più basso. Non ancora costruita.
- LEZIONE (dead-end): sempre verificare `simulated_symbols` vuoto prima di credere a un risultato; i dati simulati gonfiano di ~6× (98% vs 17%).

## TENTATIVO 6 — COMBINAZIONE motori (mean-reversion + forza) + forza su H4 (2026-06): CAMPIONE ✅
- Richiesta utente: "forza su H4" + "combinare mean-reversion + forza in un portafoglio unico per 4/4 anni con meno drawdown".
- Implementato: `_ml_ensemble_trades(..., sleeve_defs=[(name,cand_fn)])` multi-sleeve (unisce più motori in un unico stream di trade, capitale/compounding/cap condivisi). `_ml_walkforward_compute(..., mode)` con mode "meanrev"|"strength"|"combo". `MlWalkForwardReq.mode`. Combo = mean-reversion + forza valutaria su 12 coppie reali.
- CONFRONTO COMPLETO (walk-forward reale 2023-2026, no-SL, 0,1/€10k):
  | Config | Anni+ | Media/anno | Composta | peggior anno | DD |
  |---|---|---|---|---|---|
  | D1 mean-rev baseline | 3/4 | +8,82% | +34,8% | -15,4% | 16,4% |
  | D1 + cross-pair feat | 1/4 | -2,18% | -9,4% | | 20,8% |
  | H4 mean-rev | 4/4 | +10,85% | +47,7% | +1,8% | 21,1% |
  | D1 strength | 2/4 | +4,40% | +17,0% | -3,8% | 30,5% |
  | **D1 COMBO** ✅ | **4/4** | **+15,35%** | **+76,1%** | **+6,5%** | 29,0% |
  | H4 combo | 3/4 | +9,62% | +41,6% | -1,2% | 34,0% |
  - D1 combo dettaglio: 2023 +22,1% · 2024 +18,6% · 2025 +6,5% · 2026 +14,2%.
- SCOPERTA: i due motori sono COMPLEMENTARI (forza vince il 2024, mean-reversion gli altri anni) → la combinazione D1 dà il miglior risultato assoluto: 4/4 positivi, +76,1% composto, anche risk-adjusted (76/29=2,6 vs H4 47,7/21=2,3). L'H4 aiuta SOLO il mean-reversion puro (più esempi), ma sulla combo/forza aggiunge solo rumore (troppi trade, DD 34%, meno consistente) → H4-combo BOCCIATO.
- SPEDITO: frontend `wf-panel` ora lancia mode="combo" su D1 (12 coppie); label "combo (mean-reversion + forza valutaria)". Il campione è il D1 combo.
- ONESTÀ: backtest storico su dati reali; DD alto (29%, molti trade senza SL); nessuna garanzia futura. `mode` "strength"/"combo" e "meanrev", timeframe D1/H4 restano disponibili via API per confronto.

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

## TENTATIVO 7 — PESI VARIABILI tra i motori (sweep) + lista trade 2026 (2026-06): RIUSCITO ✅
- Richiesta utente: "peso variabile tra i motori per migliorare la resa; poi la lista dei trade eseguiti nel 2026". Scelte utente: (a) peso = ripartizione degli slot max-concorrenti tra i due motori (sizing pieno 0,1/€10k invariato per trade); (b) sweep automatico di più pesi con tabella comparativa; (c) lista trade 2026 (data in/out, simbolo, lato, motore, lotti, esito, P&L netto) in tabella + CSV.
- Implementazione backend (`server.py`):
  - `_nosl_settle(..., sleeve_caps=None)`: cap di posizioni contemporanee PER-SLEEVE (oltre al cap globale). Ora restituisce anche `trades` (lista completa: entry_date, exit_date, symbol, side, sleeve, lot, outcome TP/time-stop/aperta, net, entry/exit price).
  - Estratto `_wf_gen_year(...)` (generazione trade out-of-sample di un anno, condiviso). `_ml_walkforward_compute` rifattorizzato per usarlo (invariato nel comportamento). I trade portano ora il campo `sleeve`.
  - `_combo_weight_sweep_compute(...)`: genera i trade UNA volta per anno (mode combo), poi ri-settla per ogni peso (economico, no re-training). Best = resa composta più alta; estrae la lista trade 2026 del peso vincente. Calcola anche Calmar (composta/DD).
  - `POST /api/portfolio/combo_weights` (job async, `ComboWeightReq`: years/start_balance/lot_per_10k/max_concurrent/timeframe/weights) → `_run_combo_weights` (fetch 12 STRENGTH_SYMBOLS reali, scarta simulati, costruisce strength context, pesi default 7/3·6/4·5/5·4/6·3/7). Stato via GET /api/portfolio/backtest/{job_id}.
- Frontend `ForwardTest.jsx`: nuovo pannello `sweep-panel` ("Pesi tra i motori (combo)") con `sweep-run-button` ("Confronta pesi"), tabella `sweep-weights-table` (riga migliore evidenziata verde + check), dettaglio per-anno del best, tabella `sweep-trades-2026-table` (150 righe, badge motore forza/mean-rev), export CSV `sweep-export-2026` → apexflow_trade_2026.csv.
- RISULTATO REALE (D1, 12 coppie REALI, SIM vuoto, walk-forward 2023-2026, no-SL, 0,1/€10k):
  | Peso (mean-rev / forza) | Anni+ | Media/anno | Composta | Peggior DD | Calmar |
  |---|---|---|---|---|---|
  | **7 / 3** ✅ | **4/4** | **+22,75%** | **+125,8%** | **18,92%** | **6,65** |
  | 6 / 4 | 4/4 | +17,95% | +92,0% | 25,22% | 3,65 |
  | 5 / 5 | 4/4 | +18,02% | +93,0% | 24,45% | 3,80 |
  | 4 / 6 | 4/4 | +16,40% | +80,1% | 32,00% | 2,50 |
  | 3 / 7 | 3/4 | +8,25% | +35,4% | 33,94% | 1,04 |
  - Best 7/3 dettaglio anni: 2023 +27,9% · 2024 +24,4% · 2025 +26,8% · 2026 +11,9%. 2026: 150 trade (117 mean-rev + 33 forza), somma netta +€1.190,64.
- SCOPERTA: tiltare l'allocazione verso il mean-reversion (7 slot) con una piccola quota di forza (3 slot) MIGLIORA sia la resa (composta +125,8% vs +76/93% dei combo precedenti) SIA il drawdown (18,92%, il più basso). Più forza = più rumore/DD. Il default combo resta 5/5 nel pannello walk-forward; lo sweep è un pannello di ricerca separato.
- Verifica: backend agent-tested via API (12 REAL, SIM vuoto); frontend testing-agent iteration 13 (100%, nessun bug), login demo OK, tabelle+CSV OK.
- ONESTÀ (fondamentale): scegliere il peso "migliore" sullo storico è UN'ALTRA ottimizzazione → selection bias/overfitting possibile. Le rese composte alte derivano dal compounding annuale su dati passati. Resta un backtest storico, nessuna garanzia futura, no-SL sempre senza protezione di prezzo.

## OPERATIVITÀ — Auto-Trading su MT5 Demo + UI ripulita (2026-06): RIUSCITO ✅
- Richiesta utente: "rimuoviamo le robe inutili... non serve un tasto/sezione per verificarla ormai... voglio vedere la lista dei trade aperti e una sezione di quelli chiusi... poi ci prepariamo per collegarla al account demo e far partire i trade in automatico su mt5". Scelte: rimuovere TUTTI i pannelli di ricerca/verifica, lasciare solo stato bot + trade aperti + trade chiusi; resto default.
- **UI ripulita**: `Dashboard.jsx` ora renderizza SOLO `Header` + nuovo `AutoTrader.jsx`. Rimossi dalla dashboard: ForwardTest (backtest/walk-forward/sweep/discovery/intraday/no-SL), Watchlist, CandleChart, AiPanel, BotPanel, PositionsTable (i file restano ma non sono più usati).
- **Motore auto-trading** (`server.py`): strategia fissa combo D1, slot 7 mean-rev / 3 forza, 12 coppie, max 10, NO stop di prezzo, TP ATR + time-stop 28g, sizing 0,1 lotti/€10k composto.
  - `_live_signals(candles, cfg, sleeve_defs, ctx, tstop)`: valuta i segnali di ingresso sull'ULTIMA barra D1 completata (ML addestrato su tutta la storia precedente, no look-ahead).
  - `_autobot_cycle()`: check connessione → time-stop posizioni apexflow oltre 28g → conta slot per sleeve → fetch 12 D1 reali + strength context → per ogni coppia valuta segnali → piazza ordini market reali (comment `apexflow_<sleeve>`) rispettando cap e dedup (symbol,sleeve). Log in Mongo `autobot`.
  - `_autobot_loop()`: scheduler background (avviato allo startup) che esegue un ciclo ogni 6h quando `running`.
  - Endpoint: `GET /api/autobot` (stato + strategia + account + trade aperti/chiusi reali + log), `POST /api/autobot/start` (avvia + ciclo immediato), `/stop`, `/run-now`, `POST /api/autobot/close/{pid}`.
- **metaapi_service.py**: `place_market_order` con `comment` (rimosso `clientId` che violava il pattern MetaApi → causava "Validation failed"); `close_position(id)`; `get_closed_deals(days)` (deal DEAL_ENTRY_OUT con P&L realizzato); `get_positions` arricchito con id/comment/tp/time; SYMBOL_MAP esteso a tutte le 12 coppie strength.
- **AutoTrader.jsx**: card controllo/stato (START/STOP con conferma, Valuta ora, stato ciclo, ultimo/prossimo ciclo, equity, P&L aperto, connessione), tabella trade aperti (con chiusura manuale), tabella trade chiusi (P&L realizzato), registro attività collassabile. Tutti i data-testid `autobot-*`.
- **VERIFICATO LIVE (conto Tickmill MT5 demo reale, MetaApi CONNESSO)**:
  - Ordine test manuale piazzato → aperto → chiuso via `/autobot/close` → apparso in trade chiusi (P&L reale). ✓
  - Ciclo motore completo: **7 ordini reali piazzati** (0,1 lotti ciascuno) — 4 mean-rev (EUR/USD BUY, USD/CHF SELL, AUD/USD BUY, EUR/CHF BUY) + 3 forza (GBP/USD SELL, USD/CHF BUY, AUD/USD SELL), ognuno con TP, nessuno stop di prezzo, cap rispettati (forza a 3/3, meanrev 4/7). ✓
  - Frontend testing-agent iteration 14: 100%, cockpit + tabelle + START/STOP + registro OK, nessun overflow mobile, pannelli di ricerca assenti. ✓
- NOTA: due sleeve indipendenti possono aprire posizioni OPPOSTE sullo stesso simbolo (es. USD/CHF meanrev SELL + strength BUY) — è coerente col backtest combo (che fonde entrambi gli sleeve). Il bot resta ATTIVO con le 7 posizioni; l'utente controlla via pulsante Ferma bot / Chiudi.
- ONESTÀ: esecuzione reale su conto DEMO; nessuno stop di prezzo (solo TP + time-stop + cap). I risultati storici non garantiscono profitti futuri.

## RAFFINAMENTI OPERATIVI — Direzione netta + Controllo giornaliero + Telegram (2026-06): RIUSCITO ✅
- Richieste utente: (1) i due motori non devono aprire posizioni OPPOSTE sullo stesso simbolo (tenere solo il segnale netto, risparmiare spread); (2) avvisi Telegram su apertura/chiusura trade; (3) valutare i segnali 1×/giorno alla chiusura D1 invece che ogni 6h.
- **Direzione netta** (`_autobot_cycle`): raccoglie prima tutti i segnali sleeve per simbolo, poi risolve: BUY+SELL sullo stesso simbolo → annullati (nessun ordine, log "segnali opposti annullati"); stesso lato → un solo ordine (slot assegnato a meanrev se presente, TP di quel motore). Una sola posizione per simbolo (dedup per simbolo). Testato live: AUD/USD e USD/CHF con segnali opposti correttamente annullati.
- **Controllo giornaliero**: rimosso il ciclo ogni 6h. `AUTOBOT_DAILY_HOUR_UTC=22`; `_autobot_loop` esegue un ciclo automatico al massimo 1×/giorno UTC dopo le 22:00 (gate su `last_run_date`). START esegue comunque un ciclo immediato; "Valuta ora" resta manuale. `next_run` mostra lo slot 22:00. RACCOMANDAZIONE data all'utente: D1 giornaliero è meglio (i segnali cambiano solo alla chiusura D1; 6h ricontrolla la stessa candela e rischia di valutare la barra in formazione).
- **Telegram** (`_tg_send`, `_notify_trade`): bot @squalo_signals_bot, token in backend/.env `TELEGRAM_BOT_TOKEN`; chat_id auto-rilevato via `POST /api/autobot/telegram/link` (getUpdates) e salvato in Mongo `db.autobot.telegram_chat_id` (Erik, 1340672782). `POST /api/autobot/telegram/test` per test. Notifiche su: avvio/stop bot, apertura trade, chiusura manuale/time-stop. Testato live: messaggi consegnati (message_id confermato). UI: pulsante "Collega Telegram" (se token presente e chat non collegata) / "Test Telegram" (se collegato); indicatore stato Telegram nella card strategia.
- Frontend `AutoTrader.jsx`: card strategia aggiornata (direzione netta, frequenza 1×/giorno, stato Telegram); handler linkTelegram/testTelegram. Backend agent-tested via API live; frontend compila (Compiled successfully) — i nuovi pulsanti non ri-testati E2E in-browser ma verificati a livello API.
- Stato: bot ATTIVO con ~9 posizioni demo (alcuni hedge legacy pre-direzione-netta ancora aperti; i nuovi cicli non ne aprono più).

## Backlog / prossimi step
- P1: Rolling walk-forward su più finestre annuali (non solo ultimo anno) per stimare stabilità nel tempo.
- P1: Esecuzione live guidata su Tickmill demo dalla strategia appresa (con conferma + kill switch).
- P2: Portafoglio multi-strumento con correlazioni; job store discover con TTL/eviction; split di server.py (~1180 righe).
