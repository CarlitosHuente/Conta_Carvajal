# rrhh/forms.py

from django import forms
from .models import Empresa, Trabajador, Contrato, IndicadorEconomico

class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ['rut', 'razon_social', 'logo']
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
        }
        
class TrabajadorForm(forms.ModelForm):
    class Meta:
        model = Trabajador
        # Seleccionamos los campos que queremos en el formulario de creación
        fields = [
            'empresa', 'rut', 'nombres', 'apellido_paterno', 'apellido_materno',
            'fecha_nacimiento', 'nacionalidad', 'estado_civil', 'direccion', 
            'comuna', 'telefono', 'email_personal', 'banco', 'tipo_cuenta', 'numero_cuenta'
        ]
        
        # Agregamos widgets para darles estilo y funcionalidad
        widgets = {
            'empresa': forms.Select(attrs={'class': 'form-select'}),
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_nacimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nacionalidad': forms.TextInput(attrs={'class': 'form-control'}),
            'estado_civil': forms.Select(attrs={'class': 'form-select'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
            'comuna': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'email_personal': forms.EmailInput(attrs={'class': 'form-control'}),
            'banco': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control'}),
        }
        
class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        # Excluimos el trabajador porque lo asignaremos automáticamente
        exclude = ['trabajador', 'vigente']

        # Damos estilo a los campos
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'afp': forms.Select(attrs={'class': 'form-select'}),
            'sistema_salud': forms.Select(attrs={'class': 'form-select'}),
            'plan_salud_pactado': forms.NumberInput(attrs={'class': 'form-control'}),
            'moneda_plan_salud': forms.Select(attrs={'class': 'form-select'}),
            'sueldo_base': forms.NumberInput(attrs={'class': 'form-control'}),
            'colacion': forms.NumberInput(attrs={'class': 'form-control'}),
            'movilizacion': forms.NumberInput(attrs={'class': 'form-control'}),
            'tipo_gratificacion': forms.Select(attrs={'class': 'form-select'}),
            'monto_gratificacion_fija': forms.NumberInput(attrs={'class': 'form-control'}),
            'tipo_jornada': forms.Select(attrs={'class': 'form-select'}),
            'horas_semanales': forms.NumberInput(attrs={'class': 'form-control'}),
            'dias_semana': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class IndicadorEconomicoForm(forms.ModelForm):
    class Meta:
        model = IndicadorEconomico
        fields = '__all__' # Incluir todos los campos del modelo

        # Damos estilo a los campos para que se vean bien con Bootstrap
        widgets = {
            'mes': forms.NumberInput(attrs={'class': 'form-control'}),
            'ano': forms.NumberInput(attrs={'class': 'form-control'}),
            'uf': forms.NumberInput(attrs={'class': 'form-control'}),
            'utm': forms.NumberInput(attrs={'class': 'form-control'}),
            'sueldo_minimo': forms.NumberInput(attrs={'class': 'form-control'}),
            'tope_imponible_afp_uf': forms.NumberInput(attrs={'class': 'form-control'}),
            'tope_imponible_afp_pesos': forms.NumberInput(attrs={'class': 'form-control'}),
            'tope_imponible_cesantia_uf': forms.NumberInput(attrs={'class': 'form-control'}),
            'tope_imponible_cesantia_pesos': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_sis': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_a_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_a_limite': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_b_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_b_limite': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_c_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_c_limite': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        