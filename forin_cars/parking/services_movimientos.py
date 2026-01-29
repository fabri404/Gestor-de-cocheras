from django.db import transaction
from django.utils import timezone
from .models import Vehiculo, Cliente, Movimiento, Espacio


def _normalize_ult3(value: str) -> str:
    v = (value or "").strip().upper()
    if not v:
        return ""
    if len(v) != 3:
        raise ValueError("La patente (últimos 3) debe tener exactamente 3 caracteres.")
    return v


def _has_cliente_data(cliente_data: dict) -> bool:
    if not cliente_data:
        return False
    return any((cliente_data.get(k) or "").strip() for k in ["nombre", "apellido", "telefono", "email"])


@transaction.atomic
def ingresar_vehiculo(*, cochera, operador, tipo, ticket, patente_ult3=None, cliente_data=None):
    ticket = (ticket or "").strip().upper()
    if not ticket:
        raise ValueError("El TICKET es obligatorio para identificar el vehículo.")

    ult3 = _normalize_ult3(patente_ult3)

    if cliente_data is None:
        cliente_data = {}

    # 1) buscar vehiculo existente por ticket (evita crear cliente al pedo)
    vehiculo = Vehiculo.objects.filter(ticket=ticket).select_related("cliente").first()

    if vehiculo is None:
        # crear cliente solo una vez por vehículo
        if _has_cliente_data(cliente_data):
            cliente = Cliente.objects.create(
                nombre=cliente_data.get("nombre", "").strip(),
                apellido=cliente_data.get("apellido", "").strip(),
                telefono=cliente_data.get("telefono", "").strip(),
                email=cliente_data.get("email", "").strip(),
            )
        else:
            cliente = Cliente.objects.create()  # placeholder mínimo

        vehiculo = Vehiculo.objects.create(
            ticket=ticket,
            cliente=cliente,
            tipo=tipo,
            patente_ult3=ult3,
        )
    else:
        # si lo reingresan, actualizamos tipo y ult3 si vino cargado
        vehiculo.tipo = tipo
        if ult3:
            vehiculo.patente_ult3 = ult3
        vehiculo.save()

    # evita doble “adentro”
    if Movimiento.objects.filter(cochera=cochera, vehiculo=vehiculo, estado="ABIERTO").exists():
        raise ValueError("Ese vehículo ya está dentro (movimiento ABIERTO).")

    # asignar espacio libre del tipo
    espacio = Espacio.objects.select_for_update().filter(
        cochera=cochera, tipo=tipo, ocupado=False
    ).first()

    if not espacio:
        raise ValueError(f"No hay espacios libres disponibles para tipo '{tipo.nombre}'.")

    espacio.ocupado = True
    espacio.save(update_fields=["ocupado"])

    mov = Movimiento.objects.create(
        cochera=cochera,
        vehiculo=vehiculo,
        espacio=espacio,
        operador=operador,
        estado="ABIERTO",
        ingreso_at=timezone.now(),
    )
    return mov


@transaction.atomic
def egresar_vehiculo(*, cochera, operador, ticket):
    ticket = (ticket or "").strip().upper()

    mov = Movimiento.objects.select_for_update().filter(
        cochera=cochera,
        vehiculo__ticket=ticket,
        estado="ABIERTO"
    ).select_related("espacio").first()

    if not mov:
        raise ValueError("No existe un movimiento ABIERTO para ese ticket en esta cochera.")

    espacio = mov.espacio
    espacio.ocupado = False
    espacio.save(update_fields=["ocupado"])

    mov.estado = "CERRADO"
    mov.egreso_at = timezone.now()
    mov.save(update_fields=["estado", "egreso_at"])

    return mov
