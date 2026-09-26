#!/usr/bin/env bash
# Backup giornaliero del MongoDB (container "mongo") con rotazione: tiene gli ultimi 7.
# Uso manuale:   bash deploy/backup.sh
# Personalizza:  BACKUP_DIR=/percorso KEEP=30 bash deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-$HOME/trading-bot-backups}"
KEEP="${KEEP:-7}"
COMPOSE="docker compose --env-file deploy/.env -f deploy/docker-compose.yml"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "==> Dump MongoDB -> $BACKUP_DIR/mongo-$STAMP.archive.gz"
$COMPOSE exec -T mongo sh -c 'mongodump --archive --gzip' > "$BACKUP_DIR/mongo-$STAMP.archive.gz"

echo "==> Rotazione: tengo gli ultimi $KEEP backup"
ls -1t "$BACKUP_DIR"/mongo-*.archive.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "OK - Backup completato: $BACKUP_DIR/mongo-$STAMP.archive.gz"
ls -lh "$BACKUP_DIR"/mongo-*.archive.gz
