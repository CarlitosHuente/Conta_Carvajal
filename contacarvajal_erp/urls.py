from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views # <--- SECCION 1: Importar vistas de auth
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # El inicio de la aplicación ahora lo domina CORE
    path('', include('core.urls')), 
    
    # Rutas de autenticación (Login/Logout)
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('admin/', admin.site.urls),
    path('rrhh/', include('rrhh.urls')),
    path('contabilidad/', include('contabilidad.urls')), # <--- Agregamos el nuevo módulo
]

# Permite a Django mostrar los PDFs temporales y logos en modo de desarrollo (DEBUG = True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)