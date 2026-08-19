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
]
