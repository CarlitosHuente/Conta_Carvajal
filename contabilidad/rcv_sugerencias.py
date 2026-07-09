"""Sugerencia inteligente de cuenta gasto/existencia por proveedor."""

from django.db.models import Count, Max, Min

from .models import (
    CuentaContable, DocumentoCompraRCV, EmpresaProveedor, ProveedorCuentaStats,
)

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


def _docs_contabilizados_qs(*, empresa=None, proveedor=None, excluir_empresa=None):
    """Solo compras con asiento vigente en el libro diario."""
    qs = DocumentoCompraRCV.objects.filter(
        estado='contabilizada',
        asiento__isnull=False,
        cuenta_gasto__isnull=False,
    ).exclude(
        cuenta_gasto__codigo__in=CODIGOS_EXCLUIDOS,
    ).filter(
        cuenta_gasto__tipo__in=('perdida', 'activo'),
    )
    if empresa is not None:
        qs = qs.filter(empresa=empresa)
    if proveedor is not None:
        qs = qs.filter(proveedor=proveedor)
    if excluir_empresa is not None:
        qs = qs.exclude(empresa=excluir_empresa)
    return qs


def _mejor_cuenta_por_uso(qs):
    row = (
        qs.values('cuenta_gasto')
        .annotate(n=Count('id'))
        .order_by('-n', 'cuenta_gasto')
        .first()
    )
    if not row:
        return None, 0
    cuenta = CuentaContable.objects.filter(pk=row['cuenta_gasto']).first()
    return cuenta, row['n']


def sugerir_cuenta_gasto(empresa, proveedor):
    """
    Retorna (cuenta, fuente, detalle) o (None, '', '').
    Prioridad: habitual empresa → uso en empresa → uso en otras empresas del estudio.
    Basado solo en documentos RCV aún contabilizados (con asiento).
    """
    docs_emp = _docs_contabilizados_qs(empresa=empresa, proveedor=proveedor)
    cuenta, n = _mejor_cuenta_por_uso(docs_emp)
    if cuenta and _es_cuenta_valida(cuenta):
        vinculo = EmpresaProveedor.objects.filter(
            empresa=empresa, proveedor=proveedor,
        ).select_related('cuenta_gasto_habitual').first()
        if vinculo and vinculo.cuenta_gasto_habitual_id == cuenta.id:
            return cuenta, 'habitual', f'Usada habitualmente en esta empresa ({n} veces)'
        return cuenta, 'empresa', f'Usada {n} veces en esta empresa'

    docs_otras = _docs_contabilizados_qs(proveedor=proveedor, excluir_empresa=empresa)
    cuenta, n = _mejor_cuenta_por_uso(docs_otras)
    if cuenta and _es_cuenta_valida(cuenta):
        return cuenta, 'estudio', f'Sugerencia del estudio ({n} usos en otros clientes)'

    return None, '', ''


def registrar_uso_cuenta(empresa, proveedor, cuenta, fecha_compra):
    """Actualiza caché de inteligencia tras contabilizar (se resincroniza al revertir)."""
    vinculo, _ = EmpresaProveedor.objects.get_or_create(empresa=empresa, proveedor=proveedor)
    vinculo.cuenta_gasto_habitual = cuenta
    vinculo.veces_contabilizado += 1
    if not vinculo.primera_compra or fecha_compra < vinculo.primera_compra:
        vinculo.primera_compra = fecha_compra
    if not vinculo.ultima_compra or fecha_compra > vinculo.ultima_compra:
        vinculo.ultima_compra = fecha_compra
    vinculo.save()

    for emp_scope in (empresa, None):
        stat, _ = ProveedorCuentaStats.objects.get_or_create(
            proveedor=proveedor, cuenta=cuenta, empresa=emp_scope,
            defaults={'contador': 0},
        )
        stat.contador += 1
        stat.save(update_fields=['contador'])


def sincronizar_inteligencia_proveedores(*, empresa_id=None):
    """
    Reconstruye estadísticas desde documentos RCV realmente contabilizados.
    Corrige caché obsoleta si se eliminaron asientos fuera del flujo RCV.
    """
    base = DocumentoCompraRCV.objects.filter(
        estado='contabilizada',
        asiento__isnull=False,
        cuenta_gasto__isnull=False,
    )
    if empresa_id:
        base = base.filter(empresa_id=empresa_id)

    if empresa_id:
        ProveedorCuentaStats.objects.filter(empresa_id=empresa_id).delete()
        por_empresa = base.filter(empresa_id=empresa_id).values(
            'proveedor_id', 'cuenta_gasto_id',
        ).annotate(n=Count('id'))
        for row in por_empresa:
            ProveedorCuentaStats.objects.create(
                proveedor_id=row['proveedor_id'],
                cuenta_id=row['cuenta_gasto_id'],
                empresa_id=empresa_id,
                contador=row['n'],
            )

        proveedor_ids = base.filter(empresa_id=empresa_id).values_list(
            'proveedor_id', flat=True,
        ).distinct()
        for prov_id in proveedor_ids:
            docs = base.filter(empresa_id=empresa_id, proveedor_id=prov_id)
            resumen = docs.aggregate(
                total=Count('id'),
                primera=Min('fecha_docto'),
                ultima=Max('fecha_docto'),
            )
            top = (
                docs.values('cuenta_gasto_id')
                .annotate(n=Count('id'))
                .order_by('-n', 'cuenta_gasto_id')
                .first()
            )
            EmpresaProveedor.objects.update_or_create(
                empresa_id=empresa_id,
                proveedor_id=prov_id,
                defaults={
                    'veces_contabilizado': resumen['total'] or 0,
                    'primera_compra': resumen['primera'],
                    'ultima_compra': resumen['ultima'],
                    'cuenta_gasto_habitual_id': top['cuenta_gasto_id'] if top else None,
                },
            )

        EmpresaProveedor.objects.filter(empresa_id=empresa_id).exclude(
            proveedor_id__in=proveedor_ids,
        ).update(
            veces_contabilizado=0,
            cuenta_gasto_habitual=None,
        )

    ProveedorCuentaStats.objects.filter(empresa__isnull=True).delete()
    por_global = base.values('proveedor_id', 'cuenta_gasto_id').annotate(n=Count('id'))
    for row in por_global:
        ProveedorCuentaStats.objects.create(
            proveedor_id=row['proveedor_id'],
            cuenta_id=row['cuenta_gasto_id'],
            empresa=None,
            contador=row['n'],
        )
