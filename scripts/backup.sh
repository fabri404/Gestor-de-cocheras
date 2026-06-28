#!/usr/bin/env bash
# backup.sh — pg_dump de la instancia N hacia backups/parking-N/
# Uso: bash scripts/backup.sh [INSTANCE]
#      Ej: bash scripts/backup.sh 1
#      Cron (diario a las 2am): 0 2 * * * cd /opt/forin-cars && bash scripts/backup.sh 1
set -euo pipefail

INSTANCE="${1:-1}"
ENV_FILE=".env.parking-$INSTANCE"
BACKUP_DIR="backups/parking-$INSTANCE"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"   # conservar N días de backups

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[backup]${NC} $*"; }
error() { echo -e "${RED}[backup]${NC} $*" >&2; exit 1; }

# ─── Validaciones ─────────────────────────────────────────────────────────────
[ -f "$ENV_FILE" ] || error "$ENV_FILE no existe. Creá la instancia primero con: make new-instance INSTANCE=$INSTANCE"

DB_NAME=$(grep "^DB_NAME=" "$ENV_FILE" | cut -d= -f2)
DB_USER=$(grep "^DB_USER=" "$ENV_FILE" | cut -d= -f2)
DB_PASSWORD=$(grep "^DB_PASSWORD=" "$ENV_FILE" | cut -d= -f2)
PROJECT="parking-$INSTANCE"

[ -z "$DB_NAME" ]     && error "DB_NAME no encontrado en $ENV_FILE"
[ -z "$DB_USER" ]     && error "DB_USER no encontrado en $ENV_FILE"
[ -z "$DB_PASSWORD" ] && error "DB_PASSWORD no encontrado en $ENV_FILE"

# ─── Crear directorio de destino ──────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

info "Iniciando backup de instancia $INSTANCE ($DB_NAME)..."

# ─── Ejecutar pg_dump dentro del contenedor de la DB ─────────────────────────
docker compose -p "$PROJECT" --env-file "$ENV_FILE" \
  exec -T db \
  sh -c "PGPASSWORD='$DB_PASSWORD' pg_dump -U '$DB_USER' '$DB_NAME' --no-owner --no-acl" \
  | gzip > "$BACKUP_FILE"

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
info "Backup guardado: $BACKUP_FILE ($BACKUP_SIZE)"

# ─── Verificar integridad mínima ─────────────────────────────────────────────
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
  error "El backup está corrupto: $BACKUP_FILE"
fi
info "Integridad verificada (gzip OK)."

# ─── Limpiar backups viejos ───────────────────────────────────────────────────
OLD_COUNT=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS | wc -l)
if [ "$OLD_COUNT" -gt 0 ]; then
  find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
  info "Eliminados $OLD_COUNT backups con más de $RETENTION_DAYS días."
fi

# ─── Listar backups disponibles ───────────────────────────────────────────────
info "Backups disponibles en $BACKUP_DIR:"
ls -lh "$BACKUP_DIR/"*.sql.gz 2>/dev/null || true

echo ""
echo "Para restaurar: bash scripts/restore.sh $INSTANCE $BACKUP_FILE"
