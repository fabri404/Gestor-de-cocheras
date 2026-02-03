from django import forms
from django.core.validators import validate_email
from .models import Cochera


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

        # unique
        emails_list = list(dict.fromkeys(emails_list))

        if cantidad is not None and cantidad != len(emails_list):
            raise forms.ValidationError(
                f"La cantidad ({cantidad}) no coincide con los emails cargados ({len(emails_list)})."
            )

        cleaned["emails_list"] = emails_list
        return cleaned
