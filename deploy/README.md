# Apex Flow — Installazione sul tuo VPS (indipendenza totale)

Guida per far girare **tutto** (bot + backend + app PWA) su un tuo server, senza dipendere da Emergent.
Tutto gira in Docker: backend FastAPI + il bot 24/7 + la PWA React servita con HTTPS automatico.

**Per il test sul conto demo useremo Oracle Cloud "Always Free" (0 €).** Quando passerai al conto vero,
consiglio di spostarti su **Hetzner CAX11 (~3,79 €/mese)**: basterà rifare `git clone` + `.env` + avvio, il pacchetto è identico.

---

## Cosa ti serve (una volta sola)

1. **Server**:
   - **Test (gratis)** → **Oracle Cloud Always Free**, istanza ARM Ampere A1 → https://www.oracle.com/cloud/free/
   - **Produzione (a pagamento, affidabile)** → **Hetzner CAX11** ARM 4 GB, ~3,79 €/mese → https://www.hetzner.com/cloud
2. **MongoDB Atlas** (gratis, piano M0) → https://www.mongodb.com/cloud/atlas/register
3. **DuckDNS** (sottodominio gratis per avere HTTPS) → https://www.duckdns.org
4. Le tue chiavi **MetaApi** (token + account id) e, se vuoi, il **token del bot Telegram**.

> Nota architettura: le immagini Docker sono multi-arch, quindi funzionano **identiche** sia su ARM (Oracle/Hetzner CAX) sia su x86.

---

## Passo 1 — Crea il server

### Opzione A — Oracle Cloud Always Free (gratis, per il test) ⭐
1. Registrati su Oracle Cloud (serve una carta per la verifica, ma il tier **Always Free non viene addebitato**).
2. **Menu → Compute → Instances → Create Instance**.
3. **Image**: Ubuntu 24.04. **Shape**: cambia in **VM.Standard.A1.Flex** (ARM Always Free) → imposta **2 OCPU / 12 GB** (rientra nel free).
4. **Networking**: assegna un **IP pubblico**. Aggiungi la tua chiave SSH.
5. Crea l'istanza e **annota l'IP pubblico**.
6. **⚠️ APRI LE PORTE (2 livelli — è il punto dove tutti si bloccano):**
   - **a) Security List del cloud**: Networking → Virtual Cloud Networks → la tua VCN → Security Lists → Default → **Add Ingress Rules**:
     - Source `0.0.0.0/0`, IP Protocol TCP, Destination Port **80**
     - Source `0.0.0.0/0`, IP Protocol TCP, Destination Port **443**
   - **b) Firewall interno dell'istanza** (le immagini Ubuntu di Oracle bloccano tutto tranne SSH). Collegati in SSH e lancia:
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save
     ```
   Senza ENTRAMBI i passaggi, HTTPS non funziona e la PWA non si installa.

### Opzione B — Hetzner CAX11 (per la produzione)
1. Registrati su Hetzner Cloud → **Add Server**.
2. Immagine: **Ubuntu 24.04**. Tipo: **CAX11** (ARM, 4 GB). Località: Germania/Finlandia.
3. Aggiungi la tua chiave SSH e crea il server; **annota l'IP pubblico**.
4. In **Firewall** apri le porte **22, 80, 443** (su Hetzner basta questo, niente iptables interni).

## Passo 2 — DuckDNS (dominio gratis → HTTPS)
1. Vai su https://www.duckdns.org, accedi con Google/GitHub.
2. Crea un sottodominio, es. `apexflow` → diventa **`apexflow.duckdns.org`**.
3. Nel campo **current ip** metti l'**IP del server** del Passo 1 e premi **update ip**.


## Passo 3 — MongoDB Atlas (database gratis)
1. Registrati su Atlas → crea un cluster **M0 (Free)**.
2. **Database Access** → crea un utente con password.
3. **Network Access** → **Add IP Address** → `0.0.0.0/0` (consenti da ovunque).
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
- **Oracle Always Free (test)**: è gratis ma **senza garanzia di uptime** e a volte la capacità ARM non è disponibile (errore "out of capacity" → riprova più tardi o cambia Availability Domain). Va benissimo per testare col demo; quando passi al conto vero, sposta tutto su Hetzner CAX11 rifacendo Passi 4-7 sul nuovo server.
- **Migrazione Oracle → Hetzner**: aggiorna l'IP su DuckDNS al nuovo server, poi `git clone` + copia il tuo `deploy/.env` + `docker compose ... up -d --build`. Il database resta su Atlas, quindi utenti e configurazioni non si perdono.
