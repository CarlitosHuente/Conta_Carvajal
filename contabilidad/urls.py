from django.urls import path
from . import views, views_libros

app_name = 'contabilidad'

urlpatterns = [
    path('', views.contabilidad_hub_view, name='hub'),
    path('f29/', views.f29_lista_view, name='f29_lista'),
    path('f29/subir/', views.f29_subir_view, name='f29_subir'),
    path('f29/pdf-temporal/<str:token>/', views.f29_pdf_temporal_view, name='f29_pdf_temporal'),
    path('f29/guardar/', views.f29_guardar_view, name='f29_guardar'),
    path('f29/<int:pk>/', views.f29_detalle_view, name='f29_detalle'),
    path('f29/<int:pk>/eliminar/', views.f29_eliminar_view, name='f29_eliminar'),
    path('f29/<int:pk>/recalcular/', views.f29_recalcular_view, name='f29_recalcular'),
    path('f29/<int:pk>/editar/', views.f29_editar_view, name='f29_editar'),
    path('f29/<int:pk>/centralizar/', views.f29_centralizar_view, name='f29_centralizar'),

    # --- PLAN DE CUENTAS ---
    path('plan-cuentas/', views.plan_cuentas_lista_view, name='plan_cuentas_lista'),
    path('plan-cuentas/crear/', views.plan_cuentas_crear_view, name='plan_cuentas_crear'),
    path('plan-cuentas/cargar-base/', views.plan_cuentas_cargar_base_view, name='plan_cuentas_cargar_base'),
    path('plan-cuentas/exportar/', views.plan_cuentas_exportar_view, name='plan_cuentas_exportar'),
    path('plan-cuentas/importar/', views.plan_cuentas_importar_view, name='plan_cuentas_importar'),
    path('plan-cuentas/vaciar/', views.plan_cuentas_vaciar_view, name='plan_cuentas_vaciar'),
    path('plan-cuentas/<int:pk>/editar/', views.plan_cuentas_editar_view, name='plan_cuentas_editar'),
    path('plan-cuentas/<int:pk>/acciones/', views.plan_cuentas_acciones_view, name='plan_cuentas_acciones'),
    path('plan-cuentas/<int:pk>/eliminar/', views.plan_cuentas_eliminar_view, name='plan_cuentas_eliminar'),

    # --- PLANTILLAS DE CENTRALIZACIÓN ---
    path('plantillas/', views.plantilla_lista_view, name='plantilla_lista'),
    path('plantillas/crear/', views.plantilla_crear_view, name='plantilla_crear'),
    path('plantillas/copiar/', views.plantilla_copiar_view, name='plantilla_copiar'),
    path('plantillas/<int:pk>/editar/', views.plantilla_editar_view, name='plantilla_editar'),

    # --- LIBRO DIARIO ---
    path('libro-diario/', views.libro_diario_view, name='libro_diario'),
    path('libro-diario/nuevo/', views_libros.asiento_crear_view, name='asiento_crear'),
    path('libro-diario/asiento/<int:pk>/', views.asiento_detalle_view, name='asiento_detalle'),

    # --- LIBRO MAYOR Y BALANCE ---
    path('libro-mayor/', views_libros.libro_mayor_view, name='libro_mayor'),
    path('libro-mayor/cuenta/<int:pk>/', views_libros.libro_mayor_cuenta_view, name='libro_mayor_cuenta'),
    path('balance/', views_libros.balance_view, name='balance'),
]