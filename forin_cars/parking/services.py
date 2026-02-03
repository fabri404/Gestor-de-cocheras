from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model

from .models import (
    TipoEspacio,
    ConfigCapacidad,
    TarifaHora,
    InvitacionEmpleado,
    CocheraEmpleado,
    Espacio
)

User = get_user_model()


def ensure_default_tipos():
    defaults = ["Auto", "Moto", "Camioneta", "Bicicleta"]
    for n in defaults:
        TipoEspacio.objects.get_or_create(nombre=n)


@transaction.atomic
def upsert_capacidades(cochera, tipos, cap_cleaned):
    ConfigCapacidad.objects.filter(cochera=cochera).delete()
    for tipo in tipos:
        cantidad = cap_cleaned.get(f"tipo_{tipo.id}", 0)
        ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=cantidad)


@transaction.atomic
def upsert_tarifas(cochera, tipos, tarifa_cleaned):
    for tipo in tipos:
        precio = tarifa_cleaned.get(f"precio_{tipo.id}", 0)
        TarifaHora.objects.update_or_create(
            cochera=cochera,
            tipo=tipo,
            defaults={"precio_hora": precio},
        )


@transaction.atomic
def invitar_empleados(cochera, emails_list):
    # crea invitaciones y si el usuario ya existe, lo asigna al toque
    for email in emails_list:
        InvitacionEmpleado.objects.get_or_create(
            cochera=cochera,
            email=email,
            defaults={"estado": InvitacionEmpleado.PENDIENTE},
        )

        user = User.objects.filter(email__iexact=email).first()
        if user:
            CocheraEmpleado.objects.get_or_create(cochera=cochera, empleado=user)
            grp, _ = Group.objects.get_or_create(name="ADMIN_EMPLEADO")
            user.groups.add(grp)


@transaction.atomic
def apply_pending_invites(user):
    email = (user.email or "").strip().lower()
    if not email:
        return 0

    invites = InvitacionEmpleado.objects.filter(
        email__iexact=email,
        estado=InvitacionEmpleado.PENDIENTE,
    ).select_related("cochera")

    if not invites.exists():
        return 0

    grp, _ = Group.objects.get_or_create(name="ADMIN_EMPLEADO")
    user.groups.add(grp)

    count = 0
    for inv in invites:
        CocheraEmpleado.objects.get_or_create(cochera=inv.cochera, empleado=user)
        inv.estado = InvitacionEmpleado.ACEPTADA
        inv.accepted_by = user
        inv.accepted_at = timezone.now()
        inv.save(update_fields=["estado", "accepted_by", "accepted_at"])
        count += 1

    return count

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
