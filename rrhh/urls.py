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
    path('contrato/<int:pk>/editar/', views.contrato_edit_view, name='contrato_edit'),
    path('contrato/<int:contrato_id>/items/', views.gestionar_items_contrato_view, name='gestionar_items_contrato'),

    # URLs para Conceptos Variables
    path('conceptos/', views.concepto_variable_list_view, name='concepto_variable_list'),
    path('conceptos/nuevo/', views.concepto_variable_create_view, name='concepto_variable_create'),
    path('conceptos/<int:pk>/editar/', views.concepto_variable_edit_view, name='concepto_variable_edit'),

    # URLs para Liquidaciones
    path('liquidacion/nueva/', views.crear_liquidacion_view, name='crear_liquidacion'),
    path('liquidacion/<int:pk>/', views.liquidacion_detail_view, name='liquidacion_detail'),
    path('liquidacion/<int:pk>/pdf/', views.liquidacion_pdf_view, name='liquidacion_pdf'),
    path('libro-remuneraciones/', views.libro_remuneraciones_view, name='libro_remuneraciones'),
    
    # API y Novedades
    path('api/get-indicadores/<int:ano>/<int:mes>/', views.api_get_indicadores_economicos, name='api_get_indicadores'),
    path('novedades/', views.ingresar_novedades_view, name='ingresar_novedades'),
    
    # NUEVAS URLs para Indicadores Económicos
    path('indicadores/', views.indicador_list_view, name='indicador_list'),
    path('indicadores/nuevo/', views.indicador_create_view, name='indicador_create'),
    path('indicadores/<int:pk>/editar/', views.indicador_edit_view, name='indicador_edit'),
    path('indicadores/<int:pk>/eliminar/', views.indicador_delete_view, name='indicador_delete'),
    path('afps/', views.afp_list_view, name='afp_list'),
    
    path('cobranza-maestro/', views.planilla_cobranza_view, name='planilla_cobranza'),
    path('cargar-base-rrhh/', views.cargar_datos_base_rrhh_view, name='cargar_base_rrhh'),
    path('cargar-indicadores-base/', views.cargar_indicadores_base_view, name='cargar_indicadores_base'),
]