# users/views.py
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import RegistroForm
from parking.models import Cochera, Movimiento


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)

        # Solo superuser ve /admin
        if user.is_superuser:
            return redirect(reverse("admin:index"))

        next_url = request.POST.get("next") or request.GET.get("next")
        return redirect(next_url or "dashboard")

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
    user = request.user

    # Roles por grupos (evita hacer .exists() en template)
    is_superadmin = user.is_superuser
    is_admin_dueno = is_superadmin or user.groups.filter(name="ADMIN_DUENO").exists()
    is_admin_empleado = is_superadmin or user.groups.filter(name="ADMIN_EMPLEADO").exists()

    can_manage_cochera = is_admin_dueno
    can_operate = is_admin_dueno or is_admin_empleado

    # ✅ Cocheras visibles: dueño o empleado asignado (y cochera activa)
    # OJO: el campo es "activa", NO "activo". :contentReference[oaicite:2]{index=2}
    cocheras = (
        Cochera.objects.filter(
            Q(owner=user) |
            Q(cocheraempleado__empleado=user, cocheraempleado__activo=True)
        )
        .filter(activa=True)
        .distinct()
        .order_by("-created_at", "-id")
        .prefetch_related("capacidades__tipo", "espacios__tipo")
    )

    # --- Métricas globales ---
    total_espacios = 0
    ocupados = 0
    libres = 0
    mov_abiertos = 0

    # Totales globales por tipo
    totales_por_tipo = {}  # tipo_id -> dict(tipo,total,ocupados,libres)

    # Detalle por cochera (para pintar tarjetas)
    cocheras_data = []

    for c in cocheras:
        # Totales por tipo según ConfigCapacidad (lo que “debería haber”)
        caps = list(c.capacidades.all())

        total_por_tipo = {cap.tipo_id: cap.cantidad for cap in caps}
        tipo_obj = {cap.tipo_id: cap.tipo for cap in caps}

        # Ocupados reales según Espacios (lo que “hay ocupado”)
        espacios = list(c.espacios.all())
        ocupados_por_tipo = defaultdict(int)
        for e in espacios:
            if e.ocupado:
                ocupados_por_tipo[e.tipo_id] += 1
            # si aparece un tipo en espacios que no esté en capacidades, lo incluimos igual
            if e.tipo_id not in tipo_obj:
                tipo_obj[e.tipo_id] = e.tipo
                total_por_tipo.setdefault(e.tipo_id, 0)

        por_tipo_list = []
        total_c = 0
        ocupados_c = 0

        for tipo_id, tipo in sorted(tipo_obj.items(), key=lambda kv: kv[1].nombre):
            t_total = int(total_por_tipo.get(tipo_id, 0))
            t_ocup = int(ocupados_por_tipo.get(tipo_id, 0))
            t_lib = max(t_total - t_ocup, 0)

            por_tipo_list.append({
                "tipo": tipo,
                "total": t_total,
                "ocupados": t_ocup,
                "libres": t_lib,
            })

            total_c += t_total
            ocupados_c += t_ocup

            # acumular globales por tipo
            if tipo_id not in totales_por_tipo:
                totales_por_tipo[tipo_id] = {"tipo": tipo, "total": 0, "ocupados": 0, "libres": 0}
            totales_por_tipo[tipo_id]["total"] += t_total
            totales_por_tipo[tipo_id]["ocupados"] += t_ocup

        libres_c = max(total_c - ocupados_c, 0)
        abiertos_c = c.movimientos.filter(estado="ABIERTO").count()

        # acumular globales
        total_espacios += total_c
        ocupados += ocupados_c
        libres += libres_c
        mov_abiertos += abiertos_c

        cocheras_data.append({
            "cochera": c,
            "is_owner": (c.owner_id == user.id),
            "total_espacios": total_c,
            "ocupados": ocupados_c,
            "libres": libres_c,
            "mov_abiertos": abiertos_c,
            "por_tipo": por_tipo_list,
        })

    # terminar globales por tipo
    totales_por_tipo_list = []
    for d in totales_por_tipo.values():
        d["libres"] = max(d["total"] - d["ocupados"], 0)
        totales_por_tipo_list.append(d)
    totales_por_tipo_list.sort(key=lambda x: x["tipo"].nombre)

    ocupacion_pct = round((ocupados / total_espacios * 100) if total_espacios else 0, 1)

    ultimos = (
        Movimiento.objects.filter(cochera__in=cocheras)
        .select_related("cochera", "vehiculo", "vehiculo__tipo", "espacio", "espacio__tipo")
        .order_by("-ingreso_at")[:10]
    )

    # ⚠️ “Monto total”: hoy no existe un campo monto/facturación en Movimiento ni en services,
    # así que te dejo placeholder hasta que metas Tarifa/Pago.
    total_facturado = None

    ctx = {
        "cocheras": cocheras,
        "cocheras_data": cocheras_data,

        # métricas (mantenidas)
        "total_espacios": total_espacios,
        "ocupados": ocupados,
        "libres": libres,
        "mov_abiertos": mov_abiertos,
        "ocupacion_pct": ocupacion_pct,
        "ultimos": ultimos,

        # detalle global por tipo
        "totales_por_tipo": totales_por_tipo_list,

        # roles
        "is_superadmin": is_superadmin,
        "can_manage_cochera": can_manage_cochera,
        "can_operate": can_operate,

        # placeholder monetario
        "total_facturado": total_facturado,
    }
    return render(request, "users/dashboard.html", ctx)


def logout_view(request):
    logout(request)
    return redirect("login")
