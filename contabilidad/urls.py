from django.urls import path
from . import views

app_name = 'contabilidad'

urlpatterns = [
    path('f29/', views.f29_lista_view, name='f29_lista'),
    path('f29/subir/', views.f29_subir_view, name='f29_subir'),
    path('f29/guardar/', views.f29_guardar_view, name='f29_guardar'),
    path('f29/<int:pk>/', views.f29_detalle_view, name='f29_detalle'),
    path('f29/<int:pk>/eliminar/', views.f29_eliminar_view, name='f29_eliminar'),
    path('f29/<int:pk>/recalcular/', views.f29_recalcular_view, name='f29_recalcular'),
    path('f29/<int:pk>/editar/', views.f29_editar_view, name='f29_editar'),
]