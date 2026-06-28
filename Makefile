.PHONY: up up-build down logs logs-web build migrate shell-web shell-db test setup new-instance dev backup restore

# ─── Instancia activa (por defecto: 1) ────────────────────────────────────────
# Uso: make up           → instancia 1 en el puerto definido en .env.parking-1
#      make up INSTANCE=2 → instancia 2
INSTANCE ?= 1
ENV_FILE  = .env.parking-$(INSTANCE)
PROJECT   = parking-$(INSTANCE)
COMPOSE   = docker compose -p $(PROJECT) --env-file $(ENV_FILE)

# ─── Docker ───────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d

up-build:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

logs-web:
	$(COMPOSE) logs -f web

# ─── Base de datos ────────────────────────────────────────────────────────────

migrate:
	$(COMPOSE) exec web python manage.py migrate --noinput

shell-db:
	$(COMPOSE) exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

# ─── Backend ──────────────────────────────────────────────────────────────────

shell-web:
	$(COMPOSE) exec web bash

test:
	$(COMPOSE) exec web python manage.py test

# ─── Provisioning ─────────────────────────────────────────────────────────────
# setup: levanta la instancia, espera el healthcheck e imprime las credenciales.
# Uso: make setup INSTANCE=1

setup:
	$(COMPOSE) up -d --build
	@echo "Esperando que la app esté lista (puede tardar ~40s en el primer build)..."
	@$(COMPOSE) exec web sh -c 'until curl -sf http://localhost:8000/health/ > /dev/null; do sleep 3; done'
	@APP_PORT=$$(grep "^APP_PORT=" $(ENV_FILE) | cut -d= -f2); \
	SUPER_EMAIL=$$(grep "^DJANGO_SUPERUSER_EMAIL=" $(ENV_FILE) | cut -d= -f2); \
	SUPER_USER=$$(grep "^DJANGO_SUPERUSER_USERNAME=" $(ENV_FILE) | cut -d= -f2); \
	BUSINESS=$$(grep "^BUSINESS_NAME=" $(ENV_FILE) | cut -d= -f2); \
	echo ""; \
	echo "════════════════════════════════════════════════════"; \
	echo "  Instancia $(INSTANCE) lista — $${BUSINESS}"; \
	echo "  App   : http://localhost:$${APP_PORT}"; \
	echo "  Admin : http://localhost:$${APP_PORT}/admin"; \
	echo "  Login : $${SUPER_USER:-admin} / (contraseña del .env)"; \
	echo "  Email : $${SUPER_EMAIL:-admin@parking.com}"; \
	echo "════════════════════════════════════════════════════"

dev:
	docker compose -f docker-compose.yml -f docker-compose.override.yml up

# ─── Backup / Restore ─────────────────────────────────────────────────────────

backup:
	bash scripts/backup.sh $(INSTANCE)

restore:
	@read -rp "Archivo de backup (ej: backups/parking-$(INSTANCE)/archivo.sql.gz): " FILE; \
	bash scripts/restore.sh $(INSTANCE) "$$FILE"

# new-instance: crea el .env de la instancia N y guía la configuración.
# Uso: make new-instance INSTANCE=2

new-instance:
	@if [ -f "$(ENV_FILE)" ]; then \
	  echo "$(ENV_FILE) ya existe — editalo manualmente si querés reconfigurarlo."; \
	else \
	  cp .env.parking-N.example $(ENV_FILE); \
	  echo ""; \
	  echo "Creado $(ENV_FILE)."; \
	  echo "Antes de continuar, editá los siguientes campos:"; \
	  echo ""; \
	  echo "  APP_PORT                  → único por instancia (8080, 8081, 8082...)"; \
	  echo "  DB_NAME / DB_USER / DB_PASSWORD  → credenciales Postgres exclusivas"; \
	  echo "  DJANGO_SECRET_KEY         → python -c \"import secrets; print(secrets.token_hex(64))\""; \
	  echo "  DJANGO_SUPERUSER_PASSWORD → contraseña del admin inicial"; \
	  echo "  BUSINESS_NAME             → nombre del negocio (aparece en la app)"; \
	  echo ""; \
	  echo "Luego ejecutá:  make setup INSTANCE=$(INSTANCE)"; \
	  exit 1; \
	fi
	@$(MAKE) setup INSTANCE=$(INSTANCE)
