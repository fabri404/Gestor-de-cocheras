from django import forms
from django.core.validators import validate_email
from uuid import uuid4

from .services_movimientos import ingresar_vehiculo
from .models import Cochera, TipoEspacio


class PublicIngresoForm(forms.Form):
    tipo = forms.ModelChoiceField(
        queryset=TipoEspacio.objects.none(),
        empty_label="Seleccioná el tipo de vehículo",
        required=True,
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

    def clean_patente_ult3(self):
        v = (self.cleaned_data.get("patente_ult3") or "").strip().upper()
        if not v:
            return ""
        v = v.replace(" ", "")
        if len(v) != 3:
            raise forms.ValidationError("La patente (últimos 3) debe tener exactamente 3 caracteres.")
        if not v.isalnum():
            raise forms.ValidationError("La patente solo puede tener letras y números.")
        return v

    def _gen_ticket(self) -> str:
        # <= 20 chars, único a nivel DB (hay constraint unique en ticket)
        return f"QR-{uuid4().hex[:8].upper()}"

    def save_ingreso(self, *, cochera, operador=None):
        """
        - cochera: Cochera destino
        - operador: usuario que queda como operador del movimiento.
          Para flujo público (QR), si no pasás operador, usamos el owner de la cochera.
        """
        if operador is None:
            operador = cochera.owner  # fallback seguro para no romper la lógica/métricas

        ticket = self._gen_ticket()
        cliente_data = {
            "nombre": (self.cleaned_data.get("nombre") or "").strip(),
            "apellido": (self.cleaned_data.get("apellido") or "").strip(),
            "telefono": (self.cleaned_data.get("telefono") or "").strip(),
            "email": (self.cleaned_data.get("email") or "").strip().lower(),
        }
        patente_ult3 = self.cleaned_data.get("patente_ult3") or ""

        movimiento = ingresar_vehiculo(
            cochera=cochera,
            operador=operador,
            ticket=ticket,
            tipo=self.cleaned_data["tipo"],
            patente_ult3=patente_ult3,
            cliente_data=cliente_data,
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

        # unique preservando orden
        emails_list = list(dict.fromkeys(emails_list))

        if cantidad is not None and cantidad != len(emails_list):
            raise forms.ValidationError(
                f"La cantidad ({cantidad}) no coincide con los emails cargados ({len(emails_list)})."
            )

        cleaned["emails_list"] = emails_list
        return cleaned
