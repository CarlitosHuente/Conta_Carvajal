from django.contrib import admin
from .models import (
    CodigoF29, DeclaracionF29, ReglaValidacion, CuentaContable,
    PlantillaCentralizacion, LineaPlantilla, AsientoContable, LineaAsiento,
    AplicacionCobroPago, AccionRapidaCuenta, LineaAccionRapida,
)

admin.site.register(CodigoF29)
admin.site.register(DeclaracionF29)

@admin.register(ReglaValidacion)
class ReglaValidacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigos_suma', 'codigos_resta', 'codigo_resultado', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)

@admin.register(CuentaContable)
class CuentaContableAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'subtipo_operacion', 'empresa')
    list_filter = ('tipo', 'subtipo_operacion', 'empresa')
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
    list_display = ('id', 'empresa', 'fecha', 'glosa', 'tipo_asiento', 'origen_f29')
    list_filter = ('empresa', 'fecha', 'tipo_asiento')
    search_fields = ('glosa',)
    inlines = [LineaAsientoInline]


@admin.register(AplicacionCobroPago)
class AplicacionCobroPagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo', 'monto', 'asiento_pago', 'linea_origen')
    list_filter = ('tipo',)


class LineaAccionRapidaInline(admin.TabularInline):
    model = LineaAccionRapida
    extra = 1


@admin.register(AccionRapidaCuenta)
class AccionRapidaCuentaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cuenta', 'tipo', 'lado_pendiente', 'activa')
    list_filter = ('tipo', 'activa')
    inlines = [LineaAccionRapidaInline]