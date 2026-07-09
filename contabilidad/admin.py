from django.contrib import admin
from .models import (
    CodigoF29, DeclaracionF29, ReglaValidacion, CuentaContable,
    PlantillaCentralizacion, LineaPlantilla, AsientoContable, LineaAsiento,
    AplicacionCobroPago, AccionRapida, LineaAccionRapida, CuentaAccionRapida,
    ProveedorGlobal, EmpresaProveedor, ImportacionRCVCompra, DocumentoCompraRCV,
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


class CuentaAccionRapidaInline(admin.TabularInline):
    model = CuentaAccionRapida
    extra = 0


@admin.register(AccionRapida)
class AccionRapidaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'empresa', 'tipo', 'lado_pendiente', 'activa')
    list_filter = ('tipo', 'activa', 'empresa')
    inlines = [LineaAccionRapidaInline, CuentaAccionRapidaInline]


@admin.register(ProveedorGlobal)
class ProveedorGlobalAdmin(admin.ModelAdmin):
    list_display = ('rut', 'razon_social', 'rubro', 'activo')
    search_fields = ('rut', 'razon_social')


@admin.register(ImportacionRCVCompra)
class ImportacionRCVCompraAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'mes', 'ano', 'filas_nuevas', 'creado')
    list_filter = ('ano', 'mes', 'empresa')


@admin.register(DocumentoCompraRCV)
class DocumentoCompraRCVAdmin(admin.ModelAdmin):
    list_display = ('folio', 'tipo_doc', 'proveedor', 'empresa', 'monto_total', 'estado')
    list_filter = ('estado', 'tipo_doc', 'empresa')
