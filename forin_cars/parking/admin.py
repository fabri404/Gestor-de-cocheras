from django.contrib import admin
from .models import (
    TipoEspacio, Cochera, CocheraEmpleado, InvitacionEmpleado,
    ConfigCapacidad, TarifaHora, Espacio, Cliente, Vehiculo, Movimiento,
    Servicio, OrdenTrabajo, OrdenServicio, Turno,
    ChecklistItem, OrdenChecklist, FotoOrden,
    CategoriaProducto, Producto, MovimientoInventario,
    Plan, Membresia,
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


class OrdenServicioInline(admin.TabularInline):
    model = OrdenServicio
    extra = 0


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "cochera", "categoria", "precio", "duracion_minutos", "activo"]
    list_filter = ["cochera", "categoria", "activo"]
    search_fields = ["nombre"]


@admin.register(OrdenTrabajo)
class OrdenTrabajoAdmin(admin.ModelAdmin):
    list_display = ["numero", "cochera", "cliente", "vehiculo", "estado", "monto_total", "created_at"]
    list_filter = ["cochera", "estado", "created_at"]
    search_fields = ["numero", "cliente__nombre", "vehiculo__patente"]
    inlines = [OrdenServicioInline]


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ["cochera", "cliente", "vehiculo", "fecha", "hora", "estado", "operador"]
    list_filter = ["cochera", "estado", "fecha"]
    search_fields = ["cliente__nombre", "vehiculo__patente"]


admin.site.register(ChecklistItem)
admin.site.register(OrdenChecklist)
admin.site.register(FotoOrden)
admin.site.register(CategoriaProducto)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "cochera", "categoria", "stock_actual", "stock_minimo", "unidad", "activo"]
    list_filter = ["cochera", "categoria", "activo"]


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ["producto", "tipo", "cantidad", "operador", "created_at"]
    list_filter = ["tipo", "created_at"]


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["nombre", "cochera", "precio_mensual", "lavados_incluidos", "activo"]
    list_filter = ["cochera", "activo"]


@admin.register(Membresia)
class MembresiaAdmin(admin.ModelAdmin):
    list_display = ["cliente", "plan", "estado", "fecha_inicio", "fecha_vencimiento"]
    list_filter = ["estado", "plan__cochera"]
    search_fields = ["cliente__nombre", "cliente__apellido"]
