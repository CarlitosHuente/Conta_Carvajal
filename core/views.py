from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Empresa
from .vista import es_admin_real, limpiar_vista_cliente


@login_required
def home_view(request):
    """
    Controlador de tráfico principal.
    - Si es admin, muestra el selector de empresas.
    - Si es cliente, selecciona su empresa y lo redirige al dashboard.
    """
    if 'empresa_activa_id' in request.session:
        del request.session['empresa_activa_id']
    limpiar_vista_cliente(request.session)

    if request.user.perfil.rol == 'admin':
        empresas = Empresa.objects.all()
        return render(request, 'core/seleccionar_empresa.html', {'empresas': empresas})
    else:
        empresa_cliente = request.user.perfil.empresa
        if empresa_cliente:
            request.session['empresa_activa_id'] = empresa_cliente.id
            return redirect('core:empresa_dashboard')
        else:
            return render(request, 'core/error_sin_empresa.html')


@login_required
def seleccionar_empresa_view(request, empresa_id):
    """Guarda la empresa seleccionada por el admin en la sesión y redirige al dashboard."""
    if request.user.perfil.rol != 'admin':
        return redirect('core:home')
    empresa = get_object_or_404(Empresa, id=empresa_id)
    request.session['empresa_activa_id'] = empresa.id
    limpiar_vista_cliente(request.session)
    return redirect('core:empresa_dashboard')


@login_required
def salir_empresa_view(request):
    """Limpia la empresa de la sesión y devuelve al admin al selector."""
    if 'empresa_activa_id' in request.session:
        del request.session['empresa_activa_id']
    limpiar_vista_cliente(request.session)
    return redirect('core:home')


@login_required
def empresa_dashboard_view(request):
    """Dashboard principal para la empresa que está activa en la sesión."""
    if not request.session.get('empresa_activa_id'):
        return redirect('core:home')
    return render(request, 'core/empresa_dashboard.html')


@login_required
def toggle_vista_cliente_view(request):
    """Alterna entre vista administrador y vista cliente simulada."""
    if not es_admin_real(request.user):
        return redirect('core:home')
    if request.method != 'POST':
        return redirect('core:empresa_dashboard')

    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, 'Selecciona una empresa para cambiar la vista.')
        return redirect('core:home')

    empresa = get_object_or_404(Empresa, id=empresa_id)
    modo = request.POST.get('modo', '')
    if modo == 'cliente':
        request.session['vista_cliente'] = True
        messages.info(request, f'Vista cliente activa: ves el sistema como {empresa.razon_social}.')
    else:
        limpiar_vista_cliente(request.session)
        messages.info(request, 'Vista administrador restaurada.')

    destino = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('core:empresa_dashboard')
    return redirect(destino)
