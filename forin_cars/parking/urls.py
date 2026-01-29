# parking/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Cocheras
    path("cocheras/nueva/", views.cochera_new, name="cochera_new"),
    path("cocheras/<int:cochera_id>/editar/", views.cochera_edit, name="cochera_edit"),
    path("cocheras/<int:cochera_id>/", views.cochera_detail, name="cochera_detail"),

    # Compat: si algún template todavía usa cochera_setup, lo dejamos vivo
    path("setup/", views.cochera_new, name="cochera_setup"),

    # Movimientos por cochera
    path("<int:cochera_id>/ingreso/", views.ingreso_view, name="ingreso"),
    path("<int:cochera_id>/egreso/", views.egreso_view, name="egreso"),
]
