from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect

from .forms import RegistroForm
from parking.models import Cochera, Movimiento


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            return redirect("dashboard")
        messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, "users/login.html", {"form": form})


def registro_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuario creado correctamente. Ahora iniciá sesión.")
            return redirect("login")
    else:
        form = RegistroForm()

    return render(request, "users/registro.html", {"form": form})


@login_required
def dashboard_view(request):
    # Todas las cocheras activas del usuario
    cocheras = Cochera.objects.filter(owner=request.user, activa=True).order_by("-id")

    # Cochera "seleccionada" (por querystring ?cochera=ID) o la última creada
    cochera_id = request.GET.get("cochera")
    cochera = cocheras.filter(id=cochera_id).first() if cochera_id else cocheras.first()

    # Métricas para la cochera seleccionada (NO se borran, se mantienen)
    total = ocupados = libres = mov_abiertos = 0
    ocupacion_pct = 0
    ultimos = []

    if cochera:
        total = cochera.espacios.count()
        ocupados = cochera.espacios.filter(ocupado=True).count()
        libres = total - ocupados
        mov_abiertos = cochera.movimientos.filter(estado="ABIERTO").count()
        ocupacion_pct = round((ocupados / total * 100) if total else 0, 1)

        ultimos = (
            Movimiento.objects.filter(cochera=cochera)
            .select_related("vehiculo", "vehiculo__tipo", "espacio")
            .order_by("-ingreso_at")[:10]
        )

    ctx = {
        "cocheras": cocheras,   # lista completa
        "cochera": cochera,     # cochera seleccionada
        "total_espacios": total,
        "ocupados": ocupados,
        "libres": libres,
        "mov_abiertos": mov_abiertos,     # mantenemos nombre usado por tu template :contentReference[oaicite:6]{index=6}
        "ocupacion_pct": ocupacion_pct,
        "ultimos": ultimos,
    }
    return render(request, "users/dashboard.html", ctx)


def logout_view(request):
    logout(request)
    return redirect("login")
