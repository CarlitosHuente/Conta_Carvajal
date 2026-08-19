from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def usuario_puede_invergesal(user):
    """
    Acceso a Invergesal (no depende de empresa activa).
    - superuser o perfil.rol == 'admin'
    - o perfil.puede_invergesal (flag que agrega Conta en PerfilUsuario)
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = getattr(user, 'perfil', None)
    if perfil is None:
        return False
    if getattr(perfil, 'rol', None) == 'admin':
        return True
    return bool(getattr(perfil, 'puede_invergesal', False))


def usuario_solo_invergesal(user):
    """
    Cliente autorizado a Invergesal y sin permisos de RRHH/contabilidad.
    Al entrar va directo a /invergesal y no ve el resto del ERP.
    Admin y superuser nunca entran en este modo.
    """
    if not usuario_puede_invergesal(user):
        return False
    if user.is_superuser:
        return False
    perfil = getattr(user, 'perfil', None)
    if perfil is None or getattr(perfil, 'rol', None) != 'cliente':
        return False
    from core.models import PermisoAccesoUsuario
    return not PermisoAccesoUsuario.objects.filter(user=user, permitido=True).exists()


def invergesal_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not usuario_puede_invergesal(request.user):
            messages.error(request, 'No tienes acceso a Invergesal. Contacta al administrador.')
            return redirect('core:home')
        return view_func(request, *args, **kwargs)

    return wrapped
