"""Registro de pagos a proveedores y cobros a clientes."""

from django.db import transaction

from .libros import config_saldar_cuenta
from .models import AsientoContable, LineaAsiento, AplicacionCobroPago, CuentaContable


class SaldarMovimientosError(Exception):
    pass


@transaction.atomic
def registrar_pago_o_cobro(empresa, cuenta_operacion, lineas_origen, medios, fecha, glosa=None, tipo=None):
    """
    cuenta_operacion: cuenta del mayor a saldar
    lineas_origen: LineaAsiento pendientes seleccionadas
    medios: [{'cuenta_id': id, 'monto': int}, ...] — puede ser Caja + Banco u otras
    """
    config = config_saldar_cuenta(cuenta_operacion)
    if not config:
        raise SaldarMovimientosError('Esta cuenta no admite cobros/pagos rápidos.')

    tipo = tipo or config['tipo']

    if not lineas_origen:
        raise SaldarMovimientosError('Selecciona al menos un movimiento pendiente.')

    if not medios:
        raise SaldarMovimientosError('Agrega al menos un medio de pago o cobro.')

    monto_total = 0
    for linea in lineas_origen:
        if linea.cuenta_id != cuenta_operacion.id:
            raise SaldarMovimientosError('Movimiento de otra cuenta.')
        if linea.monto_pendiente <= 0:
            raise SaldarMovimientosError(f'El movimiento #{linea.id} ya está saldado.')
        monto_total += linea.monto_pendiente

    if monto_total <= 0:
        raise SaldarMovimientosError('El monto total debe ser mayor a cero.')

    lineas_medio = []
    monto_medios = 0
    for medio in medios:
        monto = int(medio.get('monto') or 0)
        if monto <= 0:
            continue
        cuenta_medio = CuentaContable.objects.get(pk=medio['cuenta_id'], empresa=empresa)
        lineas_medio.append({'cuenta': cuenta_medio, 'monto': monto})
        monto_medios += monto

    if not lineas_medio:
        raise SaldarMovimientosError('Indica montos mayores a cero en los medios de pago/cobro.')

    if monto_medios != monto_total:
        raise SaldarMovimientosError(
            f'Los medios (${monto_medios:,}) deben sumar el total seleccionado (${monto_total:,}).'
        )

    if tipo == 'pago':
        glosa_def = glosa or f'Pago {cuenta_operacion.nombre}'
        linea_operacion = {'debe': monto_total, 'haber': 0}
        lado_medio = 'haber'
    else:
        glosa_def = glosa or f'Cobro {cuenta_operacion.nombre}'
        linea_operacion = {'debe': 0, 'haber': monto_total}
        lado_medio = 'debe'

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha,
        glosa=glosa_def,
        tipo_asiento=tipo,
    )

    LineaAsiento.objects.create(
        asiento=asiento,
        cuenta=cuenta_operacion,
        debe=linea_operacion['debe'],
        haber=linea_operacion['haber'],
    )

    for lm in lineas_medio:
        if lado_medio == 'haber':
            LineaAsiento.objects.create(
                asiento=asiento,
                cuenta=lm['cuenta'],
                debe=0,
                haber=lm['monto'],
            )
        else:
            LineaAsiento.objects.create(
                asiento=asiento,
                cuenta=lm['cuenta'],
                debe=lm['monto'],
                haber=0,
            )

    for linea in lineas_origen:
        AplicacionCobroPago.objects.create(
            asiento_pago=asiento,
            linea_origen=linea,
            monto=linea.monto_pendiente,
            tipo=tipo,
        )

    return asiento, monto_total, tipo


@transaction.atomic
def crear_asiento_manual(empresa, fecha, glosa, lineas_data):
    """lineas_data: list of dict cuenta_id, debe, haber"""
    if not lineas_data:
        raise SaldarMovimientosError('Agrega al menos una línea al comprobante.')

    total_debe = sum(int(l.get('debe') or 0) for l in lineas_data)
    total_haber = sum(int(l.get('haber') or 0) for l in lineas_data)

    if total_debe != total_haber:
        raise SaldarMovimientosError(
            f'El comprobante no cuadra: Debe ${total_debe:,} | Haber ${total_haber:,}'
        )
    if total_debe == 0:
        raise SaldarMovimientosError('El comprobante no puede estar en cero.')

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha,
        glosa=glosa,
        tipo_asiento='manual',
    )

    for linea in lineas_data:
        cuenta = CuentaContable.objects.get(pk=linea['cuenta_id'], empresa=empresa)
        debe = int(linea.get('debe') or 0)
        haber = int(linea.get('haber') or 0)
        if debe == 0 and haber == 0:
            continue
        LineaAsiento.objects.create(asiento=asiento, cuenta=cuenta, debe=debe, haber=haber)

    return asiento
