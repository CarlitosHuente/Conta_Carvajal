# rrhh/urls.py

from django.urls import path
from . import views

app_name = 'rrhh'

urlpatterns = [
    # URLs para Gestión de Empresas
    path('empresas/', views.empresa_list_view, name='empresa_list'),
    path('empresa/nueva/', views.empresa_create_view, name='empresa_create'),

    # NUEVAS URLs para Gestión de Trabajadores
    path('trabajadores/', views.trabajador_list_view, name='trabajador_list'),
    path('trabajador/nuevo/', views.trabajador_create_view, name='trabajador_create'),
    path('trabajador/<int:pk>/', views.trabajador_detail_view, name='trabajador_detail'),
    path('trabajador/<int:trabajador_pk>/contrato/nuevo/', views.contrato_create_view, name='contrato_create'),

    # URLs para Liquidaciones
    path('liquidacion/nueva/', views.crear_liquidacion_view, name='crear_liquidacion'),
    path('api/cargar-datos-contrato/<int:contrato_id>/', views.cargar_datos_contrato_api, name='api_cargar_datos_contrato'),
    
    # NUEVAS URLs para Indicadores Económicos
    path('indicadores/', views.indicador_list_view, name='indicador_list'),
    path('indicadores/nuevo/', views.indicador_create_view, name='indicador_create'),
]