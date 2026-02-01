# users/views.py
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import RegistroForm
from parking.models import Cochera, Movimiento

GRUPO_ADMIN_DUENO = "ADMIN_DUENO"
GRUPO_ADMIN_EMPLEADO = "ADMIN_EMPLEADO"


def _role_flags(user):
    """Flags de roles para usar en templates SIN lógica compleja."""
    if not user.is_authenticated:
        return {
            "is_superadmin": False,
            "is_admin_dueno": False,
            "is_admin_empleado": False,
            "can_manage_cochera": False,
            "can_operate": False,
            "show_admin_link": False,
        }

    is_superadmin = bool(user.is_superuser or user.is_staff)
    is_admin_dueno = user.groups.filter(name=GRUPO_ADMIN_DUENO).exists()
    is_admin_empleado = user.groups.filter(name=GRUPO_ADMIN_EMPLEADO).exists()

    # Permisos:
    # - superadmin: todo
    # - admin_dueño: gestiona cocheras (y suele poder operar también)
    # - admin_empleado: solo opera (ingreso/egreso)
    can_manage_cochera = is_superadmin or is_admin_dueno
    can_operate = is_superadmin or is_admin_dueno or is_admin_empleado

    return {
        "is_superadmin": is_superadmin,
        "is_admin_dueno": is_admin_dueno,
        "is_admin_empleado": is_admin_empleado,
        "can_manage_cochera": can_manage_cochera,
        "can_operate": can_operate,
        "show_admin_link": is_superadmin,  # solo el dueño creador ve Admin Django
    }


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Superadmin => directo al /admin/ sin relogueo
            if user.is_superuser or user.is_staff:
                return redirect(reverse("admin:index"))

            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(next_url or "dashboard")

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
    # Todas las cocheras activas del usuario (usuario puede tener varias)
    cocheras = Cochera.objects.filter(owner=request.user, activa=True).order_by("-id")

    # Cochera seleccionada por querystring (?cochera=ID) o la primera
    cochera_id = request.GET.get("cochera")
    cochera = cocheras.filter(id=cochera_id).first() if cochera_id else cocheras.first()

    # Métricas (se mantienen)
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
        "cocheras": cocheras,
        "cochera": cochera,
        "total_espacios": total,
        "ocupados": ocupados,
        "libres": libres,
        "mov_abiertos": mov_abiertos,
        "ocupacion_pct": ocupacion_pct,
        "ultimos": ultimos,
    }
    ctx.update(_role_flags(request.user))

    return render(request, "users/dashboard.html", ctx)


def logout_view(request):
    logout(request)
    return redirect("login")
