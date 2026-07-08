from django import forms
from .models import CuentaContable

class CuentaContableForm(forms.ModelForm):
    class Meta:
        model = CuentaContable
        fields = ['codigo', 'nombre', 'tipo', 'subtipo_operacion']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 1.01.05'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: IVA Crédito Fiscal'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'subtipo_operacion': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, bloquear_estructura=False, **kwargs):
        super().__init__(*args, **kwargs)
        if bloquear_estructura:
            self.fields['codigo'].disabled = True
            self.fields['tipo'].disabled = True