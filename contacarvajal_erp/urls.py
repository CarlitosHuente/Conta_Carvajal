from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView # <--- Necesario para la portada simple

urlpatterns = [
    # Portada (Home)
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # Tus aplicaciones
    path('rrhh/', include('rrhh.urls')),
]