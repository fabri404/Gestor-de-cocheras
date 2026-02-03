from django.contrib import admin
from .models import (
    TipoEspacio, Cochera, CocheraEmpleado, InvitacionEmpleado,
    ConfigCapacidad, TarifaHora, Espacio, Cliente, Vehiculo, Movimiento
)

admin.site.register(TipoEspacio)
admin.site.register(Cochera)
admin.site.register(CocheraEmpleado)
admin.site.register(InvitacionEmpleado)
admin.site.register(ConfigCapacidad)
admin.site.register(TarifaHora)
admin.site.register(Espacio)
admin.site.register(Cliente)
admin.site.register(Vehiculo)
admin.site.register(Movimiento)
