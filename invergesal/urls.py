from django.urls import path

from . import views

app_name = 'invergesal'

urlpatterns = [
    path('', views.estadisticas, name='estadisticas'),
    path('generar-reporte/', views.generar_reporte, name='generar_reporte'),
    path('detalle-puerto/', views.detalle_puerto, name='detalle_puerto'),
    path('descargar-reporte/', views.descargar_reporte, name='descargar_reporte'),
    path('descargar-reporte-pdf/', views.descargar_reporte_pdf, name='descargar_reporte_pdf'),
    path('descargar-filtrado/', views.descargar_filtrado, name='descargar_filtrado'),
    path('saldos-ecuador/', views.saldos_ecuador, name='saldos_ecuador'),
    path('saldos-ecuador/tc-extra/', views.guardar_tc_extra_liquidacion, name='guardar_tc_extra'),
    path('saldos-ecuador/parametros/', views.guardar_parametro_gasto, name='guardar_parametro_gasto'),
    path('saldos-ecuador/conexiones/', views.guardar_conexiones_saldos, name='guardar_conexiones_saldos'),
    path('saldos-ecuador/actualizar/', views.actualizar_saldos_ecuador, name='actualizar_saldos_ecuador'),
    path('escalas/', views.calendario_escalas, name='calendario_escalas'),
    path('escalas/dias-viaje/', views.guardar_dias_viaje_view, name='guardar_dias_viaje'),
]
