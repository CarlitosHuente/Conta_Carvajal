# rrhh/admin.py

from django.contrib import admin
from .models import (
    Empresa, AFP, SistemaSalud, Trabajador, 
    Contrato, ItemContrato, Liquidacion, ItemLiquidacion, Prestamo
)
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import PerfilUsuario
from .models import RegistroCobro

# --- INLINES ---

# ¡NUEVO! Inline para agregar ítems recurrentes en el Contrato
class ItemContratoInline(admin.TabularInline):
    model = ItemContrato
    extra = 1

class ItemLiquidacionInline(admin.TabularInline):
    model = ItemLiquidacion
    extra = 2
    fields = ('nombre', 'monto', 'tipo', 'es_imponible')
    
# --- ADMINS ---

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    # ... (sin cambios)
    list_display = ('rut', 'razon_social')
    search_fields = ('rut', 'razon_social')

@admin.register(Trabajador)
class TrabajadorAdmin(admin.ModelAdmin):
    # ... (sin cambios)
    list_display = ('rut', 'nombre_completo', 'empresa', 'email_personal', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('rut', 'nombres', 'apellido_paterno')
    
    fieldsets = (
        ('Información Principal', {'fields': ('empresa', 'rut', 'nombres', 'apellido_paterno', 'apellido_materno', 'activo')}),
        ('Datos Personales', {'fields': ('fecha_nacimiento', 'nacionalidad', 'estado_civil')}),
        ('Información de Contacto', {'fields': ('direccion', 'comuna', 'telefono', 'email_personal')}),
        ('Información Bancaria', {'fields': ('banco', 'tipo_cuenta', 'numero_cuenta')}),
        ('Acceso al Sistema', {'fields': ('user',), 'classes': ('collapse',)}),
    )

# ¡MODIFICADO! El ContratoAdmin ahora muestra sus ítems recurrentes
@admin.register(Contrato)
class ContratoAdmin(admin.ModelAdmin):
    list_display = ('trabajador', 'fecha_inicio', 'sueldo_base', 'vigente')
    list_filter = ('vigente', 'trabajador__empresa')
    search_fields = ('trabajador__rut', 'trabajador__nombres')
    
    inlines = [ItemContratoInline] # <--- ¡AQUÍ AGREGAMOS EL INLINE!

@admin.register(Liquidacion)
class LiquidacionAdmin(admin.ModelAdmin):
    list_display = ('contrato', 'mes', 'ano', 'sueldo_liquido')
    list_filter = ('ano', 'contrato__trabajador__empresa')
    inlines = [ItemLiquidacionInline]

    # ¡LÓGICA CORREGIDA Y MEJORADA!
    # Sobrescribimos el formulario para pasarle datos iniciales
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None and 'contrato' in request.GET: # Solo al añadir y si el contrato está en la URL
            contrato_id = request.GET.get('contrato')
            self.contrato_id_for_inlines = contrato_id # Guardamos el ID para usarlo después
        return form

    # Usamos el ID guardado para poblar los inlines
    def get_formsets_with_inlines(self, request, obj=None):
        for formset in super().get_formsets_with_inlines(request, obj):
            if obj is None and hasattr(self, 'contrato_id_for_inlines'):
                try:
                    contrato = Contrato.objects.get(id=self.contrato_id_for_inlines)
                    initial_data = []
                    # 1. Haberes fijos del Contrato
                    initial_data.append({'nombre': 'Sueldo Base', 'monto': contrato.sueldo_base, 'tipo': 'HABER', 'es_imponible': True})
                    if contrato.colacion > 0:
                        initial_data.append({'nombre': 'Colación', 'monto': contrato.colacion, 'tipo': 'HABER', 'es_imponible': False})
                    if contrato.movilizacion > 0:
                        initial_data.append({'nombre': 'Movilización', 'monto': contrato.movilizacion, 'tipo': 'HABER', 'es_imponible': False})
                    
                    # 2. Copiamos todos los Items Recurrentes del Contrato
                    for item in contrato.items_recurrentes.all():
                        initial_data.append({
                            'nombre': item.nombre, 'monto': item.monto,
                            'tipo': item.tipo, 'es_imponible': item.es_imponible
                        })

                    formset.initial = initial_data
                except Contrato.DoesNotExist:
                    pass
                # Limpiamos la variable para futuras llamadas
                del self.contrato_id_for_inlines
            yield formset

# SECCION: Integración de Perfil en el Admin de Usuarios
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Información de Rol y Empresa'

class UserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline,)
    # Opcional: Mostrar el rol en la lista de usuarios
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_rol')

    def get_rol(self, instance):
        return instance.perfil.rol if hasattr(instance, 'perfil') else "Sin Rol"
    get_rol.short_description = 'Rol'
    
@admin.register(RegistroCobro)
class RegistroCobroAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'mes', 'ano', 'monto_uf', 'total_pesos', 'nro_bh_emitida', 'pagado')
    list_filter = ('mes', 'ano', 'pagado', 'empresa')
    search_fields = ('empresa__razon_social', 'nro_bh_emitida')
    # Ordenamos para ver lo más reciente arriba
    ordering = ('-ano', '-mes')

# Reinscribimos el modelo User con nuestra nueva configuración
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(AFP)
admin.site.register(SistemaSalud)
admin.site.register(Prestamo)