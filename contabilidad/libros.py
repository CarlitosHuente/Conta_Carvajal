"""Cálculos de Libro Mayor y Balance."""

from django.db.models import Sum, Q
from .models import CuentaContable, LineaAsiento


def _filtro_hasta(fecha_corte):
    if fecha_corte:
        return Q(asiento__fecha__lte=fecha_corte)
    return Q()


def config_saldar_cuenta(cuenta):
    """Devuelve tipo (pago/cobro), lado pendiente y acción rápida si aplica."""
    subtipo = cuenta.subtipo_detectado()
    if subtipo == 'proveedores':
        return {'tipo': 'pago', 'lado_pendiente': 'haber', 'accion': None}
    if subtipo == 'clientes':
        return {'tipo': 'cobro', 'lado_pendiente': 'debe', 'accion': None}
    accion = cuenta.acciones_rapidas.filter(activa=True).order_by('orden', 'id').first()
    if accion:
        return {
            'tipo': accion.tipo,
            'lado_pendiente': accion.lado_pendiente,
            'accion': accion,
        }
    return None


def saldo_cuenta_natural(cuenta, total_debe, total_haber):
    """Saldo según naturaleza de la cuenta (deudora o acreedora)."""
    if cuenta.tipo in ('activo', 'perdida'):
        return total_debe - total_haber
    return total_haber - total_debe


def resumen_cuentas_empresa(empresa, fecha_corte=None):
    cuentas = CuentaContable.objects.filter(empresa=empresa).prefetch_related('acciones_rapidas')
    filtro = _filtro_hasta(fecha_corte)
    resumen = []

    for cuenta in cuentas:
        agregados = LineaAsiento.objects.filter(cuenta=cuenta).filter(filtro).aggregate(
            debe=Sum('debe'),
            haber=Sum('haber'),
        )
        debe = agregados['debe'] or 0
        haber = agregados['haber'] or 0
        if debe == 0 and haber == 0:
            continue
        saldo = saldo_cuenta_natural(cuenta, debe, haber)
        config = config_saldar_cuenta(cuenta)
        resumen.append({
            'cuenta': cuenta,
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
            'subtipo': cuenta.subtipo_detectado(),
            'puede_saldar': bool(config),
        })

    return sorted(resumen, key=lambda x: x['cuenta'].codigo)


def movimientos_cuenta(cuenta, fecha_corte=None):
    filtro = _filtro_hasta(fecha_corte)
    config = config_saldar_cuenta(cuenta)
    lado_pendiente = config['lado_pendiente'] if config else None

    lineas = (
        LineaAsiento.objects.filter(cuenta=cuenta)
        .filter(filtro)
        .select_related('asiento', 'asiento__origen_f29', 'asiento__origen_plantilla')
        .prefetch_related('aplicaciones_salida')
        .order_by('asiento__fecha', 'asiento__id', 'id')
    )

    movimientos = []
    saldo_acum = 0
    es_deudora = cuenta.tipo in ('activo', 'perdida')

    for linea in lineas:
        if es_deudora:
            saldo_acum += linea.debe - linea.haber
        else:
            saldo_acum += linea.haber - linea.debe

        lado_operacion = None
        if lado_pendiente == 'haber' and linea.haber > 0:
            lado_operacion = 'cargo'
        elif lado_pendiente == 'debe' and linea.debe > 0:
            lado_operacion = 'cargo'

        movimientos.append({
            'linea': linea,
            'asiento': linea.asiento,
            'fecha': linea.asiento.fecha,
            'glosa': linea.asiento.glosa,
            'debe': linea.debe,
            'haber': linea.haber,
            'saldo_acumulado': saldo_acum,
            'pendiente': linea.monto_pendiente if lado_operacion else 0,
            'seleccionable': bool(lado_operacion and linea.monto_pendiente > 0),
            'lado_operacion': lado_operacion,
            'esta_saldada': linea.esta_saldada if lado_operacion else None,
        })

    return movimientos, saldo_acum


def balance_ocho_columnas(empresa, fecha_corte=None):
    filas = resumen_cuentas_empresa(empresa, fecha_corte)
    resultado = []
    totales = {'debe': 0, 'haber': 0, 'saldo_deudor': 0, 'saldo_acreedor': 0}

    for fila in filas:
        saldo = fila['saldo']
        saldo_deudor = saldo if saldo > 0 else 0
        saldo_acreedor = abs(saldo) if saldo < 0 else 0
        totales['debe'] += fila['debe']
        totales['haber'] += fila['haber']
        totales['saldo_deudor'] += saldo_deudor
        totales['saldo_acreedor'] += saldo_acreedor
        resultado.append({**fila, 'saldo_deudor': saldo_deudor, 'saldo_acreedor': saldo_acreedor})

    return resultado, totales


def cuentas_medio_pago(empresa):
    return CuentaContable.objects.filter(
        empresa=empresa,
    ).filter(
        Q(subtipo_operacion__in=('caja', 'banco'))
        | Q(codigo__startswith='1.01.01')
        | Q(codigo__startswith='1.01.02'),
    ).order_by('codigo')


def cuentas_contrapartida_disponibles(empresa):
    """Todas las cuentas que pueden usarse como medio de pago/cobro."""
    return CuentaContable.objects.filter(empresa=empresa).order_by('codigo')
