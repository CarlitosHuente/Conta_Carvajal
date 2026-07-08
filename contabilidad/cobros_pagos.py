"""Registro de pagos a proveedores y cobros a clientes."""

from django.db import transaction

from .models import AsientoContable, LineaAsiento, AplicacionCobroPago, CuentaContable


class SaldarMovimientosError(Exception):
    pass


@transaction.atomic
def registrar_pago_o_cobro(empresa, cuenta_operacion, lineas_origen, cuenta_medio_id, fecha, glosa=None):
    """
    cuenta_operacion: clientes o proveedores
    lineas_origen: LineaAsiento pendientes seleccionadas
    cuenta_medio_id: caja o banco
    """
    subtipo = cuenta_operacion.subtipo_detectado()
    if subtipo not in ('clientes', 'proveedores'):
        raise SaldarMovimientosError('Esta cuenta no admite cobros/pagos rápidos.')

    if not lineas_origen:
        raise SaldarMovimientosError('Selecciona al menos un movimiento pendiente.')

    cuenta_medio = CuentaContable.objects.get(pk=cuenta_medio_id, empresa=empresa)
    if cuenta_medio.subtipo_detectado() not in ('caja', 'banco'):
        raise SaldarMovimientosError('La contrapartida debe ser Caja o Banco.')

    monto_total = 0
    for linea in lineas_origen:
        if linea.cuenta_id != cuenta_operacion.id:
            raise SaldarMovimientosError('Movimiento de otra cuenta.')
        if linea.monto_pendiente <= 0:
            raise SaldarMovimientosError(f'El movimiento #{linea.id} ya está saldado.')
        monto_total += linea.monto_pendiente

    if monto_total <= 0:
        raise SaldarMovimientosError('El monto total debe ser mayor a cero.')

    if subtipo == 'proveedores':
        tipo = 'pago'
        glosa_def = glosa or f'Pago {cuenta_operacion.nombre}'
        linea_operacion = {'debe': monto_total, 'haber': 0}
        linea_medio = {'debe': 0, 'haber': monto_total}
    else:
        tipo = 'cobro'
        glosa_def = glosa or f'Cobro {cuenta_operacion.nombre}'
        linea_operacion = {'debe': 0, 'haber': monto_total}
        linea_medio = {'debe': monto_total, 'haber': 0}

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha,
        glosa=glosa_def,
        tipo_asiento=tipo,
    )

    linea_contra = LineaAsiento.objects.create(
        asiento=asiento,
        cuenta=cuenta_operacion,
        debe=linea_operacion['debe'],
        haber=linea_operacion['haber'],
    )
    LineaAsiento.objects.create(
        asiento=asiento,
        cuenta=cuenta_medio,
        debe=linea_medio['debe'],
        haber=linea_medio['haber'],
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
