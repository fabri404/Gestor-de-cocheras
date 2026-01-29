from django.conf import settings
from django.db import models
from django.utils import timezone


class Cochera(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cocheras")
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=200, blank=True)
    activa = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.owner.username})"


class TipoEspacio(models.Model):
    """
    Auto / Moto / Camioneta / Bici, etc.
    Se puede precargar con data inicial luego.
    """
    nombre = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.nombre


class ConfigCapacidad(models.Model):
    """
    Para cada cochera, cuántos espacios tiene por tipo.
    Esto define el "mapa" lógico.
    """
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="capacidades")
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cochera", "tipo"], name="uq_capacidad_cochera_tipo")
        ]

    def __str__(self):
        return f"{self.cochera.nombre} - {self.tipo.nombre}: {self.cantidad}"


class Espacio(models.Model):
    """
    Espacios lógicos (no necesariamente numeración física).
    """
    cochera = models.ForeignKey(Cochera, on_delete=models.CASCADE, related_name="espacios")
    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)
    ocupado = models.BooleanField(default=False)

    # opcional: etiqueta/nro si quisieras
    etiqueta = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.cochera.nombre} - {self.tipo.nombre} - {'OCUPADO' if self.ocupado else 'LIBRE'}"


class Cliente(models.Model):
    """
    Minimalista: informacion basica para contacto.
    """
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

    # opcional: solo últimos 3 (guardamos como texto)
    patente_ult3 = models.CharField(max_length=3, blank=True, null=True)

    # obligatorio: identificador operativo interno (para egreso si no hay patente)
    ticket = models.CharField(max_length=20)

    tipo = models.ForeignKey(TipoEspacio, on_delete=models.PROTECT)

    class Meta:
        # evita duplicar ticket dentro del sistema (podés luego hacerlo por cochera)
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