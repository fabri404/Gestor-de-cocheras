# parking/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden

from .models import Cochera, TipoEspacio, ConfigCapacidad
try:
    # si ya lo tenés (modelo con empleados)
    from .models import CocheraEmpleado
except Exception:
    CocheraEmpleado = None

from .forms import CocheraForm, CapacidadForm
from .services import regenerar_espacios
from .services_movimientos import ingresar_vehiculo, egresar_vehiculo


GROUP_ADMIN_DUENO = "ADMIN_DUENO"
GROUP_ADMIN_EMPLEADO = "ADMIN_EMPLEADO"


def _is_superadmin(user) -> bool:
    return user.is_authenticated and user.is_superuser


def _is_admin_dueno(user) -> bool:
    if not user.is_authenticated:
        return False
    return _is_superadmin(user) or user.groups.filter(name=GROUP_ADMIN_DUENO).exists()


def _is_admin_empleado(user) -> bool:
    if not user.is_authenticated:
        return False
    return _is_superadmin(user) or user.groups.filter(name=GROUP_ADMIN_EMPLEADO).exists()


def _cocheras_visibles(user):
    """
    - Dueño: ve sus cocheras activas
    - Empleado: ve cocheras asignadas activas (si existe CocheraEmpleado)
    - Superadmin: ve todas
    """
    if _is_superadmin(user):
        return Cochera.objects.filter(activa=True).order_by("-created_at")

    qs = Cochera.objects.filter(owner=user, activa=True)

    if CocheraEmpleado is not None:
        ids = CocheraEmpleado.objects.filter(empleado=user, activo=True).values_list("cochera_id", flat=True)
        qs = (qs | Cochera.objects.filter(id__in=ids, activa=True))

    return qs.distinct().order_by("-created_at")


def _can_manage_cochera(user, cochera: Cochera) -> bool:
    return _is_superadmin(user) or cochera.owner_id == user.id


def _can_operate_cochera(user, cochera: Cochera) -> bool:
    if _can_manage_cochera(user, cochera):
        return True
    if CocheraEmpleado is None:
        return False
    return CocheraEmpleado.objects.filter(cochera=cochera, empleado=user, activo=True).exists()


# ===========================
# COCHERAS
# ===========================

@login_required
def cochera_new(request):
    # Solo dueño o superadmin crea cocheras
    if not (_is_admin_dueno(request.user) or _is_superadmin(request.user)):
        return HttpResponseForbidden("No tenés permiso para crear cocheras.")

    tipos = TipoEspacio.objects.all().order_by("nombre")

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST)
        cap_form = CapacidadForm(request.POST, tipos=tipos)

        if cochera_form.is_valid() and cap_form.is_valid():
            cochera = cochera_form.save(commit=False)
            cochera.owner = request.user
            cochera.save()

            ConfigCapacidad.objects.filter(cochera=cochera).delete()
            for tipo in tipos:
                cantidad = cap_form.cleaned_data.get(f"tipo_{tipo.id}", 0)
                ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=cantidad)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_edit", cochera_id=cochera.id)

            messages.success(request, "Cochera creada y configurada correctamente.")
            return redirect("dashboard")

    else:
        cochera_form = CocheraForm()
        cap_form = CapacidadForm(tipos=tipos)

    return render(
        request,
        "parking/setup.html",
        {"cochera_form": cochera_form, "cap_form": cap_form, "modo": "new"},
    )


@login_required
def cochera_edit(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, activa=True)

    if not _can_manage_cochera(request.user, cochera):
        return HttpResponseForbidden("No tenés permiso para editar esta cochera.")

    tipos = TipoEspacio.objects.all().order_by("nombre")
    existentes = {c.tipo_id: c.cantidad for c in ConfigCapacidad.objects.filter(cochera=cochera)}
    initial = {f"tipo_{t.id}": existentes.get(t.id, 0) for t in tipos}

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST, instance=cochera)
        cap_form = CapacidadForm(request.POST, tipos=tipos)

        if cochera_form.is_valid() and cap_form.is_valid():
            cochera_form.save()

            ConfigCapacidad.objects.filter(cochera=cochera).delete()
            for tipo in tipos:
                cantidad = cap_form.cleaned_data.get(f"tipo_{tipo.id}", 0)
                ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=cantidad)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_edit", cochera_id=cochera.id)

            messages.success(request, "Cochera actualizada correctamente.")
            return redirect("cochera_detail", cochera_id=cochera.id)

    else:
        cochera_form = CocheraForm(instance=cochera)
        cap_form = CapacidadForm(tipos=tipos, initial=initial)

    return render(
        request,
        "parking/setup.html",
        {"cochera_form": cochera_form, "cap_form": cap_form, "cochera": cochera, "modo": "edit"},
    )


@login_required
def cochera_detail(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, activa=True)

    if not _can_operate_cochera(request.user, cochera):
        return HttpResponseForbidden("No tenés acceso a esta cochera.")

    # métricas simples por cochera (NO borra nada)
    total_espacios = cochera.espacios.count()
    ocupados = cochera.espacios.filter(ocupado=True).count()
    libres = total_espacios - ocupados
    mov_abiertos = cochera.movimientos.filter(estado="ABIERTO").count()

    return render(
        request,
        "parking/cochera_detail.html",
        {
            "cochera": cochera,
            "total_espacios": total_espacios,
            "ocupados": ocupados,
            "libres": libres,
            "mov_abiertos": mov_abiertos,
        },
    )


# ===========================
# SELECTOR DE COCHERA (multi)
# ===========================

@login_required
def ingreso_select_cochera_view(request):
    cocheras = _cocheras_visibles(request.user)

    if not cocheras.exists():
        if _is_admin_dueno(request.user) or _is_superadmin(request.user):
            messages.info(request, "Primero creá/configurá una cochera.")
            return redirect("cochera_new")
        messages.error(request, "No tenés cocheras asignadas. Pedile al dueño que te asigne una.")
        return redirect("dashboard")

    if cocheras.count() == 1:
        return redirect("ingreso_cochera", cochera_id=cocheras.first().id)

    return render(request, "parking/select_cochera.html", {"cocheras": cocheras, "accion": "ingreso"})


@login_required
def egreso_select_cochera_view(request):
    cocheras = _cocheras_visibles(request.user)

    if not cocheras.exists():
        if _is_admin_dueno(request.user) or _is_superadmin(request.user):
            messages.info(request, "Primero creá/configurá una cochera.")
            return redirect("cochera_new")
        messages.error(request, "No tenés cocheras asignadas. Pedile al dueño que te asigne una.")
        return redirect("dashboard")

    if cocheras.count() == 1:
        return redirect("egreso_cochera", cochera_id=cocheras.first().id)

    return render(request, "parking/select_cochera.html", {"cocheras": cocheras, "accion": "egreso"})


# ===========================
# MOVIMIENTOS
# ===========================

@login_required
def ingreso_view(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, activa=True)

    if not _can_operate_cochera(request.user, cochera):
        return HttpResponseForbidden("No tenés permiso para operar esta cochera.")

    tipos = TipoEspacio.objects.all().order_by("nombre")

    if request.method == "POST":
        tipo_id = request.POST.get("tipo_id")
        ticket = request.POST.get("ticket", "")
        patente_ult3 = request.POST.get("patente_ult3", "")

        try:
            tipo = TipoEspacio.objects.get(id=tipo_id)

            ingresar_vehiculo(
                cochera=cochera,
                operador=request.user,
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

            messages.success(request, "Ingreso realizado correctamente.")
            return redirect("cochera_detail", cochera_id=cochera.id)

        except TipoEspacio.DoesNotExist:
            messages.error(request, "Tipo de vehículo inválido.")
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "parking/ingreso.html", {"cochera": cochera, "tipos": tipos})


@login_required
def egreso_view(request, cochera_id: int):
    cochera = get_object_or_404(Cochera, id=cochera_id, activa=True)

    if not _can_operate_cochera(request.user, cochera):
        return HttpResponseForbidden("No tenés permiso para operar esta cochera.")

    if request.method == "POST":
        ticket = request.POST.get("ticket", "")
        try:
            egresar_vehiculo(cochera=cochera, operador=request.user, ticket=ticket)
            messages.success(request, "Egreso realizado correctamente.")
            return redirect("cochera_detail", cochera_id=cochera.id)
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "parking/egreso.html", {"cochera": cochera})
