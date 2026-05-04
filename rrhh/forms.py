# rrhh/forms.py

from django import forms
from .models import Trabajador, Contrato, IndicadorEconomico, NovedadMensual, ItemContrato, ConceptoVariable, TramoConcepto
from core.models import Empresa

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
    BANCOS_CHILE_CHOICES = [
        ('', 'Selecciona banco...'),
        ('BancoEstado', 'BancoEstado'),
        ('Banco de Chile', 'Banco de Chile'),
        ('Banco Santander', 'Banco Santander'),
        ('BCI', 'BCI'),
        ('Scotiabank', 'Scotiabank'),
        ('Itaú', 'Itaú'),
        ('Banco Security', 'Banco Security'),
        ('Banco Falabella', 'Banco Falabella'),
        ('Banco Ripley', 'Banco Ripley'),
        ('Banco Consorcio', 'Banco Consorcio'),
        ('Banco Internacional', 'Banco Internacional'),
    ]
    TIPO_CUENTA_CHOICES = [
        ('', 'Selecciona tipo de cuenta...'),
        ('Cuenta Corriente', 'Cuenta Corriente'),
        ('Cuenta Vista', 'Cuenta Vista'),
        ('Cuenta de Ahorro', 'Cuenta de Ahorro'),
        ('Cuenta RUT', 'Cuenta RUT'),
    ]

    banco = forms.ChoiceField(
        choices=BANCOS_CHILE_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    tipo_cuenta = forms.ChoiceField(
        choices=TIPO_CUENTA_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

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
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56912345678'}),
            'email_personal': forms.EmailInput(attrs={'class': 'form-control'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 1234567890'}),
        }

    def __init__(self, *args, **kwargs):
        self.empresa_fija_id = kwargs.pop('empresa_fija_id', None)
        super().__init__(*args, **kwargs)
        self.fields['nacionalidad'].initial = self.initial.get('nacionalidad') or 'Chilena'
        self.fields['tipo_cuenta'].initial = self.initial.get('tipo_cuenta') or 'Cuenta RUT'
        if self.empresa_fija_id:
            self.fields['empresa'].widget = forms.HiddenInput()
            self.fields['empresa'].required = False

    def clean_rut(self):
        rut = (self.cleaned_data.get('rut') or '').strip().upper().replace('.', '')
        if '-' not in rut:
            raise forms.ValidationError("Formato de RUT inválido. Usa formato 12345678-9.")

        cuerpo, dv = rut.split('-', 1)
        if not cuerpo.isdigit() or not dv:
            raise forms.ValidationError("Formato de RUT inválido. Usa formato 12345678-9.")
        if len(cuerpo) < 7:
            raise forms.ValidationError("RUT inválido: largo insuficiente.")

        dv_esperado = self._calcular_dv_rut(cuerpo)
        if dv != dv_esperado:
            raise forms.ValidationError("RUT inválido: dígito verificador no coincide.")

        return f"{int(cuerpo)}-{dv}"

    @staticmethod
    def _calcular_dv_rut(cuerpo):
        suma = 0
        multiplicador = 2
        for digito in reversed(cuerpo):
            suma += int(digito) * multiplicador
            multiplicador = 2 if multiplicador == 7 else multiplicador + 1
        resto = 11 - (suma % 11)
        if resto == 11:
            return '0'
        if resto == 10:
            return 'K'
        return str(resto)
        
class ContratoForm(forms.ModelForm):
    @staticmethod
    def _normalizar_decimal_plan_salud(raw):
        """Acepta 3.357, 3,357 o 1.234,567 (miles CL + decimal coma) para el plan en UF/CLP."""
        if raw is None:
            return ''
        s = str(raw).strip().replace(' ', '')
        if not s:
            return s
        if ',' in s and '.' in s:
            if s.rfind(',') > s.rfind('.'):
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
        elif ',' in s:
            s = s.replace(',', '.')
        return s

    def __init__(self, *args, **kwargs):
        if args:
            data = args[0]
            if data is not None and hasattr(data, 'copy') and 'plan_salud_pactado' in data:
                data = data.copy()
                raw = data.get('plan_salud_pactado')
                if raw not in (None, ''):
                    data['plan_salud_pactado'] = self._normalizar_decimal_plan_salud(raw)
                args = (data,) + tuple(args[1:])
        super().__init__(*args, **kwargs)

    class Meta:
        model = Contrato
        # Excluimos el trabajador porque lo asignaremos automáticamente
        exclude = ['trabajador', 'vigente']

        # Damos estilo a los campos
        widgets = {
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'afp': forms.Select(attrs={'class': 'form-select'}),
            'sistema_salud': forms.Select(attrs={'class': 'form-select'}),
            'plan_salud_pactado': forms.TextInput(attrs={
                'class': 'form-control',
                'inputmode': 'decimal',
                'placeholder': 'Ej: 3,357 o 3.357 UF',
                'autocomplete': 'off',
            }),
            'moneda_plan_salud': forms.Select(attrs={'class': 'form-select'}),
            'sueldo_base': forms.NumberInput(attrs={'class': 'form-control'}),
            'colacion': forms.NumberInput(attrs={'class': 'form-control'}),
            'movilizacion': forms.NumberInput(attrs={'class': 'form-control'}),
            'tipo_gratificacion': forms.Select(attrs={'class': 'form-select'}),
            'monto_gratificacion_fija': forms.NumberInput(attrs={'class': 'form-control'}),
            'tipo_jornada': forms.Select(attrs={'class': 'form-select'}),
            'horas_semanales': forms.NumberInput(attrs={'class': 'form-control'}),
            'dias_semana': forms.NumberInput(attrs={'class': 'form-control'}),
            'conceptos_variables': forms.CheckboxSelectMultiple,
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
            'tasa_afp_capital': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_cuprum': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_habitat': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_modelo': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_planvital': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_provida': forms.NumberInput(attrs={'class': 'form-control'}),
            'tasa_afp_uno': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_a_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_a_limite': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_b_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_b_limite': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_c_monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'asig_familiar_tramo_c_limite': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class NovedadMensualForm(forms.ModelForm):
    class Meta:
        model = NovedadMensual
        fields = [
            'dias_licencia', 'dias_ausencia', 'horas_extras_50', 'horas_extras_100',
            'bono_esporadico', 'descuento_esporadico'
        ]
        widgets = {
            'dias_licencia': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 70px;'}),
            'dias_ausencia': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 70px;'}),
            'horas_extras_50': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 70px;'}),
            'horas_extras_100': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 70px;'}),
            'bono_esporadico': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 100px;'}),
            'descuento_esporadico': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 100px;'}),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos los conceptos variables que nos pasa la vista antes de iniciar el formulario
        self.conceptos = kwargs.pop('conceptos', [])
        super().__init__(*args, **kwargs)
        
        # Extraemos el JSON guardado previamente (si existe)
        datos_guardados = self.instance.datos_variables if self.instance and self.instance.pk else {}
        
        # Creamos un campo dinámico por cada concepto variable creado por la empresa
        for concepto in self.conceptos:
            field_name = f'concepto_{concepto.id}'
            initial_val = datos_guardados.get(str(concepto.id), 0)
            self.fields[field_name] = forms.IntegerField(
                required=False,
                initial=initial_val,
                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'style': 'min-width: 90px;'}),
                label=concepto.nombre
            )
            
    def get_conceptos_fields(self):
        """Método de ayuda para que el template HTML pueda dibujar las columnas dinámicas fácilmente"""
        for concepto in self.conceptos:
            yield (concepto, self[f'concepto_{concepto.id}'])
            
    def save(self, commit=True):
        # Sobreescribimos el guardado para empacar todas las columnas dinámicas dentro del JSONField
        instance = super().save(commit=False)
        datos_variables_json = {}
        for concepto in self.conceptos:
            valor = self.cleaned_data.get(f'concepto_{concepto.id}')
            if valor: # Solo guardamos si ingresó un valor mayor a 0
                datos_variables_json[str(concepto.id)] = valor
                
        instance.datos_variables = datos_variables_json
        if commit:
            instance.save()
        return instance
        
class ItemContratoForm(forms.ModelForm):
    class Meta:
        model = ItemContrato
        fields = ['nombre', 'monto', 'tipo', 'es_imponible']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Bono Responsabilidad'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
        }

class ConceptoVariableForm(forms.ModelForm):
    class Meta:
        model = ConceptoVariable
        fields = ['nombre', 'tipo_calculo', 'porcentaje_calculo', 'es_imponible']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_calculo': forms.Select(attrs={'class': 'form-select'}),
            'porcentaje_calculo': forms.NumberInput(attrs={'class': 'form-control'}),
            'es_imponible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class TramoConceptoForm(forms.ModelForm):
    class Meta:
        model = TramoConcepto
        fields = ['tramo_desde', 'tramo_hasta', 'porcentaje']
        widgets = {
            'tramo_desde': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ej: 0'}),
            'tramo_hasta': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ej: 1000000 (O vacío)'}),
            'porcentaje': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ej: 2.5'}),
        }