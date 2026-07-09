"""Registro de pagos a proveedores y cobros a clientes."""

from collections import defaultdict

from django.db import transaction

from .auxiliares import aux_desde_linea, crear_linea_asiento
from .libros import config_saldar_cuenta
from .models import AsientoContable, AplicacionCobroPago, CuentaContable


class SaldarMovimientosError(Exception):
    pass


def _items_origen(lineas_origen, cuenta_operacion):
    items = []
    for linea in lineas_origen:
        if linea.cuenta_id != cuenta_operacion.id:
            raise SaldarMovimientosError('Movimiento de otra cuenta.')
        if linea.monto_pendiente <= 0:
            raise SaldarMovimientosError(f'El movimiento #{linea.id} ya está saldado.')
        items.append({
            'linea': linea,
            'monto': linea.monto_pendiente,
            'aux': aux_desde_linea(linea),
        })
    return items


def _agrupar_montos_por_rut(items_origen):
    grupos = defaultdict(int)
    for item in items_origen:
        rut = (item['aux'].get('auxiliar_rut') or '').strip()
        grupos[rut] += item['monto']
    return dict(grupos)


def _crear_lineas_medio(asiento, items_origen, lineas_medio, tipo):
    """Haber/debe de medios: una línea por RUT cuando hay varios proveedores distintos."""
    grupos_rut = _agrupar_montos_por_rut(items_origen)
    es_pago = tipo == 'pago'

    if len(grupos_rut) <= 1:
        for lm in lineas_medio:
            if es_pago:
                crear_linea_asiento(asiento, lm['cuenta'], haber=lm['monto'])
            else:
                crear_linea_asiento(asiento, lm['cuenta'], debe=lm['monto'])
        return

    cuenta_default = lineas_medio[0]['cuenta']
    if len(lineas_medio) == 1:
        for rut in sorted(grupos_rut.keys()):
            aux = {'auxiliar_rut': rut, 'auxiliar_doc': '', 'centro_costo': ''}
            if es_pago:
                crear_linea_asiento(asiento, cuenta_default, haber=grupos_rut[rut], aux=aux)
            else:
                crear_linea_asiento(asiento, cuenta_default, debe=grupos_rut[rut], aux=aux)
        return

    total_op = sum(grupos_rut.values())
    rut_items = sorted(grupos_rut.items())
    for lm in lineas_medio:
        resto = lm['monto']
        for idx, (rut, rut_total) in enumerate(rut_items):
            if idx == len(rut_items) - 1:
                parte = resto
            else:
                parte = int(round(lm['monto'] * rut_total / total_op))
                resto -= parte
            if parte <= 0:
                continue
            aux = {'auxiliar_rut': rut, 'auxiliar_doc': '', 'centro_costo': ''}
            if es_pago:
                crear_linea_asiento(asiento, lm['cuenta'], haber=parte, aux=aux)
            else:
                crear_linea_asiento(asiento, lm['cuenta'], debe=parte, aux=aux)


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

    items = _items_origen(lineas_origen, cuenta_operacion)
    monto_total = sum(i['monto'] for i in items)

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
    else:
        glosa_def = glosa or f'Cobro {cuenta_operacion.nombre}'

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha,
        glosa=glosa_def,
        tipo_asiento=tipo,
    )

    for item in items:
        if tipo == 'pago':
            crear_linea_asiento(
                asiento, cuenta_operacion, debe=item['monto'], haber=0, aux=item['aux'],
            )
        else:
            crear_linea_asiento(
                asiento, cuenta_operacion, debe=0, haber=item['monto'], aux=item['aux'],
            )

    _crear_lineas_medio(asiento, items, lineas_medio, tipo)

    for item in items:
        AplicacionCobroPago.objects.create(
            asiento_pago=asiento,
            linea_origen=item['linea'],
            monto=item['monto'],
            tipo=tipo,
        )

    return asiento, monto_total, tipo


@transaction.atomic
def crear_asiento_manual(empresa, fecha, glosa, lineas_data):
    """lineas_data: list of dict cuenta_id, debe, haber, auxiliar_rut, auxiliar_doc, centro_costo"""
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
        aux = {
            'auxiliar_rut': linea.get('auxiliar_rut', ''),
            'auxiliar_doc': linea.get('auxiliar_doc', ''),
            'centro_costo': linea.get('centro_costo', ''),
        }
        crear_linea_asiento(asiento, cuenta, debe=debe, haber=haber, aux=aux)

    return asiento
