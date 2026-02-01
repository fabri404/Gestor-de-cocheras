def role_flags(request):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "is_superadmin": False,
            "show_admin_link": False,
            "can_manage_cochera": False,
            "can_operate": False,
        }

    group_names = set(user.groups.values_list("name", flat=True))

    is_superadmin = user.is_superuser
    show_admin_link = user.is_staff or is_superadmin

    # Dueño: puede crear/configurar cocheras
    can_manage_cochera = is_superadmin or ("ADMIN_DUENO" in group_names)

    # Operación: ingreso/egreso (dueño o empleado)
    can_operate = is_superadmin or ("ADMIN_DUENO" in group_names) or ("ADMIN_EMPLEADO" in group_names)

    return {
        "is_superadmin": is_superadmin,
        "show_admin_link": show_admin_link,
        "can_manage_cochera": can_manage_cochera,
        "can_operate": can_operate,
    }
