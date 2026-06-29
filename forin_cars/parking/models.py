import secrets
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone


class Cochera(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cocheras",
    )
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=200, blank=True)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    empleados = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="cocheras_asignadas",
        blank=True,
        through="CocheraEmpleado",
    )

    @property
    def estado(self):
        return "ACTIVA" if self.activa else "INACTIVA"

    def __str__(self):
        return f"{self.nombre} ({self.owner.username})"


class CocheraEmpleado(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cochera", "empleado"], name="uq_cochera_empleado")
        ]

    def __str__(self):
        return f"{self.cochera.nombre} -> {self.empleado.username}"


class InvitacionEmpleado(models.Model):
    PENDIENTE = "PENDIENTE"
    ACEPTADA = "ACEPTADA"
    CANCELADA = "CANCELADA"
    ESTADOS = [
        (PENDIENTE, "PENDIENTE"),
        (ACEPTADA, "ACEPTADA"),
        (CANCELADA, "CANCELADA"),
    ]

    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="invitaciones")
    email = models.EmailField()
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE)

    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitaciones_aceptadas",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cochera", "email"], name="uq_invite_cochera_email")
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.email} ({self.cochera.nombre}) - {self.estado}"


class TipoEspacio(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.nombre


class ConfigCapacidad(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="capacidades")
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cochera", "tipo"], name="uq_capacidad_cochera_tipo")
        ]

    def __str__(self):
        return f"{self.cochera.nombre} - {self.tipo.nombre}: {self.cantidad}"


class TarifaHora(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="tarifas")
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)
    precio_hora = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cochera", "tipo"], name="uq_tarifa_cochera_tipo")
        ]

    def __str__(self):
        return f"{self.cochera.nombre} - {self.tipo.nombre}: ${self.precio_hora}/h"


class Espacio(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="espacios")
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)
    ocupado = models.BooleanField(default=False)
    etiqueta = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.cochera.nombre} - {self.tipo.nombre} - {'OCUPADO' if self.ocupado else 'LIBRE'}"


class Cliente(models.Model):
    nombre = models.CharField(max_length=80, blank=True)
    apellido = models.CharField(max_length=80, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    observaciones = models.TextField(blank=True)
    es_vip = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        label = (self.nombre + " " + self.apellido).strip()
        return label if label else f"Cliente#{self.pk}"

    @property
    def nombre_completo(self):
        return (self.nombre + " " + self.apellido).strip() or f"Cliente#{self.pk}"


class Vehiculo(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="vehiculos")
    patente_ult3 = models.CharField(max_length=3, blank=True, null=True)
    patente = models.CharField(max_length=10, blank=True, db_index=True)
    marca = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=60, blank=True)
    anio = models.PositiveSmallIntegerField(null=True, blank=True)
    color = models.CharField(max_length=40, blank=True)
    ticket = models.CharField(max_length=20)
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticket"], name="uq_vehiculo_ticket"),
        ]

    def __str__(self):
        p = self.patente or self.patente_ult3 or "SIN-PAT"
        desc = f"{self.marca} {self.modelo}".strip()
        return f"{p} - {desc or self.tipo.nombre}"

    @property
    def descripcion_corta(self):
        parts = [self.patente or self.patente_ult3 or "—"]
        if self.marca:
            parts.append(f"{self.marca} {self.modelo}".strip())
        if self.color:
            parts.append(self.color)
        return " | ".join(parts)


class Movimiento(models.Model):
    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"
    ESTADOS = [(ABIERTO, "ABIERTO"), (CERRADO, "CERRADO")]

    HORA = "HORA"
    MEMBRESIA = "MEMBRESIA"
    TIPOS_PAGO = [
        (HORA, "Por hora"),
        (MEMBRESIA, "Membresía"),
    ]

    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="movimientos")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="movimientos")
    espacio = models.ForeignKey(Espacio, on_delete=models.PROTECT, related_name="movimientos")
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos")

    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTO)
    ingreso_at = models.DateTimeField(default=timezone.now)
    egreso_at = models.DateTimeField(null=True, blank=True)

    # Estimaciones al ingreso
    horas_previstas = models.PositiveIntegerField(default=1)
    egreso_estimado_at = models.DateTimeField(null=True, blank=True)
    tarifa_hora_aplicada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Modalidad de pago
    tipo_pago = models.CharField(max_length=10, choices=TIPOS_PAGO, default=HORA)
    membresia = models.ForeignKey(
        "Membresia", null=True, blank=True, on_delete=models.SET_NULL, related_name="movimientos"
    )

    # Cierre
    monto_cobrado = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pagado = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["cochera", "estado"]),
            models.Index(fields=["vehiculo", "estado"]),
            models.Index(fields=["espacio", "estado"]),
            models.Index(fields=["egreso_estimado_at"]),
        ]

    def __str__(self):
        return f"{self.vehiculo.ticket} - {self.cochera.nombre} - {self.estado}"

    def horas_transcurridas(self):
        fin = self.egreso_at or timezone.now()
        delta = fin - self.ingreso_at
        return round(delta.total_seconds() / 3600, 2)

    def monto_acumulado(self):
        if self.tipo_pago == self.MEMBRESIA:
            return Decimal("0.00")
        horas = Decimal(str(self.horas_transcurridas()))
        # Cobro mínimo: 1 hora (fracción de hora se redondea al bloque de 1h)
        horas = max(horas, Decimal("1.00"))
        monto = self.tarifa_hora_aplicada * horas
        return monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


TipoVehiculo = TipoEspacio


# ─── Catálogo de servicios ────────────────────────────────────────────────────

class Servicio(models.Model):
    LAVADO = "LAVADO"
    PROTECCION = "PROTECCION"
    RESTAURACION = "RESTAURACION"
    DETAILING = "DETAILING"
    OTRO = "OTRO"
    CATEGORIAS = [
        (LAVADO, "Lavado"),
        (PROTECCION, "Protección"),
        (RESTAURACION, "Restauración"),
        (DETAILING, "Detailing / Estética"),
        (OTRO, "Otro"),
    ]

    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="servicios")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_minutos = models.PositiveIntegerField(default=60)
    categoria = models.CharField(max_length=15, choices=CATEGORIAS, default=LAVADO)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["categoria", "nombre"]

    def __str__(self):
        return f"{self.nombre} (${self.precio})"


# ─── Orden de Trabajo ─────────────────────────────────────────────────────────

class OrdenTrabajo(models.Model):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    FINALIZADO = "FINALIZADO"
    CANCELADO = "CANCELADO"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (EN_PROCESO, "En proceso"),
        (FINALIZADO, "Finalizado"),
        (CANCELADO, "Cancelado"),
    ]

    numero = models.CharField(max_length=20, unique=True, editable=False)
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="ordenes")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="ordenes")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="ordenes")
    servicios = models.ManyToManyField(Servicio, through="OrdenServicio", related_name="ordenes")
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ordenes"
    )
    estado = models.CharField(max_length=15, choices=ESTADOS, default=PENDIENTE)
    observaciones = models.TextField(blank=True)
    monto_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    entrega_estimada_at = models.DateTimeField(null=True, blank=True)
    entregado_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["cochera", "estado"]),
            models.Index(fields=["cochera", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = "OT-" + secrets.token_hex(3).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} | {self.vehiculo.patente or self.vehiculo.patente_ult3 or '?'} | {self.get_estado_display()}"

    def recalcular_total(self):
        total = sum(s.precio_aplicado for s in self.ordenservicio_set.all())
        self.monto_total = total
        self.save(update_fields=["monto_total"])
        return total


class OrdenServicio(models.Model):
    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.CASCADE)
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    precio_aplicado = models.DecimalField(max_digits=10, decimal_places=2)
    observaciones = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.orden.numero} — {self.servicio.nombre}"


# ─── Sistema de Turnos ────────────────────────────────────────────────────────

class Turno(models.Model):
    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    EN_ESPERA = "EN_ESPERA"
    EN_PROCESO = "EN_PROCESO"
    FINALIZADO = "FINALIZADO"
    CANCELADO = "CANCELADO"
    AUSENTE = "AUSENTE"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (CONFIRMADO, "Confirmado"),
        (EN_ESPERA, "En espera"),
        (EN_PROCESO, "En proceso"),
        (FINALIZADO, "Finalizado"),
        (CANCELADO, "Cancelado"),
        (AUSENTE, "Ausente"),
    ]

    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="turnos")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="turnos")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="turnos")
    orden = models.OneToOneField(
        OrdenTrabajo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turno",
    )
    fecha = models.DateField()
    hora = models.TimeField()
    duracion_minutos = models.PositiveIntegerField(default=60)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="turnos",
    )
    estado = models.CharField(max_length=15, choices=ESTADOS, default=PENDIENTE)
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "hora"]
        indexes = [
            models.Index(fields=["cochera", "fecha"]),
        ]

    def __str__(self):
        return f"Turno {self.fecha} {self.hora} — {self.cliente.nombre_completo}"


# ─── Checklist de calidad ─────────────────────────────────────────────────────

class ChecklistItem(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="checklist_items")
    descripcion = models.CharField(max_length=150)
    orden = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.cochera.nombre} — {self.descripcion}"


class OrdenChecklist(models.Model):
    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.CASCADE, related_name="checklist")
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT)
    completado = models.BooleanField(default=False)
    observacion = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["item__orden", "item__id"]
        unique_together = [("orden", "item")]

    def __str__(self):
        estado = "✔" if self.completado else "○"
        return f"{estado} {self.item.descripcion}"


# ─── Fotos de Orden ───────────────────────────────────────────────────────────

class FotoOrden(models.Model):
    ANTES = "ANTES"
    DESPUES = "DESPUES"
    TIPOS = [(ANTES, "Antes"), (DESPUES, "Después")]

    orden = models.ForeignKey(OrdenTrabajo, on_delete=models.CASCADE, related_name="fotos")
    tipo = models.CharField(max_length=7, choices=TIPOS, default=ANTES)
    imagen = models.ImageField(upload_to="ordenes/fotos/%Y/%m/")
    descripcion = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "-created_at"]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.orden.numero}"


# ─── Inventario ───────────────────────────────────────────────────────────────

class CategoriaProducto(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="productos")
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.SET_NULL, null=True, blank=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    unidad = models.CharField(max_length=20, default="unidad")
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["categoria__nombre", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.stock_actual} {self.unidad})"

    @property
    def bajo_stock(self):
        return self.stock_actual <= self.stock_minimo


class MovimientoInventario(models.Model):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    AJUSTE = "AJUSTE"
    TIPOS = [
        (ENTRADA, "Entrada"),
        (SALIDA, "Salida"),
        (AJUSTE, "Ajuste"),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="movimientos_inv")
    tipo = models.CharField(max_length=8, choices=TIPOS)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=200, blank=True)
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_inv")
    orden = models.ForeignKey(
        OrdenTrabajo, on_delete=models.SET_NULL, null=True, blank=True, related_name="consumos"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        signo = "+" if self.tipo == self.ENTRADA else "-"
        return f"{signo}{self.cantidad} {self.producto.nombre}"

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.tipo == self.ENTRADA:
                self.producto.stock_actual += self.cantidad
            elif self.tipo == self.AJUSTE:
                # Ajuste absoluto: corrige el stock al valor de conteo físico
                self.producto.stock_actual = self.cantidad
            else:  # SALIDA
                self.producto.stock_actual -= self.cantidad
            self.producto.save(update_fields=["stock_actual"])
        super().save(*args, **kwargs)


# ─── Membresías ───────────────────────────────────────────────────────────────

class Plan(models.Model):
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="planes")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    lavados_incluidos = models.PositiveSmallIntegerField(
        default=0, help_text="0 = ilimitados"
    )
    descuento_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    servicios = models.ManyToManyField(Servicio, blank=True, related_name="planes")

    class Meta:
        ordering = ["precio_mensual"]

    def __str__(self):
        return f"{self.nombre} — ${self.precio_mensual}/mes"


class Membresia(models.Model):
    ACTIVA = "ACTIVA"
    SUSPENDIDA = "SUSPENDIDA"
    CANCELADA = "CANCELADA"
    VENCIDA = "VENCIDA"
    ESTADOS = [
        (ACTIVA, "Activa"),
        (SUSPENDIDA, "Suspendida"),
        (CANCELADA, "Cancelada"),
        (VENCIDA, "Vencida"),
    ]

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="membresias")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="membresias")
    estado = models.CharField(max_length=12, choices=ESTADOS, default=ACTIVA)
    fecha_inicio = models.DateField()
    fecha_vencimiento = models.DateField()
    lavados_usados = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.cliente.nombre_completo} — {self.plan.nombre} ({self.get_estado_display()})"

    @property
    def lavados_restantes(self):
        if self.plan.lavados_incluidos == 0:
            return None
        return max(0, self.plan.lavados_incluidos - self.lavados_usados)
