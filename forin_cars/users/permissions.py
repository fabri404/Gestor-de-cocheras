
def is_dueno(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="ADMIN_DUENO").exists())

def is_empleado(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="ADMIN_EMPLEADO").exists())

def can_operate_cochera(user, cochera):
    """
    Dueño: si es owner.
    Empleado: si está asignado (activo).
    Superuser: todo.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if cochera.owner_id == user.id:
        return True
    return cochera.empleados.filter(id=user.id, cocheraempleado__activo=True).exists()
