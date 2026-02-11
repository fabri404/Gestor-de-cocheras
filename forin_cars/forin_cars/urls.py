from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home),
    path("", include("users.urls")),
    path("", include("qrform.urls")),
    path("parking/", include(("parking.urls", "parking"), namespace="parking"))
]
