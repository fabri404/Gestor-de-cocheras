from io import BytesIO
import secrets
from urllib.parse import urlencode
import base64
import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import FieldError
from django.core.signing import BadSignature, Signer
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from .forms import CapacidadForm, CocheraForm, EmpleadosForm, PublicIngresoForm, TarifaForm
from .models import Cochera, TipoEspacio, TarifaHora
from .services import (
    ensure_default_tipos,
    invitar_empleados,
    regenerar_espacios,
    upsert_capacidades,
    upsert_tarifas,
)
from .services_movimientos import egresar_vehiculo, ingresar_vehiculo
import json


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


def _public_ingreso_url(request, cochera_id: int, token: str) -> str:
    return request.build_absolute_uri(
        reverse(URL_INGRESO_PUBLIC, kwargs={"cochera_id": cochera_id})
        + "?"
        + urlencode({"t": token})
    )


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

    horas = int(request.POST.get("horas") or 1)
    if horas <= 0:
        raise ValueError("Horas inválidas.")

    if request.method == "POST":
        tipo_id = request.POST.get("tipo_id")
        ticket = request.POST.get("ticket", "")
        patente_ult3 = request.POST.get("patente_ult3", "")

        if not tipo_id:
            messages.error(request, "Tipo de vehículo requerido.")
        else:
            try:
                tipo = TipoEspacio.objects.get(id=tipo_id)
                ingresar_vehiculo(
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
                messages.success(request, "Ingreso realizado correctamente.")
                return redirect(f"{reverse(URL_DASHBOARD)}?cochera={cochera.id}")

            except TipoEspacio.DoesNotExist:
                messages.error(request, "Tipo de vehículo inválido.")
            except ValueError as e:
                messages.error(request, str(e))
    tarifas_json = _tarifas_json_for_cochera(cochera)

    return render(request,
        "parking/ingreso.html",
        {"cochera": cochera, "tipos": tipos, "tarifas_json": tarifas_json})


@login_required
@user_passes_test(can_operate)
def egreso_view(request, cochera_id: int):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    if request.method == "POST":
        ticket = request.POST.get("ticket", "")
        try:
            egresar_vehiculo(cochera=cochera, operador=request.user, ticket=ticket)
            messages.success(request, "Egreso OK.")
            return redirect(f"{reverse(URL_DASHBOARD)}?cochera={cochera.id}")
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "parking/egreso.html", {"cochera": cochera})
