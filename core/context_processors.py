from .models import Empresa, PermisoAccesoUsuario


def _has_access(user, empresa_id, modulo, submodulo='', accion='ver'):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if hasattr(user, 'perfil') and user.perfil.rol == 'admin':
        return True

    qs = PermisoAccesoUsuario.objects.filter(
        user=user,
        empresa_id=empresa_id,
        modulo=modulo,
        accion=accion,
        permitido=True
    )
    return qs.filter(submodulo=submodulo).exists() or qs.filter(submodulo='').exists()

def empresa_context(request):
    """
    Hace que la empresa activa en sesión esté disponible en todas las plantillas.
    El objeto estará disponible como `empresa_activa`.
    """
    empresa_activa = None
    empresa_activa_id = request.session.get('empresa_activa_id')

    permisos_ui = {
        'rrhh_trabajadores_ver': False,
        'rrhh_novedades_editar': False,
        'rrhh_liquidaciones_crear': False,
        'rrhh_liquidaciones_ver': False,
        'contabilidad_f29_ver': False,
        'contabilidad_f29_crear': False,
        'contabilidad_libro_diario_ver': False,
        'contabilidad_plan_cuentas_ver': False,
        'contabilidad_plantillas_ver': False,
        'rrhh_menu_visible': False,
        'contabilidad_menu_visible': False,
    }

    if empresa_activa_id:
        try:
            empresa_activa = Empresa.objects.get(id=empresa_activa_id)
            permisos_ui.update({
                'rrhh_trabajadores_ver': _has_access(request.user, empresa_activa_id, 'rrhh', 'trabajadores', 'ver'),
                'rrhh_novedades_editar': _has_access(request.user, empresa_activa_id, 'rrhh', 'novedades', 'editar'),
                'rrhh_liquidaciones_crear': _has_access(request.user, empresa_activa_id, 'rrhh', 'liquidaciones', 'crear'),
                'rrhh_liquidaciones_ver': _has_access(request.user, empresa_activa_id, 'rrhh', 'liquidaciones', 'ver'),
                'contabilidad_f29_ver': _has_access(request.user, empresa_activa_id, 'contabilidad', 'f29', 'ver'),
                'contabilidad_f29_crear': _has_access(request.user, empresa_activa_id, 'contabilidad', 'f29', 'crear'),
                'contabilidad_libro_diario_ver': _has_access(request.user, empresa_activa_id, 'contabilidad', 'libro_diario', 'ver'),
                'contabilidad_plan_cuentas_ver': _has_access(request.user, empresa_activa_id, 'contabilidad', 'plan_cuentas', 'ver'),
                'contabilidad_plantillas_ver': _has_access(request.user, empresa_activa_id, 'contabilidad', 'plantillas', 'ver'),
            })
            permisos_ui['rrhh_menu_visible'] = any([
                permisos_ui['rrhh_trabajadores_ver'],
                permisos_ui['rrhh_novedades_editar'],
                permisos_ui['rrhh_liquidaciones_crear'],
                permisos_ui['rrhh_liquidaciones_ver'],
            ]) or (hasattr(request.user, 'perfil') and request.user.perfil.rol == 'admin') or request.user.is_superuser

            permisos_ui['contabilidad_menu_visible'] = any([
                permisos_ui['contabilidad_f29_ver'],
                permisos_ui['contabilidad_f29_crear'],
                permisos_ui['contabilidad_libro_diario_ver'],
                permisos_ui['contabilidad_plan_cuentas_ver'],
                permisos_ui['contabilidad_plantillas_ver'],
            ])
        except Empresa.DoesNotExist:
            request.session.pop('empresa_activa_id', None)
            
    return {'empresa_activa': empresa_activa, 'permisos_ui': permisos_ui}