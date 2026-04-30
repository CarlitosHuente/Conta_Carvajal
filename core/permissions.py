from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import PermisoAccesoUsuario


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
            empresa_id = request.session.get('empresa_activa_id')
            if not empresa_id:
                messages.warning(request, "Debes seleccionar una empresa para continuar.")
                return redirect('core:home')

            if not _usuario_tiene_permiso(request.user, empresa_id, modulo, submodulo, accion):
                messages.error(request, "No tienes permiso para acceder a esta funcionalidad.")
                return redirect('core:empresa_dashboard')

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
