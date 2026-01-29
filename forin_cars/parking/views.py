# parking/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import Cochera, TipoEspacio, ConfigCapacidad
from .forms import CocheraForm, CapacidadForm
from .services import regenerar_espacios
from .services_movimientos import ingresar_vehiculo, egresar_vehiculo

def _cochera_user_or_404(user, cochera_id: int) -> Cochera:
    return get_object_or_404(Cochera, id=cochera_id, owner=user, activa=True)

@login_required
def cochera_new(request):
    tipos = TipoEspacio.objects.all()

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST)
        cap_form = CapacidadForm(request.POST, tipos=tipos)

        if cochera_form.is_valid() and cap_form.is_valid():
            cochera = cochera_form.save(commit=False)
            cochera.owner = request.user
            cochera.save()

            # capacidades por tipo
            for tipo in tipos:
                cantidad = cap_form.cleaned_data[f"tipo_{tipo.id}"]
                ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=cantidad)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_new")

            messages.success(request, "Cochera creada y mapeada correctamente.")
            return redirect("dashboard")

    else:
        cochera_form = CocheraForm()
        cap_form = CapacidadForm(tipos=tipos)

    return render(request, "parking/setup.html", {"cochera_form": cochera_form, "cap_form": cap_form})


@login_required
def cochera_edit(request, cochera_id):
    cochera = _cochera_user_or_404(request.user, cochera_id)
    tipos = TipoEspacio.objects.all()

    if request.method == "POST":
        cochera_form = CocheraForm(request.POST, instance=cochera)
        cap_form = CapacidadForm(request.POST, tipos=tipos)

        if cochera_form.is_valid() and cap_form.is_valid():
            cochera_form.save()

            ConfigCapacidad.objects.filter(cochera=cochera).delete()
            for tipo in tipos:
                cantidad = cap_form.cleaned_data[f"tipo_{tipo.id}"]
                ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=cantidad)

            try:
                regenerar_espacios(cochera)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("cochera_edit", cochera_id=cochera.id)

            messages.success(request, "Cochera actualizada.")
            return redirect("dashboard")

    else:
        cochera_form = CocheraForm(instance=cochera)
        cap_form = CapacidadForm(tipos=tipos)

    return render(request, "parking/setup.html", {"cochera_form": cochera_form, "cap_form": cap_form, "cochera": cochera})


@login_required
def cochera_detail(request, cochera_id):
    cochera = _cochera_user_or_404(request.user, cochera_id)
    caps = cochera.capacidades.select_related("tipo").all()
    return render(request, "parking/cochera_detail.html", {"cochera": cochera, "caps": caps})


@login_required
def ingreso_view(request, cochera_id):
    cochera = _cochera_user_or_404(request.user, cochera_id)

    # TIPOS habilitados para ESA cochera (solo los que tienen capacidad > 0)
    tipos = TipoEspacio.objects.filter(
        configcapacidad__cochera=cochera,
        configcapacidad__cantidad__gt=0
    ).distinct()

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
            return redirect("dashboard")

        except ValueError as e:
            messages.error(request, str(e))
        except TipoEspacio.DoesNotExist:
            messages.error(request, "Tipo de vehículo inválido.")

    return render(request, "parking/ingreso.html", {"tipos": tipos, "cochera": cochera})


@login_required
def egreso_view(request, cochera_id):
    cochera = _cochera_user_or_404(request.user, cochera_id)

    if request.method == "POST":
        ticket = request.POST.get("ticket", "")  # OJO: tu service egresa por ticket :contentReference[oaicite:10]{index=10}
        try:
            egresar_vehiculo(cochera=cochera, operador=request.user, ticket=ticket)
            messages.success(request, "Egreso OK.")
            return redirect("dashboard")
        except ValueError as e:
            messages.error(request, str(e))

    return render(request, "parking/egreso.html", {"cochera": cochera})
