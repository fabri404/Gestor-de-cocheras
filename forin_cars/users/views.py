from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import RegistroForm
from parking.models import Cochera, Movimiento
from parking.services import apply_pending_invites


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect(reverse("admin:index"))
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            if user.is_superuser:
                return redirect(reverse("admin:index"))

            return redirect("dashboard")

        messages.error(request, "Usuario o contraseña incorrectos.")

    return render(request, "users/login.html", {"form": form})


def registro_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()

        # si estaba invitado a una cochera, queda como ADMIN_EMPLEADO automáticamente
        apply_pending_invites(user)

        login(request, user)
        return redirect("dashboard")

    return render(request, "users/registro.html", {"form": form})


@login_required
def dashboard_view(request):
    user = request.user

    cocheras = Cochera.objects.filter(
        Q(owner=user) | Q(empleados=user),
        activa=True
    ).distinct().order_by("-created_at")

    cochera_id = request.GET.get("cochera")
    cochera = cocheras.filter(id=cochera_id).first() if cochera_id else cocheras.first()

    total = ocupados = libres = mov_abiertos = 0
    ultimos = []

    if cochera:
        total = cochera.espacios.count()
        ocupados = cochera.espacios.filter(ocupado=True).count()
        libres = total - ocupados
        mov_abiertos = cochera.movimientos.filter(estado="ABIERTO").count()

        ultimos = (
            Movimiento.objects.filter(cochera=cochera)
            .select_related("vehiculo", "vehiculo__tipo", "espacio")
            .order_by("-ingreso_at")[:10]
        )

    ctx = {
        "cocheras": cocheras,
        "cochera": cochera,
        "total_espacios": total,
        "ocupados": ocupados,
        "libres": libres,
        "mov_abiertos": mov_abiertos,
        "ultimos": ultimos,
    }
    return render(request, "users/dashboard.html", ctx)


def logout_view(request):
    logout(request)
    return redirect("login")
