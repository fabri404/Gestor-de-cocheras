#!/usr/bin/env bash
# provision.sh — configura un servidor Ubuntu/Debian desde cero y levanta la primera instancia
# Uso: bash scripts/provision.sh
#      O en servidor remoto: bash <(curl -sL <raw-url>/scripts/provision.sh)
set -euo pipefail

REPO_URL="${REPO_URL:-}"          # sobreescribir si se ejecuta remotamente
INSTANCE="${INSTANCE:-1}"
INSTALL_DIR="${INSTALL_DIR:-/opt/forin-cars}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── Verificar sistema operativo ──────────────────────────────────────────────
if [ ! -f /etc/os-release ]; then
  error "No se pudo detectar el sistema operativo. Este script requiere Ubuntu o Debian."
fi
. /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
  warn "Sistema detectado: $ID $VERSION_ID. Este script fue probado en Ubuntu/Debian."
fi

info "Iniciando provisioning de Forin Cars en $ID $VERSION_ID"

# ─── 1. Actualizar e instalar dependencias del sistema ────────────────────────
info "[1/5] Instalando Docker, make, git y curl..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl git make ca-certificates gnupg lsb-release

# Docker (si no está instalado)
if ! command -v docker &> /dev/null; then
  info "  Docker no encontrado — instalando..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$ID/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$ID $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable docker
  systemctl start docker
  info "  Docker instalado correctamente."
else
  info "  Docker ya está instalado ($(docker --version))."
fi

# ─── 2. Clonar el repositorio ─────────────────────────────────────────────────
info "[2/5] Clonando repositorio..."
if [ -z "$REPO_URL" ]; then
  echo ""
  read -rp "URL del repositorio Git (ej: https://github.com/usuario/gestor-cocheras.git): " REPO_URL
  [ -z "$REPO_URL" ] && error "REPO_URL no puede estar vacío."
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  warn "  El directorio $INSTALL_DIR ya existe — haciendo git pull..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
info "  Repositorio en $INSTALL_DIR"

# ─── 3. Crear el archivo de entorno para la instancia ────────────────────────
info "[3/5] Configurando instancia $INSTANCE..."
ENV_FILE=".env.parking-$INSTANCE"

if [ ! -f "$ENV_FILE" ]; then
  cp .env.parking-N.example "$ENV_FILE"
  info "  Creado $ENV_FILE."
else
  warn "  $ENV_FILE ya existe — omitiendo creación."
fi

# Generar SECRET_KEY automáticamente si está vacía
if grep -q "^DJANGO_SECRET_KEY=$" "$ENV_FILE"; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(64))" 2>/dev/null \
           || openssl rand -hex 64)
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$SECRET|" "$ENV_FILE"
  info "  DJANGO_SECRET_KEY generada automáticamente."
fi

echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Antes de continuar, completá los campos en $ENV_FILE:${NC}"
echo ""
echo "  APP_PORT                → puerto único (8080, 8081...)"
echo "  DB_PASSWORD             → contraseña de Postgres"
echo "  DJANGO_SUPERUSER_PASSWORD → contraseña del admin"
echo "  BUSINESS_NAME           → nombre del negocio (ej: Cochera Central)"
echo "  DJANGO_ALLOWED_HOSTS    → dominio o IP del servidor"
echo "  DJANGO_CSRF_TRUSTED_ORIGINS → https://tu-dominio.com"
echo -e "${YELLOW}════════════════════════════════════════════════════════${NC}"
echo ""
read -rp "¿Editaste el archivo y está listo para continuar? [s/N]: " CONFIRM
[[ "$CONFIRM" =~ ^[sS]$ ]] || error "Abortado. Editá $ENV_FILE y volvé a ejecutar: make setup INSTANCE=$INSTANCE"

# ─── 4. Levantar la instancia ─────────────────────────────────────────────────
info "[4/5] Levantando instancia $INSTANCE con 'make setup'..."
make setup INSTANCE="$INSTANCE"

# ─── 5. Habilitar reinicio automático ─────────────────────────────────────────
info "[5/5] Habilitando reinicio automático en boot..."
PROJECT="parking-$INSTANCE"
# Crear servicio systemd mínimo para que la instancia arranque con el servidor
SERVICE_FILE="/etc/systemd/system/forin-cars-$INSTANCE.service"
cat > "$SERVICE_FILE" << UNIT
[Unit]
Description=Forin Cars instancia $INSTANCE
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/make up INSTANCE=$INSTANCE
ExecStop=/usr/bin/make down INSTANCE=$INSTANCE
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable "forin-cars-$INSTANCE.service"
info "  Servicio forin-cars-$INSTANCE habilitado."

# ─── Resumen final ────────────────────────────────────────────────────────────
APP_PORT=$(grep "^APP_PORT=" "$ENV_FILE" | cut -d= -f2)
SUPER_EMAIL=$(grep "^DJANGO_SUPERUSER_EMAIL=" "$ENV_FILE" | cut -d= -f2)
BUSINESS=$(grep "^BUSINESS_NAME=" "$ENV_FILE" | cut -d= -f2)
SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Provisioning completado — Forin Cars instancia $INSTANCE${NC}"
echo -e "${GREEN}  Negocio : $BUSINESS${NC}"
echo -e "${GREEN}  App     : http://$SERVER_IP:$APP_PORT${NC}"
echo -e "${GREEN}  Admin   : http://$SERVER_IP:$APP_PORT/admin${NC}"
echo -e "${GREEN}  Health  : http://$SERVER_IP:$APP_PORT/health/${NC}"
echo -e "${GREEN}  Login   : ${SUPER_EMAIL:-admin} / (contraseña del .env)${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "Próximos pasos recomendados:"
echo "  1. Configurar Nginx/Caddy como reverse proxy con TLS (Let's Encrypt)"
echo "  2. Programar backups con: crontab -e → '0 2 * * * cd $INSTALL_DIR && bash scripts/backup.sh $INSTANCE'"
echo "  3. Para agregar otro cliente: make new-instance INSTANCE=2"
