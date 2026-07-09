"""Sugerencia inteligente de cuenta gasto/existencia por proveedor."""

from .models import CuentaContable, EmpresaProveedor, ProveedorCuentaStats

CODIGOS_EXCLUIDOS = {'1.01.05', '2.01.01', '2.01.03', '2.01.04'}


def cuentas_gasto_qs(empresa):
    return CuentaContable.objects.filter(
        empresa=empresa,
        tipo__in=('perdida', 'activo'),
    ).exclude(codigo__in=CODIGOS_EXCLUIDOS).order_by('codigo')


def _es_cuenta_valida(cuenta):
    if not cuenta:
        return False
    if cuenta.codigo in CODIGOS_EXCLUIDOS:
        return False
    return cuenta.tipo in ('perdida', 'activo')


def sugerir_cuenta_gasto(empresa, proveedor):
    """
    Retorna (cuenta, fuente, detalle) o (None, '', '').
    Prioridad: habitual empresa → stats empresa → stats global.
    """
    vinculo = EmpresaProveedor.objects.filter(
        empresa=empresa, proveedor=proveedor,
    ).select_related('cuenta_gasto_habitual').first()

    if vinculo and _es_cuenta_valida(vinculo.cuenta_gasto_habitual):
        c = vinculo.cuenta_gasto_habitual
        return c, 'habitual', f'Usada habitualmente en esta empresa ({vinculo.veces_contabilizado} veces)'

    stat_emp = ProveedorCuentaStats.objects.filter(
        proveedor=proveedor, empresa=empresa, cuenta__tipo__in=('perdida', 'activo'),
    ).exclude(cuenta__codigo__in=CODIGOS_EXCLUIDOS).select_related('cuenta').order_by('-contador').first()

    if stat_emp:
        return stat_emp.cuenta, 'empresa', f'Usada {stat_emp.contador} veces en esta empresa'

    stat_global = ProveedorCuentaStats.objects.filter(
        proveedor=proveedor, empresa__isnull=True, cuenta__tipo__in=('perdida', 'activo'),
    ).exclude(cuenta__codigo__in=CODIGOS_EXCLUIDOS).select_related('cuenta').order_by('-contador').first()

    if stat_global:
        return stat_global.cuenta, 'estudio', f'Sugerencia del estudio ({stat_global.contador} usos en otros clientes)'

    return None, '', ''


def registrar_uso_cuenta(empresa, proveedor, cuenta, fecha_compra):
    """Actualiza vínculo empresa-proveedor y estadísticas tras contabilizar."""
    vinculo, _ = EmpresaProveedor.objects.get_or_create(empresa=empresa, proveedor=proveedor)
    vinculo.cuenta_gasto_habitual = cuenta
    vinculo.veces_contabilizado += 1
    if not vinculo.primera_compra or fecha_compra < vinculo.primera_compra:
        vinculo.primera_compra = fecha_compra
    if not vinculo.ultima_compra or fecha_compra > vinculo.ultima_compra:
        vinculo.ultima_compra = fecha_compra
    vinculo.save()

    for emp_scope in (empresa, None):
        stat, created = ProveedorCuentaStats.objects.get_or_create(
            proveedor=proveedor, cuenta=cuenta, empresa=emp_scope,
            defaults={'contador': 0},
        )
        stat.contador += 1
        stat.save(update_fields=['contador'])
