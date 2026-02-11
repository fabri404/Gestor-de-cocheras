from django.urls import path
from . import views

app_name = "parking"

urlpatterns = [
    # ----------------------------
    # Cocheras
    # ----------------------------
    path("cocheras/nueva/", views.cochera_new, name="cochera_new"),
    path("cocheras/<int:cochera_id>/editar/", views.cochera_edit, name="cochera_edit"),
    path("cocheras/<int:cochera_id>/", views.cochera_detail, name="cochera_detail"),

    # Alias de conveniencia
    path("setup/", views.cochera_new, name="cochera_setup"),

    # ----------------------------
    # Movimientos (selector)
    # ----------------------------
    path("ingreso/", views.ingreso_select_cochera_view, name="ingreso"),
    path("egreso/", views.egreso_select_cochera_view, name="egreso"),

    # ----------------------------
    # Movimientos (por cochera)
    # ----------------------------
    path("<int:cochera_id>/ingreso/", views.ingreso_view, name="ingreso_cochera"),
    path("<int:cochera_id>/egreso/", views.egreso_view, name="egreso_cochera"),

    # ----------------------------
    # QR + ingreso público
    # ----------------------------
    path("cocheras/<int:cochera_id>/qr/", views.cochera_qr_view, name="cochera_qr"),
    path("cocheras/<int:cochera_id>/qr.png", views.cochera_qr_png_view, name="cochera_qr_png"),
    path("cocheras/<int:cochera_id>/ingreso-publico/", views.ingreso_public_view, name="ingreso_public"),
        # Form público (escaneado por QR)
    path("cocheras/<int:cochera_id>/ingreso/public/", views.ingreso_public_view, name="ingreso_public"),
]
