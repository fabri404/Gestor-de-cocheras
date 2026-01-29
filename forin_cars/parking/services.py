from django.db import transaction
from .models import Espacio, ConfigCapacidad, TipoEspacio


def ensure_tipos_base():
    """
    Crea los tipos base si la tabla está vacía.
    Esto evita que el setup/ingreso quede sin opciones.
    """
    base = ["Auto", "Moto", "Camioneta", "Bicicleta"]
    for nombre in base:
        TipoEspacio.objects.get_or_create(nombre=nombre)


@transaction.atomic
def regenerar_espacios(cochera):
    """
    Genera espacios lógicos según ConfigCapacidad.
    Estrategia simple: borrar y recrear si NO hay movimientos abiertos.
    """
    abiertos = cochera.movimientos.filter(estado="ABIERTO").exists()
    if abiertos:
        raise ValueError("No se puede reconfigurar la cochera con movimientos abiertos.")

    capacidades = ConfigCapacidad.objects.filter(cochera=cochera).select_related("tipo")
    total = sum(c.cantidad for c in capacidades)
    if total <= 0:
        raise ValueError("Tenés que configurar al menos 1 espacio (algún tipo con cantidad > 0).")

    cochera.espacios.all().delete()

    bulk = []
    for cap in capacidades:
        for i in range(cap.cantidad):
            # etiqueta opcional por si querés verlos mejor en admin
            bulk.append(Espacio(cochera=cochera, tipo=cap.tipo, ocupado=False, etiqueta=f"{cap.tipo.nombre[:3].upper()}-{i+1}"))
    Espacio.objects.bulk_create(bulk)
