from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.http import JsonResponse


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


def health(request):
    """Liveness probe — Docker healthcheck y Makefile setup lo usan."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("", home),
    path("", include("users.urls")),
    # qrform app desconectada: sus templates no existen; el QR de parking ya
    # cubre el flujo de ingreso público (parking:cochera_qr / parking:ingreso_public).
    # path("", include("qrform.urls")),
    path("parking/", include(("parking.urls", "parking"), namespace="parking")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
