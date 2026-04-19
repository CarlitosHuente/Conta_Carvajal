from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.models import Empresa
from rrhh.models import Trabajador # Necesario solo para contar en el dashboard

@login_required
def home_redirect_view(request):
    """Controlador de tráfico: Envía a cada usuario a su portal según su rol"""
    if request.user.perfil.rol == 'admin':
        return redirect('core:dashboard_admin')
    else:
        return redirect('core:home_cliente')

@login_required
def dashboard_admin_view(request):
    """Vista principal para el rol de Administrador."""
    if request.user.perfil.rol != 'admin':
        return redirect('core:home_cliente')

    context = {
        'total_empresas': Empresa.objects.count(),
        'total_trabajadores': Trabajador.objects.filter(activo=True).count(),
    }
    return render(request, 'core/dashboard_admin.html', context)

@login_required
def home_cliente_view(request):
    empresa = request.user.perfil.empresa
    if not empresa:
        return render(request, 'core/home_cliente.html', {'error': 'No tienes una empresa asignada. Contacta al administrador.'})

    return render(request, 'core/home_cliente.html', {'empresa': empresa})
