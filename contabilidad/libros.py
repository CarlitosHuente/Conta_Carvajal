"""Cálculos de Libro Mayor y Balance."""

from django.db.models import Sum, Q
from .auxiliares import aux_desde_linea, etiqueta_auxiliar
from .models import CuentaContable, LineaAsiento, CuentaAccionRapida


def _filtro_hasta(fecha_corte):
    if fecha_corte:
        return Q(asiento__fecha__lte=fecha_corte)
    return Q()


def config_saldar_cuenta(cuenta, accion=None):
    """Cuenta con al menos una acción rápida asignada."""
    if accion is None:
        asignacion = (
            CuentaAccionRapida.objects.filter(cuenta=cuenta, accion__activa=True)
            .select_related('accion')
            .order_by('orden', 'id')
            .first()
        )
        if not asignacion:
            return None
        accion = asignacion.accion
    elif not CuentaAccionRapida.objects.filter(cuenta=cuenta, accion=accion, accion__activa=True).exists():
        return None

    return {
        'tipo': accion.tipo,
        'lado_pendiente': accion.lado_pendiente,
        'accion': accion,
    }


def saldo_cuenta_natural(cuenta, total_debe, total_haber):
    if cuenta.tipo in ('activo', 'perdida'):
        return total_debe - total_haber
    return total_haber - total_debe


def _clasificar_ocho_columnas(cuenta, debe, haber):
    """Columnas 1-4 comprobación; 5-8 clasificación tributaria."""
    saldo_deudor = max(0, debe - haber)
    saldo_acreedor = max(0, haber - debe)

    activos = pasivos = perdidas = ganancias = 0
    t = cuenta.tipo
    if t == 'activo':
        activos, pasivos = saldo_deudor, saldo_acreedor
    elif t in ('pasivo', 'patrimonio'):
        pasivos, activos = saldo_acreedor, saldo_deudor
    elif t == 'perdida':
        perdidas, ganancias = saldo_deudor, saldo_acreedor
    elif t == 'ganancia':
        ganancias, perdidas = saldo_acreedor, saldo_deudor

    return {
        'debe': debe,
        'haber': haber,
        'saldo_deudor': saldo_deudor,
        'saldo_acreedor': saldo_acreedor,
        'activos': activos,
        'pasivos': pasivos,
        'perdidas': perdidas,
        'ganancias': ganancias,
    }


def resumen_cuentas_empresa(empresa, fecha_corte=None):
    cuentas = CuentaContable.objects.filter(empresa=empresa).prefetch_related(
        'asignaciones_acciones__accion',
    )
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
        resumen.append({
            'cuenta': cuenta,
            'debe': debe,
            'haber': haber,
            'saldo': saldo,
            'puede_saldar': cuenta.permite_saldar_operaciones(),
        })

    return sorted(resumen, key=lambda x: x['cuenta'].codigo)


def movimientos_cuenta(cuenta, fecha_corte=None, accion=None):
    filtro = _filtro_hasta(fecha_corte)
    config = config_saldar_cuenta(cuenta, accion)
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
            'auxiliar': aux_desde_linea(linea),
            'auxiliar_label': etiqueta_auxiliar(linea),
        })

    return movimientos, saldo_acum


def balance_ocho_columnas(empresa, fecha_corte=None):
    cuentas = CuentaContable.objects.filter(empresa=empresa)
    filtro = _filtro_hasta(fecha_corte)
    resultado = []
    totales = {
        'debe': 0, 'haber': 0,
        'saldo_deudor': 0, 'saldo_acreedor': 0,
        'activos': 0, 'pasivos': 0, 'perdidas': 0, 'ganancias': 0,
    }

    for cuenta in cuentas:
        agregados = LineaAsiento.objects.filter(cuenta=cuenta).filter(filtro).aggregate(
            debe=Sum('debe'),
            haber=Sum('haber'),
        )
        debe = agregados['debe'] or 0
        haber = agregados['haber'] or 0
        if debe == 0 and haber == 0:
            continue

        cols = _clasificar_ocho_columnas(cuenta, debe, haber)
        for k in totales:
            totales[k] += cols[k]

        resultado.append({
            'cuenta': cuenta,
            **cols,
        })

    return sorted(resultado, key=lambda x: x['cuenta'].codigo), totales


def cuentas_medio_pago(empresa):
    return CuentaContable.objects.filter(
        empresa=empresa,
    ).filter(
        Q(subtipo_operacion__in=('caja', 'banco'))
        | Q(codigo__startswith='1.01.01')
        | Q(codigo__startswith='1.01.02'),
    ).order_by('codigo')


def cuentas_contrapartida_disponibles(empresa):
    return CuentaContable.objects.filter(empresa=empresa).order_by('codigo')
