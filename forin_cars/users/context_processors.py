def role_flags(request):
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return {"can_manage_cochera": False, "can_operate": False, "is_superadmin": False}

    is_superadmin = u.is_superuser
    can_manage_cochera = is_superadmin or u.groups.filter(name="ADMIN_DUENO").exists()
    can_operate = can_manage_cochera or u.groups.filter(name="ADMIN_EMPLEADO").exists()

    return {
        "is_superadmin": is_superadmin,
        "can_manage_cochera": can_manage_cochera,
        "can_operate": can_operate,
    }
