from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # El home ahora es el selector de empresas (para admin) o el redirect (para cliente)
    path('', views.home_view, name='home'),
    
    # El dashboard específico de la empresa en sesión
    path('empresa/dashboard/', views.empresa_dashboard_view, name='empresa_dashboard'),
    path('empresa/seleccionar/<int:empresa_id>/', views.seleccionar_empresa_view, name='seleccionar_empresa'),
    path('empresa/salir/', views.salir_empresa_view, name='salir_empresa'),
]