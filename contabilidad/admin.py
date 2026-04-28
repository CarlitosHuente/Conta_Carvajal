from django.contrib import admin
from .models import CodigoF29, DeclaracionF29, ReglaValidacion, CuentaContable, PlantillaCentralizacion, LineaPlantilla, AsientoContable, LineaAsiento

admin.site.register(CodigoF29)
admin.site.register(DeclaracionF29)

@admin.register(ReglaValidacion)
class ReglaValidacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigos_suma', 'codigos_resta', 'codigo_resultado', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)

@admin.register(CuentaContable)
class CuentaContableAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'empresa')
    list_filter = ('tipo', 'empresa')
    search_fields = ('codigo', 'nombre')

class LineaPlantillaInline(admin.TabularInline):
    model = LineaPlantilla
    extra = 2

@admin.register(PlantillaCentralizacion)
class PlantillaCentralizacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'empresa', 'tipo_origen')
    list_filter = ('empresa', 'tipo_origen')
    inlines = [LineaPlantillaInline]

class LineaAsientoInline(admin.TabularInline):
    model = LineaAsiento
    extra = 2

@admin.register(AsientoContable)
class AsientoContableAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'fecha', 'glosa', 'origen_f29')
    list_filter = ('empresa', 'fecha')
    search_fields = ('glosa',)
    inlines = [LineaAsientoInline]