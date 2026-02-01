from django.urls import path
from . import views

urlpatterns = [
    # ----------------------------
    # Cocheras
    # ----------------------------
    path("cocheras/nueva/", views.cochera_new, name="cochera_new"),
    path("cocheras/<int:cochera_id>/editar/", views.cochera_edit, name="cochera_edit"),
    path("cocheras/<int:cochera_id>/", views.cochera_detail, name="cochera_detail"),

    # Alias de conveniencia (navbar / botones)
    path("setup/", views.cochera_new, name="cochera_setup"),

    # ----------------------------
    # Movimientos (selector sin cochera_id)
    # ----------------------------
    path("ingreso/", views.ingreso_select_cochera_view, name="ingreso"),
    path("egreso/", views.egreso_select_cochera_view, name="egreso"),

    # ----------------------------
    # Movimientos (operación con cochera_id)
    # ----------------------------
    path("<int:cochera_id>/ingreso/", views.ingreso_view, name="ingreso_cochera"),
    path("<int:cochera_id>/egreso/", views.egreso_view, name="egreso_cochera"),
]
