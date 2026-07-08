# rrhh/urls.py

from django.urls import path
from . import views
from . import views_operaciones

app_name = 'rrhh'

urlpatterns = [
    path('', views_operaciones.rrhh_hub_view, name='hub'),

    # URLs para Gestión de Empresas
    path('empresas/', views.empresa_list_view, name='empresa_list'),
    path('empresa/nueva/', views.empresa_create_view, name='empresa_create'),

    # NUEVAS URLs para Gestión de Trabajadores
    path('trabajadores/', views.trabajador_list_view, name='trabajador_list'),
    path('trabajador/nuevo/', views.trabajador_create_view, name='trabajador_create'),
    path('trabajador/<int:pk>/', views.trabajador_detail_view, name='trabajador_detail'),
    path('trabajador/<int:pk>/editar/', views_operaciones.trabajador_edit_view, name='trabajador_edit'),
    path('trabajador/<int:pk>/estado/', views_operaciones.trabajador_toggle_activo_view, name='trabajador_toggle_activo'),
    path('trabajador/<int:trabajador_pk>/cargas/', views_operaciones.gestionar_cargas_familiares_view, name='gestionar_cargas'),
    path('trabajador/<int:trabajador_pk>/vacaciones/', views_operaciones.gestionar_vacaciones_view, name='gestionar_vacaciones'),
    path('trabajador/<int:trabajador_pk>/contrato/nuevo/', views.contrato_create_view, name='contrato_create'),
    path('contrato/<int:pk>/editar/', views.contrato_edit_view, name='contrato_edit'),
    path('contrato/<int:contrato_id>/items/', views.gestionar_items_contrato_view, name='gestionar_items_contrato'),
    path('contrato/<int:contrato_id>/prestamos/', views_operaciones.gestionar_prestamos_view, name='gestionar_prestamos'),
    path('contrato/<int:contrato_id>/terminar/', views_operaciones.terminar_contrato_view, name='terminar_contrato'),

    # URLs para Conceptos Variables
    path('conceptos/', views.concepto_variable_list_view, name='concepto_variable_list'),
    path('conceptos/nuevo/', views.concepto_variable_create_view, name='concepto_variable_create'),
    path('conceptos/<int:pk>/editar/', views.concepto_variable_edit_view, name='concepto_variable_edit'),

    # URLs para Liquidaciones
    path('liquidacion/nueva/', views.crear_liquidacion_view, name='crear_liquidacion'),
    path('liquidacion/<int:pk>/', views.liquidacion_detail_view, name='liquidacion_detail'),
    path('liquidacion/<int:pk>/pdf/', views.liquidacion_pdf_view, name='liquidacion_pdf'),
    path('libro-remuneraciones/', views.libro_remuneraciones_view, name='libro_remuneraciones'),
    path('export-previred/', views_operaciones.export_previred_view, name='export_previred'),
    path('config-centralizacion-rrhh/', views_operaciones.configurar_centralizacion_rrhh_view, name='config_centralizacion_rrhh'),
    path('centralizar-remuneraciones/', views_operaciones.centralizar_remuneraciones_view, name='centralizar_remuneraciones'),
    path('finiquitos/', views_operaciones.finiquito_list_view, name='finiquito_list'),
    path('finiquito/<int:pk>/', views_operaciones.finiquito_detail_view, name='finiquito_detail'),
    
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