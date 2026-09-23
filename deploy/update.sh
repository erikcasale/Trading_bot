#!/usr/bin/env bash
# Aggiorna Apex Flow sul VPS: scarica il codice nuovo e ricostruisce i container.
set -e
cd "$(dirname "$0")/.."

echo "==> Scarico gli aggiornamenti da GitHub..."
git pull

echo "==> Ricostruisco e riavvio i container..."
docker compose -f deploy/docker-compose.yml up -d --build

echo "==> Pulizia immagini vecchie..."
docker image prune -f

echo "✅ Aggiornamento completato. L'app è di nuovo online."
