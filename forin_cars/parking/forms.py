from django import forms
from .models import Cochera, TipoEspacio, ConfigCapacidad


class CocheraForm(forms.ModelForm):
    class Meta:
        model = Cochera
        fields = ["nombre", "direccion"]


class CapacidadForm(forms.Form):
    """
    Renderiza un input por cada TipoEspacio.
    Ej: Auto=30, Moto=10, Bici=5
    """
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
