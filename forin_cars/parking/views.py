from io import BytesIO
import secrets
from urllib.parse import urlencode
import base64
import json

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import FieldError
from django.core.signing import BadSignature, Signer
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, Max
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    CapacidadForm,
    ChecklistItemForm,
    ClienteForm,
    CocheraForm,
    EmpleadosForm,
    FotoOrdenForm,
    MembresiaForm,
    MovimientoInventarioForm,
    OrdenTrabajoForm,
    PlanForm,
    ProductoForm,
    PublicIngresoForm,
    ServicioForm,
    TarifaForm,
    TurnoForm,
    VehiculoForm,
)
from .models import (
    Cochera,
    Cliente,
    Vehiculo,
    TipoEspacio,
    TarifaHora,
    Servicio,
    OrdenTrabajo,
    OrdenServicio,
    Turno,
    ChecklistItem,
    OrdenChecklist,
    FotoOrden,
    CategoriaProducto,
    Producto,
    MovimientoInventario,
    Plan,
    Membresia,
)
from .services import (
    ensure_default_tipos,
    invitar_empleados,
    regenerar_espacios,
    upsert_capacidades,
    upsert_tarifas,
)
from .services_movimientos import egresar_vehiculo, ingresar_vehiculo
from .pdf_utils import build_movimiento_pdf_bytes


# =========================
# Config
# =========================

QR_SIGNER = Signer(salt="forin_cars_parking_qr")

URL_INGRESO_PUBLIC = "parking:ingreso_public"
URL_COCHERA_QR_PNG = "parking:cochera_qr_png"
URL_DASHBOARD = "dashboard"


# =========================
# Helpers / permisos
# =========================

def _tarifas_json_for_cochera(cochera) -> str:
    qs = TarifaHora.objects.filter(cochera=cochera).values_list("tipo_id", "precio_hora")
    # str() para evitar problemas con Decimal en JSON
    return json.dumps({str(tipo_id): str(precio) for tipo_id, precio in qs})



def is_admin_dueno(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name="ADMIN_DUENO").exists()


def can_operate(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["ADMIN_DUENO", "ADMIN_EMPLEADO"]).exists()


def cochera_queryset_for(user):
    """
    Dueño ve sus cocheras. Empleado ve asignadas.
    Soporta:
      - owner: FK(User)
      - empleados: M2M(User) (si existe)
      - cocheraempleado__empleado: relación intermedia (si existe)
    """
    if user.is_superuser:
        return Cochera.objects.all()

    q = Q(owner=user)

    # Si el campo no existe en tu modelo, no explota: se ignora
    try:
        Cochera.objects.filter(empleados=user)  # solo para testear FieldError
        q |= Q(empleados=user)
    except FieldError:
        pass

    try:
        Cochera.objects.filter(cocheraempleado__empleado=user)
        q |= Q(cocheraempleado__empleado=user)
    except FieldError:
        pass

    return Cochera.objects.filter(q).distinct()


def _signed_token_for_cochera(cochera_id: int) -> str:
    return QR_SIGNER.sign(str(cochera_id))


def _validate_token_for_cochera(request, cochera_id: int):
    """
    Valida token ?t=... contra cochera_id.
    Devuelve (token, None) si OK, o (None, HttpResponseForbidden) si falla.
    """
    token = request.GET.get("t")
    if not token:
        return None, HttpResponseForbidden("Token faltante.")

    try:
        unsigned = QR_SIGNER.unsign(token)
    except BadSignature:
        return None, HttpResponseForbidden("Token inválido.")

    if str(unsigned) != str(cochera_id):
        return None, HttpResponseForbidden("Token inválido.")

    return token, None


def _qr_png_response(url: str) -> HttpResponse:
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


# =========================
# QR: página + PNG
# =========================

def _public_ingreso_url(request, cochera_id: int, token: str) -> str:
    path = reverse("parking:ingreso_public", kwargs={"cochera_id": cochera_id})
    url = request.build_absolute_uri(path)
    return url + "?" + urlencode({"t": token})


@login_required
def cochera_qr_view(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    token = _signed_token_for_cochera(cochera.id)
    public_url = _public_ingreso_url(request, cochera.id, token)

    # Generar QR embebido (base64) para NO depender de un endpoint PNG
    img = qrcode.make(public_url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return render(
        request,
        "parking/cochera_qr.html",
        {
            "cochera": cochera,
            "public_url": public_url,
            "qr_b64": qr_b64,
        },
    )


@login_required
def cochera_qr_png_view(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    token, forbidden = _validate_token_for_cochera(request, cochera.id)
    if forbidden:
        return forbidden

    return _qr_png_response(_public_ingreso_url(request, cochera.id, token))


def _gen_ticket_publico() -> str:
    # <= 20 chars (tu modelo limita ticket a 20)
    return "QR-" + secrets.token_hex(4).upper()  # ej: QR-1A2B3C4D

def ingreso_public_view(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id)
    
    horas = int(request.POST.get("horas") or 1)

    token = request.GET.get("t", "")
    try:
        unsigned = QR_SIGNER.unsign(token)
        if str(cochera.id) != str(unsigned):
            return HttpResponseForbidden("Token inválido.")
    except BadSignature:
        return HttpResponseForbidden("Token inválido.")

    tipos = TipoEspacio.objects.all().order_by("nombre")

    if request.method == "POST":
        tipo_id = request.POST.get("tipo_id")
        # en público, si no mandan ticket, lo generamos
        ticket = request.POST.get("ticket", "").strip() or _gen_ticket_publico()
        patente_ult3 = request.POST.get("patente_ult3", "")

        try:
            tipo = TipoEspacio.objects.get(id=tipo_id)

            ingresar_vehiculo(
                cochera=cochera,
                operador=cochera.owner,  # no hay login, guardamos como operador el dueño
                tipo=tipo,
                ticket=ticket,
                patente_ult3=patente_ult3,
                cliente_data={
                    "nombre": request.POST.get("nombre", ""),
                    "apellido": request.POST.get("apellido", ""),
                    "telefono": request.POST.get("telefono", ""),
                    "email": request.POST.get("email", ""),
                },
            )

            messages.success(request, "Ingreso cargado correctamente. ¡Gracias!")
            # redirigimos al mismo form manteniendo el token
            return redirect(
                reverse("parking:ingreso_public", kwargs={"cochera_id": cochera.id})
                + "?"
                + urlencode({"t": token})
            )

        except ValueError as e:
            messages.error(request, str(e))
        except TipoEspacio.DoesNotExist:
            messages.error(request, "Tipo de vehículo inválido.")

    tarifas_json = _tarifas_json_for_cochera(cochera)

    # GET (o si hubo error): precargamos un ticket para que el form no falle
    ctx = {
        "cochera": cochera,
        "tipos": tipos,
        "public_mode": True,
        "ticket_prefill": _gen_ticket_publico(),
        "public_token": token,
        "tarifas_json": tarifas_json,
    }
    return render(request, "parking/ingreso.html", ctx)

# =========================
# CRUD Cochera (unificado)
# =========================

def _cochera_upsert_view(request, *, title: str, cochera=None):
    """
    Unifica crear/editar evitando duplicación.
    - cochera=None => create
    - cochera=instance => edit
    """
    ensure_default_tipos()
    tipos = TipoEspacio.objects.all().order_by("nombre")

    is_edit = cochera is not None

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST, instance=cochera if is_edit else None)
        cap_form = CapacidadForm(request.POST, tipos=tipos)
        tarifa_form = TarifaForm(request.POST, tipos=tipos)
        empleados_form = EmpleadosForm(request.POST)

        if all([cochera_form.is_valid(), cap_form.is_valid(), tarifa_form.is_valid(), empleados_form.is_valid()]):
            if is_edit:
                cochera = cochera_form.save()
            else:
                cochera = cochera_form.save(commit=False)
                cochera.owner = request.user
                cochera.save()

            upsert_capacidades(cochera, tipos, cap_form.cleaned_data)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_edit" if is_edit else "cochera_new", cochera_id=getattr(cochera, "id", None))

            upsert_tarifas(cochera, tipos, tarifa_form.cleaned_data)

            emails_list = empleados_form.cleaned_data.get("emails_list") or []
            if emails_list:
                invitar_empleados(cochera, emails_list)

            messages.success(
                request,
                "Cochera actualizada correctamente." if is_edit else "Cochera creada y configurada correctamente.",
            )
            return redirect(URL_DASHBOARD)

    else:
        cochera_form = CocheraForm(instance=cochera if is_edit else None)

        if is_edit:
            cap_map = {c.tipo_id: c.cantidad for c in cochera.capacidades.all()}
            tarifa_map = {t.tipo_id: t.precio_hora for t in cochera.tarifas.all()}

            cap_initial = {f"tipo_{tipo.id}": cap_map.get(tipo.id, 0) for tipo in tipos}
            tarifa_initial = {f"precio_{tipo.id}": tarifa_map.get(tipo.id, 0) for tipo in tipos}

            cap_form = CapacidadForm(tipos=tipos, initial=cap_initial)
            tarifa_form = TarifaForm(tipos=tipos, initial=tarifa_initial)
        else:
            cap_form = CapacidadForm(tipos=tipos)
            tarifa_form = TarifaForm(tipos=tipos)

        empleados_form = EmpleadosForm()

    return render(
        request,
        "parking/cochera_form.html",
        {
            "title": title,
            "cochera": cochera,
            "cochera_form": cochera_form,
            "cap_form": cap_form,
            "tarifa_form": tarifa_form,
            "empleados_form": empleados_form,
        },
    )


@login_required
@user_passes_test(is_admin_dueno)
def cochera_new(request):
    return _cochera_upsert_view(request, title="Crear cochera", cochera=None)


@login_required
@user_passes_test(is_admin_dueno)
def cochera_edit(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    return _cochera_upsert_view(request, title="Editar cochera", cochera=cochera)


@login_required
def cochera_detail(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    tarifas = TarifaHora.objects.filter(cochera=cochera).select_related("tipo").order_by("tipo__nombre")
    capacidades = cochera.capacidades.select_related("tipo").order_by("tipo__nombre")
    empleados = cochera.empleados.all().order_by("username") if hasattr(cochera, "empleados") else []

    return render(
        request,
        "parking/cochera_detail.html",
        {"cochera": cochera, "tarifas": tarifas, "capacidades": capacidades, "empleados": empleados},
    )


@login_required
@user_passes_test(can_operate)
def cochera_live(request, cochera_id: int):
    """Panel en vivo: espacios, vehículos adentro, modalidad de pago."""
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    # Espacios con su movimiento activo (si tiene)
    espacios = (
        Espacio.objects.filter(cochera=cochera)
        .select_related("tipo")
        .prefetch_related(
            models.Prefetch(
                "movimientos",
                queryset=Movimiento.objects.filter(estado=Movimiento.ABIERTO)
                .select_related("vehiculo__cliente", "vehiculo__tipo", "membresia__plan"),
                to_attr="mov_activo_list",
            )
        )
        .order_by("tipo__nombre", "etiqueta")
    )

    # Armar lista enriquecida
    espacios_info = []
    for esp in espacios:
        mov = esp.mov_activo_list[0] if esp.mov_activo_list else None
        espacios_info.append({
            "espacio": esp,
            "mov": mov,
            "horas": round(mov.horas_transcurridas(), 1) if mov else None,
            "monto": mov.monto_acumulado() if mov else None,
        })

    # Membresías activas de esta cochera
    membresias_activas = (
        Membresia.objects.filter(plan__cochera=cochera, estado=Membresia.ACTIVA)
        .select_related("cliente", "plan")
        .order_by("fecha_vencimiento")
    )

    # Resumen por tipo de pago
    movs_abiertos = Movimiento.objects.filter(cochera=cochera, estado=Movimiento.ABIERTO)
    por_hora_count = movs_abiertos.filter(tipo_pago=Movimiento.HORA).count()
    por_membresia_count = movs_abiertos.filter(tipo_pago=Movimiento.MEMBRESIA).count()

    total = len(espacios_info)
    ocupados = sum(1 for e in espacios_info if e["mov"])

    return render(request, "parking/cochera_live.html", {
        "cochera": cochera,
        "espacios_info": espacios_info,
        "total": total,
        "ocupados": ocupados,
        "libres": total - ocupados,
        "por_hora_count": por_hora_count,
        "por_membresia_count": por_membresia_count,
        "membresias_activas": membresias_activas,
    })


# =========================
# Operación: seleccionar cochera
# =========================

def _select_cochera_view(request, *, title: str, target_url_name: str):
    qs = cochera_queryset_for(request.user).filter(activa=True).order_by("-created_at")

    first_two = list(qs[:2])
    if not first_two:
        messages.info(request, "No tenés cocheras asignadas para operar.")
        return redirect(URL_DASHBOARD)

    if len(first_two) == 1:
        return redirect(target_url_name, cochera_id=first_two[0].id)

    # Solo si hay 2 o más, traigo todas para la vista
    cocheras = list(qs)
    return render(
        request,
        "parking/select_cochera.html",
        {"title": title, "cocheras": cocheras, "target": target_url_name},
    )


@login_required
@user_passes_test(can_operate)
def ingreso_select_cochera_view(request):
    return _select_cochera_view(request, title="Elegí cochera para INGRESO", target_url_name="ingreso_cochera")


@login_required
@user_passes_test(can_operate)
def egreso_select_cochera_view(request):
    return _select_cochera_view(request, title="Elegí cochera para EGRESO", target_url_name="egreso_cochera")


# =========================
# Operación: ingreso / egreso
# =========================


@login_required
@user_passes_test(can_operate)
def ingreso_view(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    tipos = TipoEspacio.objects.all().order_by("nombre")
    membresias_activas = (
        Membresia.objects.filter(plan__cochera=cochera, estado=Membresia.ACTIVA)
        .select_related("cliente", "plan")
        .order_by("cliente__nombre")
    )

    if request.method == "POST":
        tipo_id = request.POST.get("tipo_id")
        ticket = request.POST.get("ticket", "")
        patente_ult3 = request.POST.get("patente_ult3", "")
        tipo_pago = request.POST.get("tipo_pago", Movimiento.HORA)
        membresia_id = request.POST.get("membresia_id") or None

        horas = int(request.POST.get("horas") or 1)
        if horas < 1:
            messages.error(request, "Horas inválidas.")
            return redirect(request.path)

        if not tipo_id:
            messages.error(request, "Tipo de vehículo requerido.")
        else:
            try:
                tipo = TipoEspacio.objects.get(id=tipo_id)

                membresia_obj = None
                if tipo_pago == Movimiento.MEMBRESIA and membresia_id:
                    membresia_obj = Membresia.objects.filter(
                        id=membresia_id, plan__cochera=cochera, estado=Membresia.ACTIVA
                    ).first()

                mov = ingresar_vehiculo(
                    cochera=cochera,
                    operador=request.user,
                    tipo=tipo,
                    ticket=ticket,
                    patente_ult3=patente_ult3,
                    horas_previstas=horas,
                    cliente_data={
                        "nombre": request.POST.get("nombre", ""),
                        "apellido": request.POST.get("apellido", ""),
                        "telefono": request.POST.get("telefono", ""),
                        "email": request.POST.get("email", ""),
                    },
                )

                # Guardar modalidad de pago
                mov.tipo_pago = tipo_pago
                mov.membresia = membresia_obj
                if tipo_pago == Movimiento.MEMBRESIA:
                    mov.monto_estimado = 0
                mov.save(update_fields=["tipo_pago", "membresia", "monto_estimado"])

                pdf_bytes = build_movimiento_pdf_bytes(mov, horas_previstas=horas)
                resp = HttpResponse(pdf_bytes, content_type="application/pdf")
                resp["Content-Disposition"] = f'attachment; filename="ticket-{mov.vehiculo.ticket}.pdf"'
                return resp

            except TipoEspacio.DoesNotExist:
                messages.error(request, "Tipo de vehículo inválido.")
            except ValueError as e:
                messages.error(request, str(e))

    tarifas_json = _tarifas_json_for_cochera(cochera)
    return render(
        request,
        "parking/ingreso.html",
        {
            "cochera": cochera,
            "tipos": tipos,
            "tarifas_json": tarifas_json,
            "membresias_activas": membresias_activas,
        },
    )   

@login_required
@user_passes_test(can_operate)
def egreso_view(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    # Pre-fill ticket from QS param (link desde cochera_live)
    ticket_qs = request.GET.get("ticket", "")

    if request.method == "POST":
        ticket = request.POST.get("ticket", "")
        try:
            mov = egresar_vehiculo(cochera=cochera, operador=request.user, ticket=ticket)

            # Calcular y guardar monto cobrado real
            if mov.tipo_pago == Movimiento.HORA:
                monto = mov.monto_acumulado()
            else:
                monto = 0
            mov.monto_cobrado = monto
            mov.pagado = True
            mov.save(update_fields=["monto_cobrado", "pagado"])

            messages.success(request, f"Egreso OK.{' Cobrado: $' + str(monto) if monto else ' Membresía, sin cargo.'}")
            return redirect("parking:cochera_live", cochera_id=cochera.id)
        except (ValueError, AttributeError) as e:
            messages.error(request, str(e))

    return render(request, "parking/egreso.html", {"cochera": cochera, "ticket_prefill": ticket_qs})


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Servicios
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def servicios_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    servicios = Servicio.objects.filter(cochera=cochera).order_by("categoria", "nombre")
    return render(request, "parking/servicios_list.html", {"cochera": cochera, "servicios": servicios})


@login_required
@user_passes_test(is_admin_dueno)
def servicio_form_view(request, cochera_id: int, servicio_id: int = None):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    instance = None
    if servicio_id:
        instance = get_object_or_404(Servicio, id=servicio_id, cochera=cochera)

    if request.method == "POST":
        form = ServicioForm(request.POST, instance=instance)
        if form.is_valid():
            srv = form.save(commit=False)
            srv.cochera = cochera
            srv.save()
            messages.success(request, "Servicio guardado.")
            return redirect("parking:servicios_list", cochera_id=cochera.id)
    else:
        form = ServicioForm(instance=instance)

    return render(request, "parking/servicio_form.html", {
        "cochera": cochera,
        "form": form,
        "is_edit": instance is not None,
        "servicio": instance,
    })


@login_required
@user_passes_test(is_admin_dueno)
def servicio_toggle(request, cochera_id: int, servicio_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    srv = get_object_or_404(Servicio, id=servicio_id, cochera=cochera)
    srv.activo = not srv.activo
    srv.save(update_fields=["activo"])
    messages.success(request, f"Servicio {'activado' if srv.activo else 'desactivado'}.")
    return redirect("parking:servicios_list", cochera_id=cochera.id)


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Clientes
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def clientes_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("filtro", "todos")  # todos | membresia | hora | pagado

    # Base: clientes que tienen movimientos O órdenes en esta cochera
    qs = Cliente.objects.filter(
        Q(ordenes__cochera=cochera) | Q(vehiculos__movimientos__cochera=cochera)
    ).distinct().order_by("nombre", "apellido")

    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(apellido__icontains=q)
            | Q(telefono__icontains=q) | Q(email__icontains=q)
        )

    if filtro == "membresia":
        qs = qs.filter(membresias__plan__cochera=cochera, membresias__estado=Membresia.ACTIVA).distinct()
    elif filtro == "hora":
        qs = qs.filter(
            vehiculos__movimientos__cochera=cochera,
            vehiculos__movimientos__tipo_pago=Movimiento.HORA,
        ).distinct()
    elif filtro == "pagado":
        qs = qs.filter(
            vehiculos__movimientos__cochera=cochera,
            vehiculos__movimientos__pagado=True,
        ).distinct()

    # Anotar si tienen membresía activa
    clientes_data = []
    ids = list(qs.values_list("id", flat=True))
    membs_activas = {
        m.cliente_id: m
        for m in Membresia.objects.filter(
            cliente_id__in=ids, plan__cochera=cochera, estado=Membresia.ACTIVA
        ).select_related("plan")
    }
    for c in qs:
        clientes_data.append({
            "cliente": c,
            "membresia": membs_activas.get(c.id),
        })

    return render(request, "parking/clientes_list.html", {
        "cochera": cochera,
        "clientes_data": clientes_data,
        "q": q,
        "filtro": filtro,
        "filtros": [
            ("todos", "Todos"),
            ("membresia", "Membresía activa"),
            ("hora", "Por hora"),
            ("pagado", "Ya pagaron"),
        ],
    })


@login_required
@user_passes_test(can_operate)
def cliente_detail(request, cochera_id: int, cliente_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    cliente = get_object_or_404(Cliente, id=cliente_id)
    ordenes = OrdenTrabajo.objects.filter(cochera=cochera, cliente=cliente).prefetch_related(
        "ordenservicio_set__servicio"
    )
    vehiculos = Vehiculo.objects.filter(cliente=cliente).distinct()
    return render(request, "parking/cliente_detail.html", {
        "cochera": cochera,
        "cliente": cliente,
        "ordenes": ordenes,
        "vehiculos": vehiculos,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Órdenes de Trabajo
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def ordenes_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    estado = request.GET.get("estado", "")
    qs = OrdenTrabajo.objects.filter(cochera=cochera).select_related(
        "cliente", "vehiculo", "operador"
    ).prefetch_related("ordenservicio_set__servicio")

    if estado:
        qs = qs.filter(estado=estado)

    totales = {
        "PENDIENTE": qs.filter(estado="PENDIENTE").count() if not estado else None,
        "EN_PROCESO": qs.filter(estado="EN_PROCESO").count() if not estado else None,
        "FINALIZADO": qs.filter(estado="FINALIZADO").count() if not estado else None,
        "CANCELADO": qs.filter(estado="CANCELADO").count() if not estado else None,
    } if not estado else {}

    return render(request, "parking/ordenes_list.html", {
        "cochera": cochera,
        "ordenes": qs[:50],
        "estado_filtro": estado,
        "estados": OrdenTrabajo.ESTADOS,
        "totales": totales,
    })


@login_required
@user_passes_test(can_operate)
def orden_new(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    servicios_qs = Servicio.objects.filter(cochera=cochera, activo=True).order_by("categoria", "nombre")

    if not servicios_qs.exists():
        messages.warning(request, "Primero cargá al menos un servicio en el catálogo.")
        return redirect("parking:servicios_list", cochera_id=cochera.id)

    if request.method == "POST":
        form = OrdenTrabajoForm(request.POST, cochera=cochera)
        servicios_ids = request.POST.getlist("servicios")

        if not servicios_ids:
            messages.error(request, "Seleccioná al menos un servicio.")
        elif form.is_valid():
            try:
                orden = _crear_orden_trabajo(
                    cochera=cochera,
                    operador=request.user,
                    form_data=form.cleaned_data,
                    servicios_ids=servicios_ids,
                )
                messages.success(request, f"Orden {orden.numero} creada correctamente.")
                return redirect("parking:orden_detail", cochera_id=cochera.id, orden_id=orden.id)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OrdenTrabajoForm(cochera=cochera)

    return render(request, "parking/orden_form.html", {
        "cochera": cochera,
        "form": form,
        "servicios": servicios_qs,
    })


@transaction.atomic
def _crear_orden_trabajo(*, cochera, operador, form_data, servicios_ids):
    patente = (form_data.get("vehiculo_patente") or "").strip().upper()

    vehiculo = Vehiculo.objects.filter(patente=patente).select_related("cliente").first()

    if vehiculo:
        cliente = vehiculo.cliente
        vehiculo.marca = form_data.get("vehiculo_marca", vehiculo.marca)
        vehiculo.modelo = form_data.get("vehiculo_modelo", vehiculo.modelo)
        vehiculo.color = form_data.get("vehiculo_color", vehiculo.color)
        if form_data.get("vehiculo_anio"):
            vehiculo.anio = form_data["vehiculo_anio"]
        vehiculo.tipo = form_data["vehiculo_tipo"]
        vehiculo.save()
    else:
        nombre = (form_data.get("cliente_nombre") or "").strip()
        apellido = (form_data.get("cliente_apellido") or "").strip()
        telefono = (form_data.get("cliente_telefono") or "").strip()
        email = (form_data.get("cliente_email") or "").strip().lower()
        cliente = Cliente.objects.create(
            nombre=nombre, apellido=apellido, telefono=telefono, email=email
        )
        vehiculo = Vehiculo.objects.create(
            cliente=cliente,
            patente=patente,
            patente_ult3=patente[-3:] if len(patente) >= 3 else patente,
            marca=form_data.get("vehiculo_marca", ""),
            modelo=form_data.get("vehiculo_modelo", ""),
            anio=form_data.get("vehiculo_anio"),
            color=form_data.get("vehiculo_color", ""),
            tipo=form_data["vehiculo_tipo"],
            ticket="OT-" + secrets.token_hex(4).upper(),
        )

    servicios = Servicio.objects.filter(id__in=servicios_ids, cochera=cochera, activo=True)
    if not servicios.exists():
        raise ValueError("Ninguno de los servicios seleccionados es válido.")

    orden = OrdenTrabajo.objects.create(
        cochera=cochera,
        cliente=cliente,
        vehiculo=vehiculo,
        operador=operador,
        observaciones=form_data.get("observaciones", ""),
        entrega_estimada_at=form_data.get("entrega_estimada_at"),
    )

    total = 0
    for srv in servicios:
        OrdenServicio.objects.create(orden=orden, servicio=srv, precio_aplicado=srv.precio)
        total += srv.precio
    orden.monto_total = total
    orden.save(update_fields=["monto_total"])

    # Auto-poblar checklist con los items activos de la cochera
    items = ChecklistItem.objects.filter(cochera=cochera, activo=True)
    OrdenChecklist.objects.bulk_create([
        OrdenChecklist(orden=orden, item=item) for item in items
    ])

    return orden


@login_required
@user_passes_test(can_operate)
def orden_detail(request, cochera_id: int, orden_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    orden = get_object_or_404(OrdenTrabajo, id=orden_id, cochera=cochera)
    servicios_orden = orden.ordenservicio_set.select_related("servicio").all()
    return render(request, "parking/orden_detail.html", {
        "cochera": cochera,
        "orden": orden,
        "servicios_orden": servicios_orden,
    })


@login_required
@user_passes_test(can_operate)
def orden_cambiar_estado(request, cochera_id: int, orden_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    orden = get_object_or_404(OrdenTrabajo, id=orden_id, cochera=cochera)

    if request.method == "POST":
        nuevo_estado = request.POST.get("estado")
        estados_validos = [e[0] for e in OrdenTrabajo.ESTADOS]
        if nuevo_estado not in estados_validos:
            messages.error(request, "Estado inválido.")
        else:
            orden.estado = nuevo_estado
            if nuevo_estado == OrdenTrabajo.FINALIZADO and not orden.entregado_at:
                orden.entregado_at = timezone.now()
            orden.save(update_fields=["estado", "entregado_at"])
            messages.success(request, f"Estado actualizado a {orden.get_estado_display()}.")

    return redirect("parking:orden_detail", cochera_id=cochera.id, orden_id=orden.id)


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Turnos
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def turnos_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    fecha_str = request.GET.get("fecha", "")
    qs = Turno.objects.filter(cochera=cochera).select_related(
        "cliente", "vehiculo", "operador"
    )
    if fecha_str:
        qs = qs.filter(fecha=fecha_str)
    else:
        qs = qs.filter(fecha__gte=timezone.localdate())
    return render(request, "parking/turnos_list.html", {
        "cochera": cochera,
        "turnos": qs[:100],
        "fecha_filtro": fecha_str,
        "estados": Turno.ESTADOS,
    })


@login_required
@user_passes_test(can_operate)
def turno_new(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    if request.method == "POST":
        form = TurnoForm(request.POST, cochera=cochera)
        patente = (request.POST.get("vehiculo_patente") or "").strip().upper()
        cliente_nombre = (request.POST.get("cliente_nombre") or "").strip()
        cliente_telefono = (request.POST.get("cliente_telefono") or "").strip()

        if form.is_valid():
            vehiculo = Vehiculo.objects.filter(patente=patente).first()
            if not vehiculo:
                tipo_id = request.POST.get("vehiculo_tipo")
                try:
                    tipo = TipoEspacio.objects.get(id=tipo_id)
                except TipoEspacio.DoesNotExist:
                    messages.error(request, "Tipo de vehículo inválido.")
                    return render(request, "parking/turno_form.html", {
                        "cochera": cochera, "form": form,
                        "tipos": TipoEspacio.objects.all().order_by("nombre"),
                    })
                cliente = Cliente.objects.create(nombre=cliente_nombre, telefono=cliente_telefono)
                vehiculo = Vehiculo.objects.create(
                    cliente=cliente,
                    patente=patente,
                    patente_ult3=patente[-3:] if len(patente) >= 3 else patente,
                    tipo=tipo,
                    ticket="T-" + secrets.token_hex(4).upper(),
                )
            turno = form.save(commit=False)
            turno.cochera = cochera
            turno.cliente = vehiculo.cliente
            turno.vehiculo = vehiculo
            turno.save()
            messages.success(request, "Turno creado.")
            return redirect("parking:turnos_list", cochera_id=cochera.id)
    else:
        form = TurnoForm(cochera=cochera)

    return render(request, "parking/turno_form.html", {
        "cochera": cochera,
        "form": form,
        "tipos": TipoEspacio.objects.all().order_by("nombre"),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Checklist
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(is_admin_dueno)
def checklist_config(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    items = ChecklistItem.objects.filter(cochera=cochera)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            desc = request.POST.get("descripcion", "").strip()
            if desc:
                orden_max = items.aggregate(m=models.Max("orden"))["m"] or 0
                ChecklistItem.objects.create(cochera=cochera, descripcion=desc, orden=orden_max + 1)
                messages.success(request, "Item agregado.")
        elif action == "toggle":
            item_id = request.POST.get("item_id")
            item = get_object_or_404(ChecklistItem, id=item_id, cochera=cochera)
            item.activo = not item.activo
            item.save(update_fields=["activo"])
        elif action == "delete":
            item_id = request.POST.get("item_id")
            get_object_or_404(ChecklistItem, id=item_id, cochera=cochera).delete()
            messages.success(request, "Item eliminado.")
        return redirect("parking:checklist_config", cochera_id=cochera.id)

    return render(request, "parking/checklist_config.html", {
        "cochera": cochera, "items": items
    })


@login_required
@user_passes_test(can_operate)
def orden_checklist(request, cochera_id: int, orden_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    orden = get_object_or_404(OrdenTrabajo, id=orden_id, cochera=cochera)

    if request.method == "POST":
        for key, val in request.POST.items():
            if key.startswith("item_"):
                item_id = key.split("_")[1]
                oc = OrdenChecklist.objects.filter(orden=orden, item_id=item_id).first()
                if oc:
                    oc.completado = (val == "1")
                    oc.observacion = request.POST.get(f"obs_{item_id}", "")
                    oc.save(update_fields=["completado", "observacion"])
        messages.success(request, "Checklist guardado.")
        return redirect("parking:orden_detail", cochera_id=cochera.id, orden_id=orden.id)

    checklist = orden.checklist.select_related("item").all()
    return render(request, "parking/orden_checklist.html", {
        "cochera": cochera, "orden": orden, "checklist": checklist
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Fotos
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def orden_foto_upload(request, cochera_id: int, orden_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    orden = get_object_or_404(OrdenTrabajo, id=orden_id, cochera=cochera)

    if request.method == "POST":
        form = FotoOrdenForm(request.POST, request.FILES)
        if form.is_valid():
            foto = form.save(commit=False)
            foto.orden = orden
            foto.save()
            messages.success(request, "Foto subida.")
        else:
            messages.error(request, "Error al subir la foto.")
    return redirect("parking:orden_detail", cochera_id=cochera.id, orden_id=orden.id)


@login_required
@user_passes_test(can_operate)
def orden_foto_delete(request, cochera_id: int, orden_id: int, foto_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    orden = get_object_or_404(OrdenTrabajo, id=orden_id, cochera=cochera)
    foto = get_object_or_404(FotoOrden, id=foto_id, orden=orden)
    if request.method == "POST":
        foto.imagen.delete(save=False)
        foto.delete()
        messages.success(request, "Foto eliminada.")
    return redirect("parking:orden_detail", cochera_id=cochera.id, orden_id=orden.id)


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Inventario
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def inventario_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    productos = Producto.objects.filter(cochera=cochera).select_related("categoria")
    bajo_stock = [p for p in productos if p.bajo_stock]
    return render(request, "parking/inventario_list.html", {
        "cochera": cochera,
        "productos": productos,
        "bajo_stock": bajo_stock,
    })


@login_required
@user_passes_test(is_admin_dueno)
def producto_form_view(request, cochera_id: int, producto_id: int = None):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    instance = None
    if producto_id:
        instance = get_object_or_404(Producto, id=producto_id, cochera=cochera)

    if request.method == "POST":
        form = ProductoForm(request.POST, instance=instance)
        if form.is_valid():
            prod = form.save(commit=False)
            prod.cochera = cochera
            prod.save()
            messages.success(request, "Producto guardado.")
            return redirect("parking:inventario_list", cochera_id=cochera.id)
    else:
        form = ProductoForm(instance=instance)

    return render(request, "parking/producto_form.html", {
        "cochera": cochera, "form": form, "is_edit": instance is not None
    })


@login_required
@user_passes_test(can_operate)
def producto_movimiento(request, cochera_id: int, producto_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    producto = get_object_or_404(Producto, id=producto_id, cochera=cochera)

    if request.method == "POST":
        form = MovimientoInventarioForm(request.POST, producto=producto)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.producto = producto
            mov.operador = request.user
            mov.save()
            messages.success(request, f"Movimiento registrado. Stock: {producto.stock_actual} {producto.unidad}.")
            return redirect("parking:inventario_list", cochera_id=cochera.id)
    else:
        form = MovimientoInventarioForm(producto=producto)

    historial = producto.movimientos_inv.select_related("operador").all()[:20]
    return render(request, "parking/producto_movimiento.html", {
        "cochera": cochera, "producto": producto, "form": form, "historial": historial
    })


# ═══════════════════════════════════════════════════════════════════════════════
# CAR WASH — Membresías
# ═══════════════════════════════════════════════════════════════════════════════

@login_required
@user_passes_test(can_operate)
def planes_list(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
    planes = Plan.objects.filter(cochera=cochera).prefetch_related("servicios")
    membresias = Membresia.objects.filter(
        plan__cochera=cochera, estado=Membresia.ACTIVA
    ).select_related("cliente", "plan")
    return render(request, "parking/planes_list.html", {
        "cochera": cochera, "planes": planes, "membresias": membresias
    })


@login_required
@user_passes_test(is_admin_dueno)
def plan_form_view(request, cochera_id: int, plan_id: int = None):
    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)
    instance = None
    if plan_id:
        instance = get_object_or_404(Plan, id=plan_id, cochera=cochera)

    if request.method == "POST":
        form = PlanForm(request.POST, instance=instance, cochera=cochera)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.cochera = cochera
            plan.save()
            form.save_m2m()
            messages.success(request, "Plan guardado.")
            return redirect("parking:planes_list", cochera_id=cochera.id)
    else:
        form = PlanForm(instance=instance, cochera=cochera)

    return render(request, "parking/plan_form.html", {
        "cochera": cochera, "form": form, "is_edit": instance is not None
    })


@login_required
@user_passes_test(can_operate)
def membresia_new(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    if request.method == "POST":
        form = MembresiaForm(request.POST, cochera=cochera)
        if form.is_valid():
            form.save()
            messages.success(request, "Membresía creada.")
            return redirect("parking:planes_list", cochera_id=cochera.id)
    else:
        form = MembresiaForm(cochera=cochera)

    return render(request, "parking/membresia_form.html", {
        "cochera": cochera, "form": form
    })
