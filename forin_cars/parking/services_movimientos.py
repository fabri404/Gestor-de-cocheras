from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from .models import TarifaHora, Movimiento

import secrets
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import Vehiculo, Cliente, Movimiento, Espacio


def _normalize_ult3(value: str) -> str:
    v = (value or "").strip().upper()
    if not v:
        return ""
    if len(v) != 3:
        raise ValueError("La patente (últimos 3) debe tener exactamente 3 caracteres.")
    return v


def _has_cliente_data(cliente_data: dict | None) -> bool:
    if not cliente_data:
        return False
    return any((cliente_data.get(k) or "").strip() for k in ["nombre", "apellido", "telefono", "email"])


def generar_ticket_unico(prefix: str = "TKT") -> str:
    # 8 hex => 32 bits, suficiente para uso normal. Si querés aún menos colisión, subí a 10/12 hex.
    return f"{prefix}-{secrets.token_hex(4).upper()}"


@transaction.atomic
def ingresar_vehiculo(*, cochera, operador, tipo, ticket="", patente_ult3="", cliente_data=None, ticket_prefix="", horas_previstas=1):
    """
    - ticket: si viene vacío/None => se genera automático y único.
    - tipo: debería ser tu TipoEspacio/TipoVehiculo según tu modelo (lo que uses en Espacio.tipo)
    """
    
    horas_previstas = int(horas_previstas or 1)
    if horas_previstas < 1:
        raise ValueError("Horas inválidas.")

    # Buscar tarifa por cochera + tipo
    tarifa = TarifaHora.objects.filter(cochera=cochera, tipo=tipo).first()
    if not tarifa:
        raise ValueError("No hay tarifa configurada para este tipo de vehículo.")

    precio_hora = Decimal(tarifa.precio_hora)
    ahora = timezone.now()

    ult3 = _normalize_ult3(patente_ult3)

    # Si el ticket viene vacío: generamos uno y lo garantizamos contra colisiones por unique constraint
    ticket_norm = (ticket or "").strip().upper()
    if not ticket_norm:
        # Intentamos crear un Vehiculo nuevo con ticket único; si colisiona, reintenta.
        ticket_norm = None

    if cliente_data is None:
        cliente_data = {}

    # 1) Si vino ticket, intentamos buscar vehiculo existente por ticket
    vehiculo = None
    if ticket_norm:
        vehiculo = Vehiculo.objects.filter(ticket=ticket_norm).select_related("cliente").first()

    if vehiculo is None:
        # Crear cliente (solo una vez por vehículo)
        if _has_cliente_data(cliente_data):
            cliente = Cliente.objects.create(
                nombre=cliente_data.get("nombre", "").strip(),
                apellido=cliente_data.get("apellido", "").strip(),
                telefono=cliente_data.get("telefono", "").strip(),
                email=cliente_data.get("email", "").strip(),
            )
        else:
            cliente = Cliente.objects.create()

        # Crear vehiculo con ticket único (si no vino, generamos)
        if not ticket_norm:
            for _ in range(20):
                candidate = generar_ticket_unico()
                try:
                    vehiculo = Vehiculo.objects.create(
                        ticket=candidate,
                        cliente=cliente,
                        tipo=tipo,
                        patente_ult3=ult3,
                    )
                    ticket_norm = candidate
                    break
                except IntegrityError:
                    # ticket duplicado (muy raro) => reintentar
                    continue
            else:
                raise ValueError("No se pudo generar un ticket único. Reintentá.")
        else:
            vehiculo = Vehiculo.objects.create(
                ticket=ticket_norm,
                cliente=cliente,
                tipo=tipo,
                patente_ult3=ult3,
            )
    else:
        # Si lo reingresan (mismo ticket), actualizamos tipo y ult3 si vino cargado
        vehiculo.tipo = tipo
        if ult3:
            vehiculo.patente_ult3 = ult3
        vehiculo.save()

    # Evita doble “adentro”
    if Movimiento.objects.filter(cochera=cochera, vehiculo=vehiculo, estado="ABIERTO").exists():
        raise ValueError("Ese vehículo ya está dentro (movimiento ABIERTO).")

    # Asignar espacio libre del tipo
    espacio = Espacio.objects.select_for_update().filter(
        cochera=cochera, tipo=tipo, ocupado=False
    ).first()

    if not espacio:
        raise ValueError(f"No hay espacios libres disponibles para tipo '{getattr(tipo, 'nombre', tipo)}'.")

    espacio.ocupado = True
    espacio.save(update_fields=["ocupado"])

    mov = Movimiento.objects.create(
        cochera=cochera,
        vehiculo=vehiculo,
        espacio=espacio,
        operador=operador,
        ingreso_at=ahora,
        horas_previstas=horas_previstas,
        tarifa_hora_aplicada=precio_hora,
        monto_estimado=(precio_hora * Decimal(horas_previstas)),
        egreso_estimado_at=(ahora + timedelta(hours=horas_previstas)),
    )
    return mov


@transaction.atomic
def egresar_vehiculo(*, cochera, operador, ticket: str):
    ticket = (ticket or "").strip().upper()

    mov = Movimiento.objects.select_for_update().filter(
        cochera=cochera,
        vehiculo__ticket=ticket,
        estado="ABIERTO",
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
