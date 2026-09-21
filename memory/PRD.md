# Apex Flow — PRD

## Problema originale (utente, IT)
"Voglio un app per fare trading automatico. Ma non il trading retail che fanno tutti, voglio un metodo sicuro con winrate al 98%."

Nota di onestà comunicata all'utente: nessun sistema garantisce il 98% di winrate. Costruito come **terminale dimostrativo/educativo** in stile istituzionale "Smart Money", con dati simulati e disclaimer chiari.

## Scelte utente
- Fase attuale: backtest + forward-test (dati simulati). Broker reale **Tickmill**: predisposto come step futuro, mostrato "pending", NON implementato.
- Mercati: mix (crypto / forex / azioni).
- Strategia: analisi AI "Smart Money" / order flow istituzionale (order block, FVG, liquidità, market structure) — non strategie retail.
- AI: **Claude Sonnet 4.6** (Emergent Universal Key).
- Auth: email/password con account demo pre-seedato.
- Dati mercato: simulati/demo.

## Architettura
- Backend FastAPI (`/app/backend/server.py`), MongoDB (motor). Auth JWT Bearer (token in localStorage `apex_token`).
- Frontend React (CRA + craco, alias `@`→src), Tailwind, shadcn/ui, recharts, lucide, sonner.
- AI via `emergentintegrations` (LlmChat, anthropic/claude-sonnet-4-6) con fallback deterministico.
- Simulazione mercato server-side (random walk seedato per simbolo/timeframe) + zone Smart Money calcolate (swing, order block, FVG, liquidità, struttura).

## Implementato (2026-09-21)
- Login/Register + demo login (demo@apexflow.io / apexflow2026), account seedato con $100k, bot config, 3 posizioni attive, ~24 storiche.
- Dashboard cockpit: Header con ticker live + saldo + kill switch, Watchlist multi-asset con ricerca, grafico candlestick SVG live con overlay OB/FVG/Liquidità e selettore timeframe.
- Pannello AI Smart Money (Claude 4.6): bias, confidence, narrativa IT, setup entry/SL/TP1-3.
- Pannello Bot: avvio/pausa, config risk (winrate filter, max drawdown, rischio %, max trade), blocco di emergenza, gateway Tickmill (pending).
- Backtest runner: winrate/profit factor/drawdown/net profit, equity curve, log; disclaimer risultati simulati.
- Tabella posizioni: attive con PnL live + storico, chiusura posizione con aggiornamento saldo.
- Disclaimer educativi su rischio e natura simulata.
- Verificato: 24/24 test backend + flusso e2e frontend completo.

## Backlog / prossimi step
- P1: Connessione reale broker Tickmill (richiede credenziali/API utente; rischioso).
- P1: Auto-refresh streaming (WebSocket) per prezzi e posizioni invece del polling.
- P2: Persistenza storico analisi AI e alert automatici.
- P2: Split di server.py in router modulari.
- P2: Notifiche/esecuzioni automatiche del bot che aprono posizioni simulate.
