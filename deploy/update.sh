#!/usr/bin/env bash
# Aggiorna Trading-bot sul VPS in sicurezza:
#   backup DB -> git pull -> rebuild -> health-check del backend.
# Uso:  ./deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose --env-file deploy/.env -f deploy/docker-compose.yml"

if [ ! -f deploy/.env ]; then
  echo "ERRORE: manca deploy/.env - crealo prima di aggiornare."; exit 1
fi

echo "==> [1/5] Backup del database prima dell'aggiornamento..."
bash deploy/backup.sh || echo "ATTENZIONE: backup non riuscito, continuo comunque."

echo "==> [2/5] Scarico gli aggiornamenti da GitHub..."
if ! git pull --ff-only; then
  echo "ERRORE: git pull non riuscito (probabili modifiche locali)."
  echo "        Ripristina i file tracciati con:  git checkout -- ."
  exit 1
fi

echo "==> [3/5] Ricostruisco e riavvio i container..."
$COMPOSE up -d --build

echo "==> [4/5] Verifico che il backend risponda..."
ok=0
for _ in $(seq 1 20); do
  if $COMPOSE exec -T backend sh -c 'curl -fs http://localhost:8001/api/ >/dev/null 2>&1'; then ok=1; break; fi
  sleep 3
done

echo "==> [5/5] Pulizia immagini vecchie..."
docker image prune -f >/dev/null 2>&1 || true

if [ "$ok" = "1" ]; then
  echo "OK - Aggiornamento completato. Backend sano, app online."
else
  echo "ATTENZIONE: aggiornamento fatto ma il backend non ha risposto in tempo."
  echo "            Controlla i log:  $COMPOSE logs backend --tail=80"
  exit 1
fi
