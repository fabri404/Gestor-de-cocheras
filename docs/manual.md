# Manual de uso — Gestor de Cocheras (Forin Cars)

> **Audiencia:** operadores, dueños y superadmin que usan el sistema día a día.  
> No cubre instalación ni desarrollo — para eso ver el `README.md`.

---

## Tabla de contenidos

1. [Roles de usuario](#1-roles-de-usuario)
2. [Acceso al sistema](#2-acceso-al-sistema)
3. [Dashboard — pantalla principal](#3-dashboard--pantalla-principal)
4. [Flujo de parking (cochera)](#4-flujo-de-parking-cochera)
5. [Car wash (lavadero)](#5-car-wash-lavadero)
6. [Inventario](#6-inventario)
7. [Membresías y planes](#7-membresías-y-planes)
8. [Panel de ingreso público por QR](#8-panel-de-ingreso-público-por-qr)
9. [Panel de Superadmin (`/admin`)](#9-panel-de-superadmin-admin)
10. [Modo oscuro](#10-modo-oscuro)
11. [Comportamientos no obvios](#11-comportamientos-no-obvios)
12. [Glosario](#12-glosario)
13. [Errores comunes y soluciones](#13-errores-comunes-y-soluciones)
14. [Features planificadas / incompletas](#14-features-planificadas--incompletas)

---

## 1. Roles de usuario

| Rol | Cómo se asigna | Qué puede hacer |
|-----|----------------|-----------------|
| **Superadmin** | `is_superuser` en Django | Todo. Al loguearse, va directo a `/admin`. |
| **Admin Dueño** | Grupo `ADMIN_DUENO` | Crear/editar cocheras, configurar tarifas, gestionar catálogos (servicios, planes, checklist), invitar empleados. También puede operar. |
| **Admin Empleado** | Grupo `ADMIN_EMPLEADO` | Operar cocheras asignadas (ingreso, egreso, órdenes de trabajo, turnos, clientes, inventario movimientos). No puede editar configuración. |
| **Usuario sin rol** | Registro libre | Solo puede ver el dashboard. No tiene acceso a ninguna cochera hasta que un Dueño lo invite o un Superadmin le asigne grupo. |

### Cómo se convierte un usuario en Empleado

**Camino recomendado (invitación previa):**
1. El Dueño va a "Editar cochera" → sección "Invitar empleados" → ingresa el email del empleado.
2. Si el empleado ya tiene cuenta, queda vinculado automáticamente.
3. Si aún no tiene cuenta, cuando se registre con ese email, el sistema lo detecta y lo vincula solo.

**Camino alternativo (asignación manual):**
Un Superadmin puede asignar el grupo `ADMIN_DUENO` o `ADMIN_EMPLEADO` directamente desde `/admin` → Users → editar usuario → sección "Groups".

---

## 2. Acceso al sistema

### Login
URL: `/login/`

- Ingresá tu **usuario** (no email) y contraseña.
- Si sos Superadmin, serás redirigido a `/admin` automáticamente.
- Los demás van al **Dashboard**.

### Registro
URL: `/registro/`

- Completá usuario, email y contraseña.
- Si el dueño ya te invitó por email, quedás vinculado automáticamente a la cochera y con rol Empleado.
- Si no tenés invitación, el sistema te avisa cómo pedir acceso.

### Cerrar sesión
Botón **"Cerrar sesión"** en el navbar superior (escritorio) o ícono de salida en la barra inferior (móvil).

---

## 3. Dashboard — pantalla principal

URL: `/dashboard/`

El dashboard es el **hub central** de navegación. Muestra:

- **Métricas globales** de parking: total de espacios, ocupados, libres, % de ocupación.
- **KPIs del lavadero**: órdenes del día, pendientes, en proceso, facturado hoy/mes, ticket promedio, top servicios.
- **Tarjetas por cochera**: cada cochera tiene sus acciones rápidas.

### Acciones por cochera en el dashboard

| Acción | Quién la ve | Qué hace |
|--------|------------|---------|
| **Panel vivo** | Operador | Vista en tiempo real de espacios ocupados/libres |
| **Ingreso** | Operador | Registrar entrada de vehículo |
| **Egreso** | Operador | Registrar salida y calcular monto |
| **Nueva OT** | Operador | Crear orden de trabajo de lavadero |
| **Órdenes** | Operador | Listar órdenes del lavadero |
| **Turnos** | Operador | Ver/crear agenda de turnos |
| **Clientes** | Operador | Buscar y ver historial de clientes |
| **Servicios** | Operador | Ver catálogo de servicios |
| **Inventario** | Operador | Ver stock de productos |
| **Planes** | Operador | Ver planes de membresía |
| **QR** | Operador | Ver QR para ingreso público |
| **Checklist** | Solo Dueño | Configurar checklist de calidad |
| **Editar** | Solo Dueño | Editar nombre, tarifas, capacidades |

---

## 4. Flujo de parking (cochera)

### 4.1 Crear una cochera (solo Dueño)

1. Dashboard → **+ Cochera** en el navbar, o "Crear cochera" en el dashboard.
2. Completar: nombre, dirección.
3. **Capacidad por tipo**: indicar cuántos espacios de cada tipo (Auto, Moto, etc.).
4. **Tarifas por hora**: indicar el precio por hora para cada tipo.
5. **Invitar empleados** (opcional): ingresar emails separados por comas.
6. Guardar → el sistema crea los espacios automáticamente.

> ⚠️ Si no configurás tarifa para un tipo de vehículo, no podrás registrar ingresos de ese tipo.

### 4.2 Panel vivo

URL: `/parking/cocheras/<id>/live/`

Muestra el estado actual de la cochera:
- Barra de ocupación total.
- Grillas de espacios por tipo: verde (libre) / rojo (ocupado) con tooltip del vehículo.
- Lista de vehículos adentro con tiempo transcurrido y monto acumulado.
- Membresías activas.
- Botón de egreso rápido para cada vehículo.

> ⚠️ **No es en tiempo real automático** — es una foto al momento de cargar la página. Para actualizar, recargá el navegador.

### 4.3 Ingreso de vehículo

1. Dashboard → **Ingreso** (o navbar → Ingreso).
2. Si tenés varias cocheras, elegí la cochera.
3. Completar el formulario:
   - **Tipo de vehículo**: Auto, Moto, etc.
   - **Últimos 3 caracteres de patente**: p.ej. `ABC` para `AA 123 ABC`.
   - **Horas previstas**: estimación de cuánto va a estar el vehículo.
   - **Modalidad de pago**: "Por hora" o "Membresía" (si el cliente tiene membresía activa).
   - Datos del cliente (opcionales pero útiles para historial).
4. Guardar → se descarga automáticamente el **ticket PDF** con código QR.

> 💡 El ticket es el comprobante del cliente. Imprimilo o envialo por WhatsApp.

**Cobro mínimo:** aunque el vehículo salga en minutos, se cobra al menos 1 hora de tarifa.

### 4.4 Egreso de vehículo

1. Dashboard → **Egreso** (o navbar → Egreso, o Panel vivo → botón de egreso en el vehículo).
2. Ingresar el número de ticket.
3. El sistema calcula el monto real (tiempo × tarifa, mínimo 1 hora).
4. Confirmar → espacio liberado, movimiento cerrado.

El monto cobrado aparece en el mensaje de confirmación.

### 4.5 Editar cochera

Solo Dueños. Desde dashboard → **Editar**.  
Podés cambiar nombre, dirección, ajustar capacidades y tarifas, e invitar nuevos empleados.

> ⚠️ Cambiar la capacidad regenera los espacios. No se puede si hay vehículos adentro.

---

## 5. Car wash (lavadero)

### 5.1 Catálogo de servicios

URL: `/parking/cocheras/<id>/servicios/`

Solo Dueños pueden crear/editar/activar-desactivar servicios. Los Empleados los pueden ver.

Cada servicio tiene: nombre, categoría (Lavado, Protección, Restauración, Detailing, Otro), precio y duración estimada.

### 5.2 Clientes

URL: `/parking/cocheras/<id>/clientes/`

Listado con búsqueda por nombre/apellido/patente/email y filtros (membresía, por hora, etc.).  
Al hacer clic en un cliente se ve su historial completo (órdenes, turnos, vehículos, membresías).

### 5.3 Órdenes de trabajo (OT)

URL: `/parking/cocheras/<id>/ordenes/`

**Crear una OT:**
1. Órdenes → **Nueva OT** (o dashboard / navbar → Nueva OT).
2. Buscar o crear cliente por patente.
3. Completar datos del vehículo.
4. Seleccionar servicios a realizar.
5. Indicar fecha/hora de entrega estimada y observaciones.
6. Guardar → se genera un número OT (`OT-XXXXXX`) y se crea el checklist de calidad automáticamente.

**Estados de una OT:**
- `PENDIENTE` → `EN_PROCESO` → `FINALIZADO` o `CANCELADO`
- El cambio a FINALIZADO registra la fecha/hora de entrega real.

**En el detalle de la OT** podés:
- Cambiar el estado.
- Cargar fotos antes/después.
- Completar el checklist de calidad.
- Ver los consumos de inventario.

### 5.4 Turnos / Agenda

URL: `/parking/cocheras/<id>/turnos/`

Crear turnos para clientes con fecha, hora, duración y vehículo. Se puede vincular a una OT existente.

### 5.5 Checklist de calidad

El checklist se configura por cochera (solo Dueño): `/parking/cocheras/<id>/checklist/`  
Al crear una OT, se clona el checklist activo y el operador lo va tildando en el detalle de la orden.

---

## 6. Inventario

URL: `/parking/cocheras/<id>/inventario/`

Gestión del stock de productos (shampoos, ceras, etc.).

### Tipos de movimiento de stock

| Tipo | Efecto |
|------|--------|
| **ENTRADA** | Suma al stock actual (compra o recepción) |
| **SALIDA** | Resta del stock actual (uso en servicio) |
| **AJUSTE** | Fija el stock al valor indicado (corrección por conteo físico) |

> 💡 **AJUSTE** = "conté y hay exactamente X unidades". El sistema actualiza el stock al número que ingresás, sin importar lo que había antes.

Los productos con stock ≤ stock mínimo aparecen en rojo como "bajo stock" y se cuentan en el KPI del dashboard.

Solo Dueños pueden crear/editar productos. Cualquier operador puede registrar movimientos.

---

## 7. Membresías y planes

### 7.1 Planes

URL: `/parking/cocheras/<id>/planes/`

El Dueño crea planes de membresía con precio mensual, lavados incluidos (0 = ilimitados) y descuento.

### 7.2 Crear membresía para un cliente

URL: `/parking/cocheras/<id>/membresias/nueva/`

Vincular un cliente a un plan con fecha de inicio y vencimiento.

### 7.3 Usar membresía en el ingreso

Al registrar un ingreso, elegir modalidad "Membresía" y seleccionar la membresía activa del cliente. El vehículo no paga hora al egresar.

> ⚠️ **Feature en desarrollo:** Los lavados incluidos y descuentos de membresía aún no se aplican automáticamente en las órdenes de lavadero.

---

## 8. Panel de ingreso público por QR

### Para el Dueño/Operador

1. Dashboard → **QR** (se abre en pestaña nueva).
2. Muestra el código QR y el link directo.
3. Imprimí el QR y ponlo en la entrada de la cochera.

### Para el cliente (escanea el QR)

1. Escanea el QR con la cámara del celular.
2. Completa el formulario: tipo de vehículo, últimos 3 de patente, nombre.
3. Al confirmar, ve la pantalla de confirmación con su número de ticket.
4. Al salir presenta el ticket al operador para el egreso.

> El QR tiene un **token firmado** por seguridad: solo funciona para esa cochera específica. Si el token expira o es inválido, la página muestra "Token inválido".

---

## 9. Panel de Superadmin (`/admin`)

URL: `/admin/`

Acceso solo para usuarios con `is_superuser`. En este panel podés:

- **Gestionar usuarios**: crear usuarios, asignar grupos (`ADMIN_DUENO`, `ADMIN_EMPLEADO`).
- **Ver y editar todos los datos**: cocheras, movimientos, clientes, órdenes, inventario, membresías.
- **Gestionar invitaciones**: ver el estado de las invitaciones de empleados.
- **Gestionar tipos de espacio**: crear nuevos tipos (Auto, Moto, Camioneta, etc.).

### Cómo asignar un grupo a un usuario

1. `/admin` → **Users** → clic en el usuario.
2. Sección "Groups" → mover `ADMIN_DUENO` o `ADMIN_EMPLEADO` a "Chosen groups".
3. Guardar.

### Cómo crear el primer Dueño

Después de registrar el usuario, ir a `/admin` → Users → asignarle el grupo `ADMIN_DUENO`.  
Luego el Dueño puede crear su cochera desde el Dashboard.

---

## 10. Modo oscuro

Botón de luna/sol en el navbar (escritorio) o el botón flotante (móvil).  
La preferencia se guarda en el navegador (no en el servidor), por lo que cada dispositivo recuerda su propia configuración.  
Si tu sistema operativo está en modo oscuro, el sistema lo detecta automáticamente al primer ingreso.

---

## 11. Comportamientos no obvios

| Situación | Comportamiento |
|-----------|---------------|
| **Cobro mínimo** | Aunque el auto salga en 5 minutos, se cobra 1 hora de tarifa. |
| **Panel vivo no es real-time** | Es una foto del momento de carga. Recargar para actualizar. |
| **Sin tarifa → no ingresa** | Si el tipo de vehículo no tiene tarifa configurada, el sistema rechaza el ingreso con error. |
| **Sin espacios libres → no ingresa** | Si todos los espacios del tipo están ocupados, el ingreso falla. Revisá el panel vivo. |
| **Ticket auto-generado** | Si dejás el campo ticket vacío al ingresar, el sistema genera uno automático (`TKT-XXXXXXXX`). |
| **AJUSTE de inventario** | Fija el stock al valor que ingresás (no suma ni resta). |
| **Membresía en parking** | Al egresar un vehículo con membresía, el monto cobrado es $0. |
| **Regeneración de espacios** | Al editar capacidades de una cochera, los espacios se recrean. No funciona si hay vehículos adentro. |
| **Invitación de empleado** | Si el empleado no existe aún, se crea la invitación pendiente. Al registrarse con ese email, queda vinculado automáticamente. |

---

## 12. Glosario

| Término | Definición |
|---------|-----------|
| **Cochera** | Establecimiento físico (parking o lavadero). Tiene dueño y empleados asignados. |
| **Movimiento** | Registro de entrada/salida de un vehículo al parking. Tiene estado ABIERTO/CERRADO. |
| **Espacio** | Plaza física de una cochera (p.ej. espacio A1 para autos). |
| **Ticket** | Código único de un vehículo (formato `TKT-XXXXXXXX`). Es la llave para el egreso. |
| **OT** | Orden de Trabajo. Registro de servicios de lavadero realizados a un vehículo. |
| **Turno** | Cita/reserva de un cliente para traer su vehículo. Puede vincularse a una OT. |
| **Tarifa** | Precio por hora configurado por tipo de vehículo en cada cochera. |
| **Membresía** | Suscripción de un cliente a un Plan. Permite ingresar al parking sin cargo por hora. |
| **Plan** | Producto de suscripción con precio mensual y beneficios (lavados incluidos, descuento). |
| **ChecklistItem** | Punto de control de calidad configurado por el dueño (p.ej. "Revisión de carrocería"). |
| **AJUSTE** | Corrección absoluta del stock de inventario al valor de conteo físico. |

---

## 13. Errores comunes y soluciones

### "No hay tarifa configurada para este tipo de vehículo"
El tipo de vehículo seleccionado no tiene precio por hora. Solución: Dueño → Editar cochera → configurar tarifa para ese tipo.

### "No hay espacios libres disponibles"
La cochera está llena para ese tipo de vehículo. Verificar en el Panel Vivo si hay vehículos que olvidaron hacer egreso.

### "Ese vehículo ya está dentro (movimiento ABIERTO)"
El mismo ticket ya tiene un movimiento abierto. Hacer egreso primero o revisar en Panel Vivo.

### "No existe un movimiento ABIERTO para ese ticket"
El ticket no corresponde a ningún vehículo actualmente dentro de esa cochera. Verificar que el ticket sea correcto y que sea la cochera correcta.

### "Token inválido" (en ingreso público QR)
El QR escaneado está vencido o fue generado para otra cochera. El Dueño/Operador debe mostrar el QR actualizado desde el menú "QR" de la cochera.

### Usuario sin acceso a cocheras
El usuario no tiene grupo asignado. Pedirle al Dueño que lo invite por email, o al Superadmin que asigne el grupo desde `/admin`.

### "Ninguno de los servicios seleccionados es válido"
Los servicios seleccionados están inactivos o no pertenecen a la cochera. Revisar el catálogo de servicios.

---

## 14. Features planificadas / incompletas

Las siguientes funcionalidades están parcialmente implementadas (el modelo de datos existe pero la lógica de aplicación está pendiente):

| Feature | Estado | Descripción |
|---------|--------|-------------|
| **Beneficios de membresía en lavadero** | Pendiente | `Plan.lavados_incluidos`, `Plan.descuento_pct`, `Membresia.lavados_usados` no se aplican en OTs. El descuento no se deduce del monto de la orden. |
| **Clientes VIP** | Pendiente | `Cliente.es_vip` existe en el modelo pero no tiene tratamiento especial en ningún flujo. |
| **Descuento automático** | Pendiente | `Plan.descuento_pct` está en el modelo pero no afecta los precios en órdenes. |
| **App QR independiente** | Desconectada | La app `qrform` (links QR genéricos) está desconectada porque sus templates no existen. El QR de cochera (parking) está operativo. |

Si necesitás alguna de estas features, contactar al equipo de desarrollo.
