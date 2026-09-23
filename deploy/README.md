# Apex Flow — Installazione sul tuo VPS (indipendenza totale)

Guida per far girare **tutto** (bot + backend + app PWA) su un tuo server, senza dipendere da Emergent.
Tutto gira in Docker: backend FastAPI + il bot 24/7 + la PWA React servita con HTTPS automatico.

**Costo totale: ~4,50 €/mese** (solo il VPS). Database e HTTPS sono gratuiti.

---

## Cosa ti serve (una volta sola)

1. **VPS Hetzner CX22** — 2 vCPU / 4 GB RAM / ~4,50 €/mese → https://www.hetzner.com/cloud
2. **MongoDB Atlas** (gratis, piano M0) → https://www.mongodb.com/cloud/atlas/register
3. **DuckDNS** (sottodominio gratis per avere HTTPS) → https://www.duckdns.org
4. Le tue chiavi **MetaApi** (token + account id) e, se vuoi, il **token del bot Telegram**.

---

## Passo 1 — Crea il VPS Hetzner
1. Registrati su Hetzner Cloud → crea un progetto → **Add Server**.
2. Immagine: **Ubuntu 24.04**. Tipo: **CX22**. Località: Germania/Finlandia.
3. Aggiungi la tua chiave SSH (o usa la password che ti invia via email).
4. Crea il server e **annota l'indirizzo IP pubblico** (es. `203.0.113.45`).
5. In **Firewall** (o più tardi), assicurati che siano aperte le porte **22, 80, 443**.

## Passo 2 — DuckDNS (dominio gratis → HTTPS)
1. Vai su https://www.duckdns.org, accedi con Google/GitHub.
2. Crea un sottodominio, es. `apexflow` → diventa **`apexflow.duckdns.org`**.
3. Nel campo **current ip** metti l'**IP del VPS** del Passo 1 e premi **update ip**.

## Passo 3 — MongoDB Atlas (database gratis)
1. Registrati su Atlas → crea un cluster **M0 (Free)**.
2. **Database Access** → crea un utente con password.
3. **Network Access** → **Add IP Address** → `0.0.0.0/0` (consenti da ovunque).
4. **Connect → Drivers** → copia la **connection string** (`mongodb+srv://...`).

## Passo 4 — Installa Docker sul VPS
Collegati via SSH (`ssh root@IP_DEL_VPS`) e incolla:
```bash
curl -fsSL https://get.docker.com | sh
```

## Passo 5 — Scarica il codice
Il modo più comodo per gli aggiornamenti futuri è **GitHub**:
- In Emergent usa il pulsante **"Save to GitHub"** per pubblicare il codice sul tuo repository.
- Poi sul VPS:
```bash
git clone https://github.com/TUO-UTENTE/TUO-REPO.git apexflow
cd apexflow
```
(In alternativa puoi caricare la cartella del progetto con `scp`.)

## Passo 6 — Configura le variabili
```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```
Compila:
- `DOMAIN=apexflow.duckdns.org` (il tuo sottodominio del Passo 2)
- `MONGO_URL=...` (la stringa di Atlas del Passo 3) e `DB_NAME=apexflow`
- `JWT_SECRET=` (genera con `openssl rand -hex 32`)
- `METAAPI_TOKEN=` e `METAAPI_ACCOUNT_ID=` (dal tuo MetaApi)
- `TELEGRAM_BOT_TOKEN=` (facoltativo)
Salva con `CTRL+O`, `Invio`, esci con `CTRL+X`.

## Passo 7 — Avvia tutto
```bash
docker compose -f deploy/docker-compose.yml up -d --build
```
La prima build richiede qualche minuto. Al termine:
- Apri **https://apexflow.duckdns.org** → l'app è online con HTTPS valido.
- Accedi con `demo@apexflow.io` / `apexflow2026` (o "Entra con Account Demo").
- Sul telefono Android: apri quell'URL in Chrome → **Installa app** (PWA).
- Nel cockpit premi **Avvia bot**: da qui il bot lavora **24/7 anche a telefono spento**.

### Comandi utili
```bash
docker compose -f deploy/docker-compose.yml logs -f        # vedi i log in tempo reale
docker compose -f deploy/docker-compose.yml restart        # riavvia
docker compose -f deploy/docker-compose.yml down           # ferma tutto
```

---

## Fare aggiornamenti (dopo aver modificato l'app su Emergent)
1. Su Emergent continui a sviluppare come sempre.
2. Premi **"Save to GitHub"** per salvare le modifiche sul repository.
3. Sul VPS lancia:
```bash
./deploy/update.sh
```
Lo script scarica il codice nuovo, ricostruisce e riavvia. **I dati (Atlas) e le posizioni aperte non si perdono.** Fine.

> Nota: modifiche a `deploy/.env` (es. cambio dominio o chiavi) richiedono un `docker compose -f deploy/docker-compose.yml up -d --build`.

---

## Note importanti
- **Il bot gira sul VPS, non sul telefono**: la PWA è solo il telecomando. Con il VPS sempre acceso, il ciclo giornaliero (22:00 UTC) e gli ordini funzionano anche con l'app chiusa.
- **HTTPS**: serve il dominio DuckDNS perché su IP nudo non esistono certificati validi (e senza HTTPS la PWA non si installa). Con DuckDNS + Caddy è automatico e gratis.
- **Sicurezza**: il backend NON è esposto direttamente; solo Caddy (80/443) è pubblico e inoltra `/api` internamente. Cambia sempre `JWT_SECRET` e `ADMIN_PASSWORD`.
- **Conto demo**: stai operando su MT5 demo. Nessuno stop di prezzo (solo TP + time-stop + limite posizioni). I risultati storici non garantiscono profitti futuri.
