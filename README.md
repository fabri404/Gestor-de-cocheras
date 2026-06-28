# Forin Cars — Gestor de Cocheras

Sistema web para gestión operativa de una o múltiples cocheras: ingresos/egresos, tickets PDF con QR, tarifas por tipo de vehículo, empleados por cochera e invitaciones por email.

---

## Requisitos

- Python 3.12+ (desarrollo local)
- Docker 24+ y Docker Compose v2 (producción / SaaS)
- `make` (`apt install make` en Ubuntu/Debian)
- Git

---

## Desarrollo local (sin Docker)

```bash
# 1. Clonar y crear entorno virtual
git clone <repo-url> && cd "Gestor de cocheras"
python3 -m venv venv && source venv/bin/activate

# 2. Instalar dependencias
pip install -r forin_cars/requirements.txt

# 3. Crear .env de desarrollo
cp forin_cars/.env.example forin_cars/.env
# Editar forin_cars/.env: DJANGO_SECRET_KEY y DJANGO_DEBUG=1 son obligatorios
# DATABASE_URL=sqlite:///db.sqlite3 ya viene por defecto en .env.example

# 4. Migrar y arrancar
cd forin_cars
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

App disponible en `http://localhost:8000`.

---

## Despliegue SaaS (producción — una instancia por cliente)

Cada cliente es una instancia Docker completamente aislada: su propia base de datos Postgres, su propio contenedor y su propio puerto.

### Primer cliente (instancia 1)

```bash
# 1. Crear y editar el archivo de entorno
make new-instance INSTANCE=1
# → crea .env.parking-1, muestra qué campos completar

# 2. Completar los campos obligatorios en .env.parking-1:
#    APP_PORT, DB_NAME/USER/PASSWORD, DJANGO_SECRET_KEY,
#    DJANGO_SUPERUSER_PASSWORD, BUSINESS_NAME

# 3. Levantar (build + migrate + seed + gunicorn)
make setup INSTANCE=1
```

Salida esperada:
```
════════════════════════════════════════════════════
  Instancia 1 lista — Cochera Central
  App   : http://localhost:8080
  Admin : http://localhost:8080/admin
  Login : admin / (contraseña del .env)
════════════════════════════════════════════════════
```

### Segundo cliente (instancia 2)

```bash
make new-instance INSTANCE=2
# editar .env.parking-2: APP_PORT=8081, DB_NAME=parking_b2, ...
make setup INSTANCE=2
```

### Provisioning en un servidor remoto desde cero

```bash
# En el servidor (Ubuntu/Debian)
bash <(curl -sL <repo-url-raw>/scripts/provision.sh)
```

El script instala Docker, clona el repo y guía el alta de la primera instancia.

---

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `DJANGO_SECRET_KEY` | Sí | Clave criptográfica — generar con `python3 -c "import secrets; print(secrets.token_hex(64))"` |
| `DJANGO_DEBUG` | No | `1` = desarrollo, `0` = producción (default) |
| `DJANGO_ALLOWED_HOSTS` | Sí (prod) | Dominio o IP del servidor, coma-separado |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Sí (prod) | `https://mi-dominio.com` |
| `DATABASE_URL` | Sí | `postgres://user:pass@db:5432/dbname` o `sqlite:///db.sqlite3` (dev) |
| `DJANGO_SUPERUSER_EMAIL` | No | Email del admin inicial |
| `DJANGO_SUPERUSER_USERNAME` | No | Username del admin inicial (default: `admin`) |
| `DJANGO_SUPERUSER_PASSWORD` | Sí | Contraseña del admin inicial |
| `BUSINESS_NAME` | No | Nombre del negocio en navbar y tickets (default: `Forin Cars`) |
| `BUSINESS_TIMEZONE` | No | Zona horaria (default: `America/Argentina/Buenos_Aires`) |
| `GUNICORN_WORKERS` | No | Workers de gunicorn (default: `2`) |

---

## Comandos Makefile

```bash
make new-instance INSTANCE=N   # Crea .env.parking-N desde el template
make setup        INSTANCE=N   # Build + levantar + migrate + seed
make up           INSTANCE=N   # Levantar instancia configurada
make up-build     INSTANCE=N   # Levantar y rebuilder imagen
make down         INSTANCE=N   # Detener instancia
make logs         INSTANCE=N   # Logs en tiempo real
make logs-web     INSTANCE=N   # Logs solo del contenedor web
make migrate      INSTANCE=N   # Correr migraciones pendientes
make shell-web    INSTANCE=N   # bash dentro del contenedor web
make shell-db     INSTANCE=N   # psql dentro del contenedor Postgres
make test         INSTANCE=N   # Correr tests Django
```

---

## Actualizar código en producción

```bash
git pull origin main
make up-build INSTANCE=1   # rebuilda y reinicia; las migraciones corren solas
# repetir para cada instancia activa
```

---

## Backup de base de datos

```bash
# Backup de la instancia 1
bash scripts/backup.sh 1

# Los backups quedan en backups/parking-1/
```

---

## Arquitectura

```
Cliente N (browser)
      │
      ▼
  Puerto :808N
      │
  ┌───┴────────────────────┐
  │  web (Docker)          │
  │  Django + gunicorn     │
  │  whitenoise (static)   │
  └───────────┬────────────┘
              │
  ┌───────────┴────────────┐
  │  db (Docker)           │
  │  postgres:16-alpine    │
  │  volumen: parking-N    │
  └────────────────────────┘
```

Cada instancia = un proyecto Docker Compose separado con nombre `parking-N`.

---

## Roles de usuario

| Rol | Permisos |
|---|---|
| **Superuser** (superadmin) | Acceso total + Django admin |
| **ADMIN_DUENO** | Crear/editar cocheras, configurar capacidad/tarifas, invitar empleados |
| **ADMIN_EMPLEADO** | Registrar ingresos y egresos en cocheras asignadas |

---

## Stack

- **Backend:** Django 6.0.6, gunicorn, whitenoise
- **Base de datos:** PostgreSQL 16 (producción) / SQLite (desarrollo)
- **Frontend:** Django templates + Bootstrap 5.3.3 + FontAwesome 6.5
- **PDFs:** ReportLab 4.4.9
- **QR:** qrcode 8.2
- **Infraestructura:** Docker + Docker Compose + Makefile

---

## Estructura del proyecto

```
Gestor de cocheras/
├── forin_cars/                 ← proyecto Django (manage.py aquí)
│   ├── forin_cars/             ← configuración del proyecto
│   │   ├── settings.py         ← config desde env vars
│   │   ├── urls.py             ← rutas raíz + /health/
│   │   └── context_processors.py
│   ├── parking/                ← app principal
│   │   ├── models.py           ← Cochera, Espacio, Movimiento, Tarifa...
│   │   ├── views.py
│   │   ├── services.py         ← lógica de negocio
│   │   ├── services_movimientos.py
│   │   └── pdf_utils.py        ← generación de tickets PDF
│   ├── users/                  ← autenticación y roles
│   ├── qrform/                 ← formulario público por QR
│   ├── templates/              ← templates globales (base.html)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── docker-compose.yml          ← define servicios: db + web
├── docker-compose.override.yml ← overrides para desarrollo local
├── .env.parking-N.example      ← template por instancia
├── Makefile                    ← provisioning y operaciones
├── scripts/
│   ├── provision.sh            ← setup en servidor remoto desde cero
│   └── backup.sh               ← backup de la BD por instancia
└── backups/                    ← backups locales (en .gitignore)
```
