"""Utilidades para leer montos desde ítems de liquidación."""


def item_monto(items, prefijos):
    for item in items:
        nombre = (item.nombre or '').upper()
        for prefijo in prefijos:
            if nombre.startswith(prefijo.upper()):
                return item.monto
    return 0


def descuentos_trabajador_por_institucion(items):
    """Desglosa descuentos legales del trabajador según institución de pago."""
    descuentos = [i for i in items if i.tipo == 'DESCUENTO']
    previred = (
        item_monto(descuentos, ['AFP '])
        + item_monto(descuentos, ['Salud '])
        + item_monto(descuentos, ['Seguro de Cesantía'])
    )
    impuesto_unico = item_monto(descuentos, ['Impuesto Único'])
    return previred, impuesto_unico
