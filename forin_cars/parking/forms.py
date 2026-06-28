from django import forms
from django.core.validators import validate_email
from .services_movimientos import ingresar_vehiculo
from .models import (
    Cochera,
    Cliente,
    Vehiculo,
    TipoEspacio,
    Servicio,
    OrdenTrabajo,
    OrdenServicio,
    Turno,
    ChecklistItem,
    FotoOrden,
    CategoriaProducto,
    Producto,
    MovimientoInventario,
    Plan,
    Membresia,
)
        

class PublicIngresoForm(forms.Form):
    tipo = forms.ModelChoiceField(
        queryset=TipoEspacio.objects.none(),
        empty_label="Seleccioná el tipo de vehículo",
        required=True,
    )

    horas = forms.IntegerField(
        min_value=1,
        required=True,
        initial=1,
        label="Horas a permanecer",
        help_text="Se usa para calcular total estimado.",
    )

    patente_ult3 = forms.CharField(
        max_length=3,
        required=False,
        help_text="Opcional. Últimos 3 caracteres.",
        widget=forms.TextInput(attrs={"placeholder": "ABC", "maxlength": "3"}),
    )

    # Datos del cliente (opcionales)
    nombre = forms.CharField(max_length=80, required=False)
    apellido = forms.CharField(max_length=80, required=False)
    telefono = forms.CharField(max_length=30, required=False)
    email = forms.EmailField(required=False)

    def __init__(self, *args, cochera=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cochera = cochera

        # Tipos habilitados = tipos que existan en ConfigCapacidad de esa cochera
        if cochera is not None:
            qs = (
                TipoEspacio.objects.filter(configcapacidad__cochera=cochera)
                .distinct()
                .order_by("nombre")
            )
            self.fields["tipo"].queryset = qs

    def save_ingreso(self, *, cochera, operador=None):
        if operador is None:
            operador = cochera.owner

        cliente_data = {
            "nombre": (self.cleaned_data.get("nombre") or "").strip(),
            "apellido": (self.cleaned_data.get("apellido") or "").strip(),
            "telefono": (self.cleaned_data.get("telefono") or "").strip(),
            "email": (self.cleaned_data.get("email") or "").strip().lower(),
        }
        patente_ult3 = self.cleaned_data.get("patente_ult3") or ""
        horas_previstas = int(self.cleaned_data.get("horas") or 1)

        movimiento = ingresar_vehiculo(
            cochera=cochera,
            operador=operador,
            # ticket => autogenerado en service
            ticket_prefix="QR",
            tipo=self.cleaned_data["tipo"],
            patente_ult3=patente_ult3,
            cliente_data=cliente_data,
            horas_previstas=horas_previstas,  
        )
        return movimiento


class CocheraForm(forms.ModelForm):
    class Meta:
        model = Cochera
        fields = ["nombre", "direccion"]


class CapacidadForm(forms.Form):
    def __init__(self, *args, **kwargs):
        tipos = kwargs.pop("tipos")
        super().__init__(*args, **kwargs)
        for tipo in tipos:
            self.fields[f"tipo_{tipo.id}"] = forms.IntegerField(
                min_value=0,
                required=True,
                label=f"Cantidad para {tipo.nombre}",
                initial=0,
            )


class TarifaForm(forms.Form):
    def __init__(self, *args, **kwargs):
        tipos = kwargs.pop("tipos")
        super().__init__(*args, **kwargs)
        for tipo in tipos:
            self.fields[f"precio_{tipo.id}"] = forms.DecimalField(
                min_value=0,
                required=True,
                decimal_places=2,
                max_digits=10,
                label=f"Precio por hora ({tipo.nombre})",
                initial=0,
            )


class EmpleadosForm(forms.Form):
    cantidad_empleados = forms.IntegerField(
        min_value=0,
        required=False,
        label="Cantidad de empleados",
        help_text="Opcional. Si lo completás, debe coincidir con la cantidad de emails.",
    )
    emails = forms.CharField(
        required=False,
        label="Emails de empleados",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "uno por línea"}),
    )

    def clean(self):
        cleaned = super().clean()
        raw = (cleaned.get("emails") or "").strip()
        cantidad = cleaned.get("cantidad_empleados")

        emails_list = []
        if raw:
            for line in raw.splitlines():
                e = line.strip().lower()
                if not e:
                    continue
                validate_email(e)
                emails_list.append(e)

        emails_list = list(dict.fromkeys(emails_list))

        if cantidad is not None and cantidad != len(emails_list):
            raise forms.ValidationError(
                f"La cantidad ({cantidad}) no coincide con los emails cargados ({len(emails_list)})."
            )

        cleaned["emails_list"] = emails_list
        return cleaned


# ─── Car wash forms ──────────────────────────────────────────────────────────

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "apellido", "telefono", "email", "observaciones", "es_vip"]
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }


class VehiculoForm(forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = ["patente", "marca", "modelo", "anio", "color", "tipo"]
        labels = {
            "patente": "Patente",
            "marca": "Marca",
            "modelo": "Modelo",
            "anio": "Año",
            "color": "Color",
            "tipo": "Tipo de vehículo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoEspacio.objects.all().order_by("nombre")
        self.fields["tipo"].empty_label = "Seleccioná el tipo"


class ServicioForm(forms.ModelForm):
    class Meta:
        model = Servicio
        fields = ["nombre", "descripcion", "precio", "duracion_minutos", "categoria", "activo"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 2}),
        }


class OrdenTrabajoForm(forms.Form):
    """
    Step 1: datos de cliente + vehículo + servicios + observaciones.
    """
    # Cliente
    cliente_nombre = forms.CharField(max_length=80, required=False, label="Nombre")
    cliente_apellido = forms.CharField(max_length=80, required=False, label="Apellido")
    cliente_telefono = forms.CharField(max_length=30, required=False, label="Teléfono")
    cliente_email = forms.EmailField(required=False, label="Email")

    # Vehículo
    vehiculo_patente = forms.CharField(
        max_length=10, required=True, label="Patente",
        widget=forms.TextInput(attrs={"placeholder": "ABC123", "class": "text-uppercase"}),
    )
    vehiculo_marca = forms.CharField(max_length=60, required=False, label="Marca")
    vehiculo_modelo = forms.CharField(max_length=60, required=False, label="Modelo")
    vehiculo_anio = forms.IntegerField(min_value=1900, max_value=2100, required=False, label="Año")
    vehiculo_color = forms.CharField(max_length=40, required=False, label="Color")
    vehiculo_tipo = forms.ModelChoiceField(
        queryset=TipoEspacio.objects.all().order_by("nombre"),
        empty_label="Tipo de vehículo",
        required=True,
        label="Tipo",
    )

    # Orden
    observaciones = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Observaciones",
    )
    entrega_estimada_at = forms.DateTimeField(
        required=False,
        label="Entrega estimada",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, cochera=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cochera = cochera
        if cochera:
            self.servicios_qs = Servicio.objects.filter(cochera=cochera, activo=True).order_by("categoria", "nombre")
        else:
            self.servicios_qs = Servicio.objects.none()


class TurnoForm(forms.ModelForm):
    class Meta:
        model = Turno
        fields = ["fecha", "hora", "duracion_minutos", "operador", "observaciones", "estado"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "hora": forms.TimeInput(attrs={"type": "time"}),
            "observaciones": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, cochera=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cochera:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields["operador"].queryset = User.objects.filter(
                cocheraempleado__cochera=cochera, cocheraempleado__activo=True
            ).distinct()
        self.fields["operador"].required = False
        self.fields["estado"].initial = Turno.PENDIENTE


# ─── Checklist ───────────────────────────────────────────────────────────────

class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["descripcion", "orden", "activo"]


# ─── Fotos ───────────────────────────────────────────────────────────────────

class FotoOrdenForm(forms.ModelForm):
    class Meta:
        model = FotoOrden
        fields = ["tipo", "imagen", "descripcion"]
        widgets = {"descripcion": forms.TextInput(attrs={"placeholder": "Ej: rayón puerta trasera"})}


# ─── Inventario ──────────────────────────────────────────────────────────────

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["nombre", "categoria", "descripcion", "unidad", "stock_minimo", "precio_unitario", "activo"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].required = False


class MovimientoInventarioForm(forms.ModelForm):
    class Meta:
        model = MovimientoInventario
        fields = ["tipo", "cantidad", "motivo"]

    def __init__(self, *args, producto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.producto = producto
        self.fields["cantidad"].min_value = 0

    def clean_cantidad(self):
        cantidad = self.cleaned_data["cantidad"]
        if cantidad <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor a 0.")
        tipo = self.cleaned_data.get("tipo")
        if tipo == MovimientoInventario.SALIDA and self.producto:
            if cantidad > self.producto.stock_actual:
                raise forms.ValidationError(
                    f"Stock insuficiente. Disponible: {self.producto.stock_actual} {self.producto.unidad}."
                )
        return cantidad


# ─── Membresías ──────────────────────────────────────────────────────────────

class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ["nombre", "descripcion", "precio_mensual", "lavados_incluidos", "descuento_pct", "activo", "servicios"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 2}),
            "servicios": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, cochera=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cochera:
            self.fields["servicios"].queryset = Servicio.objects.filter(cochera=cochera, activo=True)


class MembresiaForm(forms.ModelForm):
    class Meta:
        model = Membresia
        fields = ["plan", "cliente", "estado", "fecha_inicio", "fecha_vencimiento"]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_vencimiento": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, cochera=None, **kwargs):
        super().__init__(*args, **kwargs)
        if cochera:
            self.fields["plan"].queryset = Plan.objects.filter(cochera=cochera, activo=True)
            self.fields["cliente"].queryset = Cliente.objects.filter(ordenes__cochera=cochera).distinct()
