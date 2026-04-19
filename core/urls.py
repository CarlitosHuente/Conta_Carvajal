from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_redirect_view, name='home'),
    path('dashboard/', views.dashboard_admin_view, name='dashboard_admin'),
    path('portal/', views.home_cliente_view, name='home_cliente'),
]