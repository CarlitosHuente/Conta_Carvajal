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


def sugerir_cuentas_para_proveedores(empresa, proveedor_ids):
    """Sugerencias en lote (1–2 consultas en vez de N por fila RCV)."""
    proveedor_ids = list({int(p) for p in proveedor_ids if p})
    if not proveedor_ids:
        return {}

    rows_emp = (
        _docs_contabilizados_qs(empresa=empresa)
        .filter(proveedor_id__in=proveedor_ids)
        .values('proveedor_id', 'cuenta_gasto')
        .annotate(n=Count('id'))
        .order_by('proveedor_id', '-n', 'cuenta_gasto')
    )
    best_emp = {}
    for row in rows_emp:
        pid = row['proveedor_id']
        if pid not in best_emp:
            best_emp[pid] = (row['cuenta_gasto'], row['n'])

    faltantes = [p for p in proveedor_ids if p not in best_emp]
    best_global = {}
    if faltantes:
        rows_g = (
            _docs_contabilizados_qs()
            .filter(proveedor_id__in=faltantes)
            .exclude(empresa=empresa)
            .values('proveedor_id', 'cuenta_gasto')
            .annotate(n=Count('id'))
            .order_by('proveedor_id', '-n', 'cuenta_gasto')
        )
        for row in rows_g:
            pid = row['proveedor_id']
            if pid not in best_global:
                best_global[pid] = (row['cuenta_gasto'], row['n'])

    cuenta_ids = {cid for cid, _ in best_emp.values()} | {cid for cid, _ in best_global.values()}
    cuentas = {c.id: c for c in CuentaContable.objects.filter(pk__in=cuenta_ids)}

    vinculos = {
        v.proveedor_id: v
        for v in EmpresaProveedor.objects.filter(
            empresa=empresa, proveedor_id__in=proveedor_ids,
        ).select_related('cuenta_gasto_habitual')
    }

    resultado = {}
    for pid in proveedor_ids:
        if pid in best_emp:
            cid, n = best_emp[pid]
            cuenta = cuentas.get(cid)
            if cuenta and _es_cuenta_valida(cuenta):
                v = vinculos.get(pid)
                if v and v.cuenta_gasto_habitual_id == cid:
                    resultado[pid] = (cuenta, 'habitual', f'Usada habitualmente en esta empresa ({n} veces)')
                else:
                    resultado[pid] = (cuenta, 'empresa', f'Usada {n} veces en esta empresa')
                continue
        if pid in best_global:
            cid, n = best_global[pid]
            cuenta = cuentas.get(cid)
            if cuenta and _es_cuenta_valida(cuenta):
                resultado[pid] = (cuenta, 'estudio', f'Sugerencia del estudio ({n} usos en otros clientes)')
                continue
        resultado[pid] = (None, '', '')
    return resultado


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


def sincronizar_inteligencia_proveedores(*, empresa_id=None, incluir_global=True):
    """
    Reconstruye estadísticas desde documentos RCV realmente contabilizados.
    Solo se invoca al revertir/eliminar lotes o borrar asientos (no en cada vista).
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
        por_empresa = list(
            base.filter(empresa_id=empresa_id)
            .values('proveedor_id', 'cuenta_gasto_id')
            .annotate(n=Count('id'))
        )
        if por_empresa:
            ProveedorCuentaStats.objects.bulk_create([
                ProveedorCuentaStats(
                    proveedor_id=row['proveedor_id'],
                    cuenta_id=row['cuenta_gasto_id'],
                    empresa_id=empresa_id,
                    contador=row['n'],
                )
                for row in por_empresa
            ])

        aggs = list(
            base.filter(empresa_id=empresa_id)
            .values('proveedor_id')
            .annotate(total=Count('id'), primera=Min('fecha_docto'), ultima=Max('fecha_docto'))
        )
        top_rows = (
            base.filter(empresa_id=empresa_id)
            .values('proveedor_id', 'cuenta_gasto_id')
            .annotate(n=Count('id'))
        )
        top_by_prov = {}
        for row in top_rows:
            pid = row['proveedor_id']
            prev = top_by_prov.get(pid)
            if not prev or row['n'] > prev[1]:
                top_by_prov[pid] = (row['cuenta_gasto_id'], row['n'])

        proveedor_ids = [a['proveedor_id'] for a in aggs]
        for resumen in aggs:
            prov_id = resumen['proveedor_id']
            top = top_by_prov.get(prov_id)
            EmpresaProveedor.objects.update_or_create(
                empresa_id=empresa_id,
                proveedor_id=prov_id,
                defaults={
                    'veces_contabilizado': resumen['total'] or 0,
                    'primera_compra': resumen['primera'],
                    'ultima_compra': resumen['ultima'],
                    'cuenta_gasto_habitual_id': top[0] if top else None,
                },
            )

        EmpresaProveedor.objects.filter(empresa_id=empresa_id).exclude(
            proveedor_id__in=proveedor_ids,
        ).update(veces_contabilizado=0, cuenta_gasto_habitual=None)

    if not incluir_global:
        return

    ProveedorCuentaStats.objects.filter(empresa__isnull=True).delete()
    por_global = list(base.values('proveedor_id', 'cuenta_gasto_id').annotate(n=Count('id')))
    if por_global:
        ProveedorCuentaStats.objects.bulk_create([
            ProveedorCuentaStats(
                proveedor_id=row['proveedor_id'],
                cuenta_id=row['cuenta_gasto_id'],
                empresa=None,
                contador=row['n'],
            )
            for row in por_global
        ])
