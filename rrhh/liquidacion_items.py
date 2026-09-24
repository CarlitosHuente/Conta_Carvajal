"""Utilidades para leer montos desde ítems de liquidación."""


class LineaPresentacion:
    def __init__(self, nombre, monto):
        self.nombre = nombre
        self.monto = monto


def item_monto(items, prefijos):
    for item in items:
        nombre = (item.nombre or '').upper()
        for prefijo in prefijos:
            if nombre.startswith(prefijo.upper()):
                return item.monto
    return 0


def items_monto_suma(items, prefijos):
    total = 0
    for item in items:
        nombre = (item.nombre or '').upper()
        for prefijo in prefijos:
            if nombre.startswith(prefijo.upper()):
                total += item.monto
                break
    return total


def descuentos_trabajador_por_institucion(items):
    """Desglosa descuentos legales del trabajador según institución de pago."""
    descuentos = [i for i in items if i.tipo == 'DESCUENTO']
    previred = (
        item_monto(descuentos, ['AFP '])
        + items_monto_suma(descuentos, ['Salud ', 'Adicional Isapre'])
        + item_monto(descuentos, ['Seguro de Cesantía', 'Seguro de Cesantia'])
    )
    impuesto_unico = item_monto(descuentos, ['Impuesto Único', 'Impuesto Unico'])
    return previred, impuesto_unico


def _monto_salud_7(liquidacion):
    from .models import IndicadorEconomico

    imponible = liquidacion.total_haberes_imponibles or 0
    indicador = IndicadorEconomico.objects.filter(mes=liquidacion.mes, ano=liquidacion.ano).first()
    if indicador and indicador.tope_imponible_afp_pesos:
        tope = indicador.tope_imponible_afp_pesos
    elif liquidacion.uf_valor:
        tope = round(float(liquidacion.uf_valor) * 81.6)
    else:
        tope = imponible
    base = min(imponible, tope) if tope else imponible
    return round(base * 0.07)


def descuentos_para_presentacion(liquidacion):
    """
    Muestra el 7% obligatorio y, si el plan Isapre lo supera, el adicional debajo.
    Las liquidaciones nuevas ya traen las dos líneas. Las antiguas, un solo ítem, se parten aquí.
    """
    items = list(liquidacion.items.filter(tipo='DESCUENTO').order_by('id'))
    if any((i.nombre or '').lower().startswith('adicional isapre') for i in items):
        return items

    salud_idx = next(
        (i for i, item in enumerate(items) if (item.nombre or '').upper().startswith('SALUD ')),
        None,
    )
    if salud_idx is None:
        return items

    salud = items[salud_idx]
    nombre_sys = (liquidacion.salud_nombre or '').strip() or 'Salud'
    etiqueta_7 = f'Salud {nombre_sys} (7%)'
    siete = _monto_salud_7(liquidacion)
    if siete <= 0 or salud.monto <= siete:
        if '(7%)' not in (salud.nombre or ''):
            items[salud_idx] = LineaPresentacion(etiqueta_7, salud.monto)
        return items

    items[salud_idx] = LineaPresentacion(etiqueta_7, siete)
    items.insert(salud_idx + 1, LineaPresentacion('Adicional Isapre', salud.monto - siete))
    return items
