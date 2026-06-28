from django.urls import path
from . import views

app_name = "parking"

urlpatterns = [
    # ── Cocheras ──────────────────────────────────────────────────────────────
    path("cocheras/nueva/", views.cochera_new, name="cochera_new"),
    path("cocheras/<int:cochera_id>/editar/", views.cochera_edit, name="cochera_edit"),
    path("cocheras/<int:cochera_id>/", views.cochera_detail, name="cochera_detail"),
    path("cocheras/<int:cochera_id>/live/", views.cochera_live, name="cochera_live"),
    path("setup/", views.cochera_new, name="cochera_setup"),

    # ── Movimientos de cochera (parking) ──────────────────────────────────────
    path("ingreso/", views.ingreso_select_cochera_view, name="ingreso"),
    path("egreso/", views.egreso_select_cochera_view, name="egreso"),
    path("<int:cochera_id>/ingreso/", views.ingreso_view, name="ingreso_cochera"),
    path("<int:cochera_id>/egreso/", views.egreso_view, name="egreso_cochera"),

    # ── QR + ingreso público ──────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/qr/", views.cochera_qr_view, name="cochera_qr"),
    path("cocheras/<int:cochera_id>/qr.png", views.cochera_qr_png_view, name="cochera_qr_png"),
    path("cocheras/<int:cochera_id>/ingreso/public/", views.ingreso_public_view, name="ingreso_public"),

    # ── Servicios (catálogo lavadero) ─────────────────────────────────────────
    path("cocheras/<int:cochera_id>/servicios/", views.servicios_list, name="servicios_list"),
    path("cocheras/<int:cochera_id>/servicios/nuevo/", views.servicio_form_view, name="servicio_new"),
    path("cocheras/<int:cochera_id>/servicios/<int:servicio_id>/editar/", views.servicio_form_view, name="servicio_edit"),
    path("cocheras/<int:cochera_id>/servicios/<int:servicio_id>/toggle/", views.servicio_toggle, name="servicio_toggle"),

    # ── Clientes ──────────────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/clientes/", views.clientes_list, name="clientes_list"),
    path("cocheras/<int:cochera_id>/clientes/<int:cliente_id>/", views.cliente_detail, name="cliente_detail"),

    # ── Órdenes de trabajo ────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/ordenes/", views.ordenes_list, name="ordenes_list"),
    path("cocheras/<int:cochera_id>/ordenes/nueva/", views.orden_new, name="orden_new"),
    path("cocheras/<int:cochera_id>/ordenes/<int:orden_id>/", views.orden_detail, name="orden_detail"),
    path("cocheras/<int:cochera_id>/ordenes/<int:orden_id>/estado/", views.orden_cambiar_estado, name="orden_estado"),

    # ── Turnos ────────────────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/turnos/", views.turnos_list, name="turnos_list"),
    path("cocheras/<int:cochera_id>/turnos/nuevo/", views.turno_new, name="turno_new"),

    # ── Checklist de calidad ──────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/checklist/", views.checklist_config, name="checklist_config"),
    path("cocheras/<int:cochera_id>/ordenes/<int:orden_id>/checklist/", views.orden_checklist, name="orden_checklist"),

    # ── Fotos de OT ───────────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/ordenes/<int:orden_id>/fotos/", views.orden_foto_upload, name="orden_foto_upload"),
    path("cocheras/<int:cochera_id>/ordenes/<int:orden_id>/fotos/<int:foto_id>/delete/", views.orden_foto_delete, name="orden_foto_delete"),

    # ── Inventario ────────────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/inventario/", views.inventario_list, name="inventario_list"),
    path("cocheras/<int:cochera_id>/inventario/nuevo/", views.producto_form_view, name="producto_new"),
    path("cocheras/<int:cochera_id>/inventario/<int:producto_id>/editar/", views.producto_form_view, name="producto_edit"),
    path("cocheras/<int:cochera_id>/inventario/<int:producto_id>/movimiento/", views.producto_movimiento, name="producto_movimiento"),

    # ── Membresías ────────────────────────────────────────────────────────────
    path("cocheras/<int:cochera_id>/planes/", views.planes_list, name="planes_list"),
    path("cocheras/<int:cochera_id>/planes/nuevo/", views.plan_form_view, name="plan_new"),
    path("cocheras/<int:cochera_id>/planes/<int:plan_id>/editar/", views.plan_form_view, name="plan_edit"),
    path("cocheras/<int:cochera_id>/membresias/nueva/", views.membresia_new, name="membresia_new"),
]
