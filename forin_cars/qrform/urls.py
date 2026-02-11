from django.urls import path
from . import views

app_name = "qrforms"

urlpatterns = [
    path("qr/new/", views.qr_new, name="qr_new"),
    path("qr/<uuid:token>/", views.qr_detail, name="qr_detail"),
    path("qr/<uuid:token>/image.png", views.qr_image, name="qr_image"),

    # URL para escaneo
    path("q/<uuid:token>/", views.qr_form, name="qr_form"),
    path("q/<uuid:token>/ok/", views.qr_success, name="qr_success"),
]
