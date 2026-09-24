# Trading-bot — Installazione sul tuo VPS (indipendenza totale)

Guida per far girare **tutto** (bot + backend + app PWA) su un tuo server, senza dipendere da Emergent.
Tutto gira in Docker: backend FastAPI + il bot 24/7 + la PWA React servita con HTTPS automatico.

**Setup scelto: VPS server.it "Linux 8" (3 core / 8 GB, Intel Xeon x86) + dominio `trading-bot.it` + MongoDB Atlas free.**
Il VPS x86 è direttamente supportato dalle immagini Docker (nessuna modifica).

---

## Cosa ti serve (una volta sola)

1. **VPS server.it "Linux 8"** (3 core / 8 GB / 80 GB, Ubuntu) → https://www.server.it/it/cloud/vps-linux
2. **Dominio** `trading-bot.it` (anch'esso su server.it)
3. **MongoDB Atlas** (gratis, piano M0) → https://www.mongodb.com/cloud/atlas/register
4. Le tue chiavi **MetaApi** (token + account id) e, se vuoi, il **token del bot Telegram**.

---

## Passo 1 — Crea il VPS su server.it
1. Ordina il piano **Linux 8** → scegli **Ubuntu 24.04** come sistema operativo.
2. Attivazione in ~60 secondi: ricevi via email/pannello l'**IP pubblico** e la **password di root** (o imposti la tua chiave SSH).
3. Le porte 80/443 su questi VPS sono aperte di default (Ubuntu non ha iptables restrittive come Oracle). Se hai un firewall nel pannello server.it, consenti **22, 80, 443**.
4. **Annota l'IP pubblico** del VPS.

## Passo 2 — Collega il dominio trading-bot.it
Nel pannello DNS di **server.it** (Dominio → Gestione DNS) crea due record che puntano all'IP del VPS:
- Record **A** · nome `@` (o vuoto) · valore = **IP del VPS**
- Record **A** · nome `www` · valore = **IP del VPS**
Salva. La propagazione richiede da pochi minuti a qualche ora. Caddy otterrà da solo il certificato HTTPS per `trading-bot.it` e `www.trading-bot.it`.

> In alternativa (se il dominio non è ancora pronto) puoi usare un sottodominio gratuito **DuckDNS** puntato all'IP e mettere quello in `DOMAIN`.

## Passo 3 — MongoDB Atlas (database gratis)
1. Registrati su Atlas → crea un cluster **M0 (Free)**.
2. **Database Access** → crea un utente con password.
3. **Network Access** → **Add IP Address** → metti l'**IP del tuo VPS** (più sicuro di `0.0.0.0/0`).
4. **Connect → Drivers** → copia la **connection string** (`mongodb+srv://...`).

## Passo 4 — Installa Docker sul server
Collegati via SSH:
- **Oracle**: `ssh ubuntu@IP_DEL_SERVER`  (utente `ubuntu`)
- **Hetzner**: `ssh root@IP_DEL_SERVER`

Installa Docker e abilita il tuo utente a usarlo senza `sudo`:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```
(Se `newgrp` dà problemi, esci e rientra in SSH.)

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
- `DOMAIN=trading-bot.it` (il tuo dominio del Passo 2)
- `MONGO_URL=...` (la stringa di Atlas del Passo 3) e `DB_NAME=tradingbot`
- `JWT_SECRET=` (genera con `openssl rand -hex 32`)
- `METAAPI_TOKEN=` e `METAAPI_ACCOUNT_ID=` (dal tuo MetaApi)
- `TELEGRAM_BOT_TOKEN=` (facoltativo)
Salva con `CTRL+O`, `Invio`, esci con `CTRL+X`.

## Passo 7 — Avvia tutto
```bash
docker compose -f deploy/docker-compose.yml up -d --build
```
La prima build richiede qualche minuto. Al termine:
- Apri **https://trading-bot.it** → l'app è online con HTTPS valido.
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
- **Oracle Always Free (test)**: è gratis ma **senza garanzia di uptime** e a volte la capacità ARM non è disponibile (errore "out of capacity" → riprova più tardi o cambia Availability Domain). Va benissimo per testare col demo; quando passi al conto vero, sposta tutto su Hetzner CAX11 rifacendo Passi 4-7 sul nuovo server.
- **Migrazione Oracle → Hetzner**: aggiorna l'IP su DuckDNS al nuovo server, poi `git clone` + copia il tuo `deploy/.env` + `docker compose ... up -d --build`. Il database resta su Atlas, quindi utenti e configurazioni non si perdono.
