from django import forms
from .models import CuentaContable

class CuentaContableForm(forms.ModelForm):
    class Meta:
        model = CuentaContable
        fields = ['codigo', 'nombre', 'tipo']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 1.1.01.01'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: IVA Crédito Fiscal'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
        }