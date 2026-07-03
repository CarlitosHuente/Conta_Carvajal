from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import PermisoAccesoUsuario


def get_empresa_operativa_id(request):
    """
    Empresa cuyos datos operativos (trabajadores, contratos, etc.) debe ver el usuario.
    Admin: empresa activa en sesión. Cliente: empresa del perfil.
    """
    user = request.user
    if not hasattr(user, 'perfil'):
        return None
    if user.perfil.rol == 'cliente':
        return user.perfil.empresa_id
    return request.session.get('empresa_activa_id')


def ensure_empresa_operativa(request):
    """
    Devuelve (empresa_id, None) si hay contexto válido, o (None, redirect_response).
    """
    empresa_id = get_empresa_operativa_id(request)
    if not empresa_id:
        messages.warning(request, "Selecciona una empresa para continuar.")
        return None, redirect('core:home')
    return empresa_id, None


def _usuario_tiene_permiso(user, empresa_id, modulo, submodulo, accion):
    if not hasattr(user, 'perfil'):
        return False

    if user.is_superuser or user.perfil.rol == 'admin':
        return True

    permisos = PermisoAccesoUsuario.objects.filter(
        user=user,
        empresa_id=empresa_id,
        modulo=modulo,
        accion=accion,
        permitido=True
    )
    return permisos.filter(submodulo=submodulo).exists() or permisos.filter(submodulo='').exists()


def require_access(modulo, submodulo='', accion='ver'):
    """
    Valida permisos por empresa activa + modulo/submodulo/accion.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            empresa_id = get_empresa_operativa_id(request)
            if not empresa_id:
                messages.warning(request, "Debes seleccionar una empresa para continuar.")
                return redirect('core:home')

            if not _usuario_tiene_permiso(request.user, empresa_id, modulo, submodulo, accion):
                messages.error(request, "No tienes permiso para acceder a esta funcionalidad.")
                return redirect('core:empresa_dashboard')

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
