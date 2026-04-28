from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Empresa

@login_required
def home_view(request):
    """
    Controlador de tráfico principal.
    - Si es admin, muestra el selector de empresas.
    - Si es cliente, selecciona su empresa y lo redirige al dashboard.
    """
    # Limpiamos cualquier contexto de empresa previo para empezar de cero.
    if 'empresa_activa_id' in request.session:
        del request.session['empresa_activa_id']

    if request.user.perfil.rol == 'admin':
        empresas = Empresa.objects.all()
        return render(request, 'core/seleccionar_empresa.html', {'empresas': empresas})
    else:
        # Es un cliente, lo asignamos a su empresa y lo mandamos a su dashboard
        empresa_cliente = request.user.perfil.empresa
        if empresa_cliente:
            request.session['empresa_activa_id'] = empresa_cliente.id
            return redirect('core:empresa_dashboard')
        else:
            # Caso borde: cliente sin empresa asignada
            return render(request, 'core/error_sin_empresa.html')

@login_required
def seleccionar_empresa_view(request, empresa_id):
    """Guarda la empresa seleccionada por el admin en la sesión y redirige al dashboard."""
    if request.user.perfil.rol != 'admin':
        return redirect('core:home')
    empresa = get_object_or_404(Empresa, id=empresa_id)
    request.session['empresa_activa_id'] = empresa.id
    return redirect('core:empresa_dashboard')

@login_required
def salir_empresa_view(request):
    """Limpia la empresa de la sesión y devuelve al admin al selector."""
    if 'empresa_activa_id' in request.session:
        del request.session['empresa_activa_id']
    return redirect('core:home')

@login_required
def empresa_dashboard_view(request):
    """Dashboard principal para la empresa que está activa en la sesión."""
    if not request.session.get('empresa_activa_id'):
        return redirect('core:home')
    # El objeto 'empresa_activa' ya está disponible en el template gracias al context processor.
    return render(request, 'core/empresa_dashboard.html')
