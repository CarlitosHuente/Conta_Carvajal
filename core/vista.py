"""Simulación de vista cliente para administradores."""

SESSION_VISTA_CLIENTE = 'vista_cliente'


def es_admin_real(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return hasattr(user, 'perfil') and user.perfil.rol == 'admin'


def vista_cliente_activa(request):
    if not es_admin_real(request.user):
        return False
    return bool(request.session.get(SESSION_VISTA_CLIENTE)) and bool(request.session.get('empresa_activa_id'))


def vista_es_admin_ui(request):
    return es_admin_real(request.user) and not vista_cliente_activa(request)


def usuario_para_permisos(request):
    if vista_cliente_activa(request):
        from .models import PerfilUsuario

        empresa_id = request.session.get('empresa_activa_id')
        perfil = PerfilUsuario.objects.filter(
            rol='cliente', empresa_id=empresa_id,
        ).select_related('user').first()
        if perfil:
            return perfil.user
    return request.user


def limpiar_vista_cliente(session):
    session.pop(SESSION_VISTA_CLIENTE, None)
