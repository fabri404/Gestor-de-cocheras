from django.conf import settings


def business_settings(request):
    """Expone configuraciones de negocio a todos los templates."""
    return {
        "BUSINESS_NAME": getattr(settings, "BUSINESS_NAME", "Forin Cars"),
    }
