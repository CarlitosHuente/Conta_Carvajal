from django.contrib import admin
from django import forms
from .models import PerfilUsuario, PermisoAccesoUsuario


SUBMODULO_CHOICES = [
    ('', 'Todos los submódulos del módulo'),
    ('trabajadores', 'RR.HH - Trabajadores'),
    ('novedades', 'RR.HH - Novedades'),
    ('liquidaciones', 'RR.HH - Liquidaciones'),
    ('f29', 'Contabilidad - F29'),
    ('libro_diario', 'Contabilidad - Libro Diario'),
    ('plan_cuentas', 'Contabilidad - Plan de Cuentas'),
    ('plantillas', 'Contabilidad - Plantillas'),
]

SUBMODULOS_VALIDOS_POR_MODULO = {
    'rrhh': {'', 'trabajadores', 'novedades', 'liquidaciones'},
    'contabilidad': {'', 'f29', 'libro_diario', 'plan_cuentas', 'plantillas'},
    'cobranza': {''},
}


class PermisoAccesoUsuarioAdminForm(forms.ModelForm):
    submodulo = forms.ChoiceField(
        choices=SUBMODULO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'vTextField'})
    )

    class Meta:
        model = PermisoAccesoUsuario
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        modulo = cleaned_data.get('modulo')
        submodulo = cleaned_data.get('submodulo') or ''
        validos = SUBMODULOS_VALIDOS_POR_MODULO.get(modulo, {''})
        if submodulo not in validos:
            raise forms.ValidationError(
                "El submódulo seleccionado no corresponde al módulo indicado."
            )
        return cleaned_data


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('user', 'rol', 'empresa')
    list_filter = ('rol', 'empresa')
    search_fields = ('user__username', 'user__email')


@admin.register(PermisoAccesoUsuario)
class PermisoAccesoUsuarioAdmin(admin.ModelAdmin):
    form = PermisoAccesoUsuarioAdminForm
    list_display = ('user', 'empresa', 'modulo', 'submodulo', 'accion', 'permitido')
    list_filter = ('empresa', 'modulo', 'accion', 'permitido')
    search_fields = ('user__username', 'empresa__razon_social', 'submodulo')
