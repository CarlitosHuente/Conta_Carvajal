from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views # <--- SECCION 1: Importar vistas de auth
from .views import home_redirect_view # <--- SECCION 2: Importar nuestra nueva lógica

urlpatterns = [
    # Si entran a la raíz, ejecutamos una lógica de redirección
    path('', home_redirect_view, name='home'), 
    
    # Rutas de autenticación (Login/Logout)
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('admin/', admin.site.urls),
    path('rrhh/', include('rrhh.urls')),
]