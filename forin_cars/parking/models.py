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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        label = (self.nombre + " " + self.apellido).strip()
        return label if label else f"Cliente#{self.pk}"


class Vehiculo(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="vehiculos")
    patente_ult3 = models.CharField(max_length=3, blank=True, null=True)
    ticket = models.CharField(max_length=20)
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ticket"], name="uq_vehiculo_ticket"),
        ]

    def __str__(self):
        p = self.patente_ult3 or "SIN-PAT"
        return f"{self.ticket} - {self.tipo.nombre} - {p}"


class Movimiento(models.Model):
    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"
    ESTADOS = [(ABIERTO, "ABIERTO"), (CERRADO, "CERRADO")]

    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="movimientos")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.PROTECT, related_name="movimientos")
    espacio = models.ForeignKey(Espacio, on_delete=models.PROTECT, related_name="movimientos")
    operador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos")

    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTO)
    ingreso_at = models.DateTimeField(default=timezone.now)
    egreso_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["cochera", "estado"]),
            models.Index(fields=["vehiculo", "estado"]),
            models.Index(fields=["espacio", "estado"]),
        ]

    def __str__(self):
        return f"{self.vehiculo.ticket} - {self.cochera.nombre} - {self.estado}"
    
TipoVehiculo = TipoEspacio
