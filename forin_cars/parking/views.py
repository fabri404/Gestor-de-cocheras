from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse

from .models import Cochera, TipoEspacio, TarifaHora
from .forms import CocheraForm, CapacidadForm, TarifaForm, EmpleadosForm
from .services import regenerar_espacios, ensure_default_tipos, upsert_capacidades, upsert_tarifas, invitar_empleados
from .services_movimientos import ingresar_vehiculo, egresar_vehiculo


def is_admin_dueno(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="ADMIN_DUENO").exists())


def can_operate(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.groups.filter(name="ADMIN_DUENO").exists()
        or user.groups.filter(name="ADMIN_EMPLEADO").exists()
    )


def cochera_queryset_for(user):
    if user.is_superuser:
        return Cochera.objects.all()
    return Cochera.objects.filter(Q(owner=user) | Q(empleados=user)).distinct()


@login_required
@user_passes_test(is_admin_dueno)
def cochera_new(request):
    ensure_default_tipos()
    tipos = TipoEspacio.objects.all().order_by("nombre")

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST)
        cap_form = CapacidadForm(request.POST, tipos=tipos)
        tarifa_form = TarifaForm(request.POST, tipos=tipos)
        empleados_form = EmpleadosForm(request.POST)

        if cochera_form.is_valid() and cap_form.is_valid() and tarifa_form.is_valid() and empleados_form.is_valid():
            cochera = cochera_form.save(commit=False)
            cochera.owner = request.user
            cochera.save()

            upsert_capacidades(cochera, tipos, cap_form.cleaned_data)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_new")

            upsert_tarifas(cochera, tipos, tarifa_form.cleaned_data)

            emails_list = empleados_form.cleaned_data.get("emails_list", [])
            if emails_list:
                invitar_empleados(cochera, emails_list)

            messages.success(request, "Cochera creada y configurada correctamente.")
            return redirect("dashboard")

    else:
        cochera_form = CocheraForm()
        cap_form = CapacidadForm(tipos=tipos)
        tarifa_form = TarifaForm(tipos=tipos)
        empleados_form = EmpleadosForm()

    return render(
        request,
        "parking/cochera_form.html",
        {
            "title": "Crear cochera",
            "cochera_form": cochera_form,
            "cap_form": cap_form,
            "tarifa_form": tarifa_form,
            "empleados_form": empleados_form,
        },
    )


@login_required
@user_passes_test(is_admin_dueno)
def cochera_edit(request, cochera_id):
    ensure_default_tipos()
    tipos = TipoEspacio.objects.all().order_by("nombre")

    cochera = get_object_or_404(Cochera, id=cochera_id, owner=request.user)

    # precargar capacidades y tarifas
    cap_map = {c.tipo_id: c.cantidad for c in cochera.capacidades.all()}
    tarifa_map = {t.tipo_id: t.precio_hora for t in cochera.tarifas.all()}

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST, instance=cochera)
        cap_form = CapacidadForm(request.POST, tipos=tipos)
        tarifa_form = TarifaForm(request.POST, tipos=tipos)
        empleados_form = EmpleadosForm(request.POST)

        if cochera_form.is_valid() and cap_form.is_valid() and tarifa_form.is_valid() and empleados_form.is_valid():
            cochera_form.save()

            upsert_capacidades(cochera, tipos, cap_form.cleaned_data)
            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_edit", cochera_id=cochera.id)

            upsert_tarifas(cochera, tipos, tarifa_form.cleaned_data)

            emails_list = empleados_form.cleaned_data.get("emails_list", [])
            if emails_list:
                invitar_empleados(cochera, emails_list)

            messages.success(request, "Cochera actualizada correctamente.")
            return redirect("dashboard")

    else:
        cochera_form = CocheraForm(instance=cochera)

        cap_initial = {}
        for tipo in tipos:
            cap_initial[f"tipo_{tipo.id}"] = cap_map.get(tipo.id, 0)

        tarifa_initial = {}
        for tipo in tipos:
            tarifa_initial[f"precio_{tipo.id}"] = tarifa_map.get(tipo.id, 0)

        cap_form = CapacidadForm(tipos=tipos, initial=cap_initial)
        tarifa_form = TarifaForm(tipos=tipos, initial=tarifa_initial)
        empleados_form = EmpleadosForm()

    return render(
        request,
        "parking/cochera_form.html",
        {
            "title": "Editar cochera",
            "cochera": cochera,
            "cochera_form": cochera_form,
            "cap_form": cap_form,
            "tarifa_form": tarifa_form,
            "empleados_form": empleados_form,
        },
    )


@login_required
def cochera_detail(request, cochera_id):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    tarifas = TarifaHora.objects.filter(cochera=cochera).select_related("tipo").order_by("tipo__nombre")
    capacidades = cochera.capacidades.select_related("tipo").order_by("tipo__nombre")
    empleados = cochera.empleados.all().order_by("username")

    return render(
        request,
        "parking/cochera_detail.html",
        {"cochera": cochera, "tarifas": tarifas, "capacidades": capacidades, "empleados": empleados},
    )


@login_required
@user_passes_test(can_operate)
def ingreso_select_cochera_view(request):
    qs = cochera_queryset_for(request.user).filter(activa=True).order_by("-created_at")
    if not qs.exists():
        messages.info(request, "No tenés cocheras asignadas para operar.")
        return redirect("dashboard")
    if qs.count() == 1:
        return redirect("ingreso_cochera", cochera_id=qs.first().id)
    return render(request, "parking/select_cochera.html", {"title": "Elegí cochera para INGRESO", "cocheras": qs, "target": "ingreso_cochera"})


@login_required
@user_passes_test(can_operate)
def egreso_select_cochera_view(request):
    qs = cochera_queryset_for(request.user).filter(activa=True).order_by("-created_at")
    if not qs.exists():
        messages.info(request, "No tenés cocheras asignadas para operar.")
        return redirect("dashboard")
    if qs.count() == 1:
        return redirect("egreso_cochera", cochera_id=qs.first().id)
    return render(request, "parking/select_cochera.html", {"title": "Elegí cochera para EGRESO", "cocheras": qs, "target": "egreso_cochera"})


@login_required
@user_passes_test(can_operate)
def ingreso_view(request, cochera_id):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)
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
            return redirect(f"{reverse('dashboard')}?cochera={cochera.id}")

        except ValueError as e:
            messages.error(request, str(e))
        except TipoEspacio.DoesNotExist:
            messages.error(request, "Tipo de vehículo inválido.")

    return render(request, "parking/ingreso.html", {"cochera": cochera, "tipos": tipos})


@login_required
@user_passes_test(can_operate)
def egreso_view(request, cochera_id):
    cochera = get_object_or_404(cochera_queryset_for(request.user), id=cochera_id)

    if request.method == "POST":
        ticket = request.POST.get("ticket", "")
        try:
            egresar_vehiculo(cochera=cochera, operador=request.user, ticket=ticket)
            messages.success(request, "Egreso OK.")
            return redirect(f"{reverse('dashboard')}?cochera={cochera.id}")
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "parking/egreso.html", {"cochera": cochera})
