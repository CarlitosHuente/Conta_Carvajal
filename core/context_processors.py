from django.conf import settings

from .models import Empresa, PermisoAccesoUsuario
from .vista import usuario_para_permisos, vista_cliente_activa, vista_es_admin_ui


def _has_access(user, empresa_id, modulo, submodulo='', accion='ver', admin_bypass=False):
    if not user.is_authenticated:
        return False
    if admin_bypass:
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
    admin_bypass = vista_es_admin_ui(request)
    user_perm = usuario_para_permisos(request)

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
                'rrhh_trabajadores_ver': _has_access(user_perm, empresa_activa_id, 'rrhh', 'trabajadores', 'ver', admin_bypass),
                'rrhh_novedades_editar': _has_access(user_perm, empresa_activa_id, 'rrhh', 'novedades', 'editar', admin_bypass),
                'rrhh_liquidaciones_crear': _has_access(user_perm, empresa_activa_id, 'rrhh', 'liquidaciones', 'crear', admin_bypass),
                'rrhh_liquidaciones_ver': _has_access(user_perm, empresa_activa_id, 'rrhh', 'liquidaciones', 'ver', admin_bypass),
                'contabilidad_f29_ver': _has_access(user_perm, empresa_activa_id, 'contabilidad', 'f29', 'ver', admin_bypass),
                'contabilidad_f29_crear': _has_access(user_perm, empresa_activa_id, 'contabilidad', 'f29', 'crear', admin_bypass),
                'contabilidad_libro_diario_ver': _has_access(user_perm, empresa_activa_id, 'contabilidad', 'libro_diario', 'ver', admin_bypass),
                'contabilidad_plan_cuentas_ver': _has_access(user_perm, empresa_activa_id, 'contabilidad', 'plan_cuentas', 'ver', admin_bypass),
                'contabilidad_plantillas_ver': _has_access(user_perm, empresa_activa_id, 'contabilidad', 'plantillas', 'ver', admin_bypass),
            })
            permisos_ui['rrhh_menu_visible'] = any([
                permisos_ui['rrhh_trabajadores_ver'],
                permisos_ui['rrhh_novedades_editar'],
                permisos_ui['rrhh_liquidaciones_crear'],
                permisos_ui['rrhh_liquidaciones_ver'],
            ])
            permisos_ui['contabilidad_menu_visible'] = any([
                permisos_ui['contabilidad_f29_ver'],
                permisos_ui['contabilidad_f29_crear'],
                permisos_ui['contabilidad_libro_diario_ver'],
                permisos_ui['contabilidad_plan_cuentas_ver'],
                permisos_ui['contabilidad_plantillas_ver'],
            ])
        except Empresa.DoesNotExist:
            request.session.pop('empresa_activa_id', None)

    return {
        'empresa_activa': empresa_activa,
        'permisos_ui': permisos_ui,
        'vista_cliente_activa': vista_cliente_activa(request),
        'vista_es_admin': admin_bypass,
    }


def ui_theme(request):
    """Expone flags del tema glass para base.html (reversible vía settings)."""
    enabled = getattr(settings, 'UI_GLASS_ENABLED', False)
    blur = getattr(settings, 'UI_GLASS_BLUR', 10)
    return {
        'ui_glass_enabled': enabled,
        'ui_glass_blur': blur,
        'ui_glass_lite': enabled and blur == 0,
    }
