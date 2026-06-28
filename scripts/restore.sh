#!/usr/bin/env bash
# restore.sh — restaura un backup de pg_dump en la instancia N
# Uso: bash scripts/restore.sh [INSTANCE] [BACKUP_FILE]
#      Ej: bash scripts/restore.sh 1 backups/parking-1/parking_b1_20260628_020000.sql.gz
set -euo pipefail

INSTANCE="${1:-}"
BACKUP_FILE="${2:-}"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
info()  { echo -e "${GREEN}[restore]${NC} $*"; }
warn()  { echo -e "${YELLOW}[restore]${NC} $*"; }
error() { echo -e "${RED}[restore]${NC} $*" >&2; exit 1; }

[ -z "$INSTANCE" ]    && error "Uso: bash scripts/restore.sh INSTANCE BACKUP_FILE"
[ -z "$BACKUP_FILE" ] && error "Uso: bash scripts/restore.sh INSTANCE BACKUP_FILE"
[ -f "$BACKUP_FILE" ] || error "Archivo no encontrado: $BACKUP_FILE"

ENV_FILE=".env.parking-$INSTANCE"
[ -f "$ENV_FILE" ] || error "$ENV_FILE no existe."

DB_NAME=$(grep "^DB_NAME=" "$ENV_FILE" | cut -d= -f2)
DB_USER=$(grep "^DB_USER=" "$ENV_FILE" | cut -d= -f2)
DB_PASSWORD=$(grep "^DB_PASSWORD=" "$ENV_FILE" | cut -d= -f2)
PROJECT="parking-$INSTANCE"

warn "ATENCIÓN: esto sobreescribirá la base de datos $DB_NAME de la instancia $INSTANCE."
read -rp "¿Continuar? [s/N]: " CONFIRM
[[ "$CONFIRM" =~ ^[sS]$ ]] || { info "Abortado."; exit 0; }

info "Restaurando $BACKUP_FILE en instancia $INSTANCE ($DB_NAME)..."

# Restaurar desde el gzip directamente al contenedor de la DB
gunzip -c "$BACKUP_FILE" \
  | docker compose -p "$PROJECT" --env-file "$ENV_FILE" \
      exec -T db \
      sh -c "PGPASSWORD='$DB_PASSWORD' psql -U '$DB_USER' '$DB_NAME' -v ON_ERROR_STOP=1"

info "Restauración completada. Reiniciando la app..."
docker compose -p "$PROJECT" --env-file "$ENV_FILE" restart web

info "Instancia $INSTANCE restaurada correctamente."
