from django.contrib import admin
from .models import CodigoF29, DeclaracionF29, ReglaValidacion

admin.site.register(CodigoF29)
admin.site.register(DeclaracionF29)

@admin.register(ReglaValidacion)
class ReglaValidacionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigos_suma', 'codigos_resta', 'codigo_resultado', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre',)