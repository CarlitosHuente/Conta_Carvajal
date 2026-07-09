"""Motor de cálculo de asientos desde plantillas de centralización."""

import re


def _evaluar_formula(formula, f29_datos, resultados_cuentas):
    codigos_f29 = re.findall(r'\[(\d+)\]', formula)
    for cod in codigos_f29:
        valor = f29_datos.get(cod, 0) or 0
        formula = formula.replace(f'[{cod}]', str(valor))

    codigos_cta = re.findall(r'\[CTA:([0-9\.]+)\]', formula, flags=re.IGNORECASE)
    for cod in codigos_cta:
        valor = resultados_cuentas.get(cod, 0)
        formula = formula.replace(f'[CTA:{cod}]', str(valor), 1)
        formula = formula.replace(f'[cta:{cod}]', str(valor), 1)

    # Alias: [2.01.03] equivale a [CTA:2.01.03] (código con puntos, no código F29)
    codigos_cta_bare = re.findall(r'\[([0-9]+(?:\.[0-9]+)+)\]', formula)
    for cod in codigos_cta_bare:
        valor = resultados_cuentas.get(cod, 0)
        formula = formula.replace(f'[{cod}]', str(valor), 1)

    if re.search(r'\[[^\]]+\]', formula):
        raise ValueError(
            f'Referencia no resuelta en fórmula: «{formula}». '
            'Use [538] para códigos F29 y [CTA:2.01.03] (o [2.01.03]) para filas ya calculadas arriba.'
        )

    try:
        return round(eval(formula, {"__builtins__": None}, {}))
    except SyntaxError as exc:
        raise ValueError(
            f'Sintaxis inválida en fórmula: «{formula}». '
            'Revise corchetes y operadores; para otras cuentas use [CTA:código].'
        ) from exc


def calcular_asiento_desde_plantilla(plantilla, f29_datos, omitir_cero=True):
    """
    Calcula las líneas de un asiento a partir de una plantilla y los datos del F29.
    Retorna dict con líneas y totales, o None si no hay montos imputables.
    """
    resultados_cuentas = {}
    lineas_calculadas = []
    total_debe = 0
    total_haber = 0

    for linea in plantilla.lineas.all():
        formula = linea.formula
        resultado_linea = _evaluar_formula(formula, f29_datos, resultados_cuentas)
        resultados_cuentas[linea.cuenta.codigo] = resultado_linea

        debe = resultado_linea if linea.tipo_movimiento == 'debe' else 0
        haber = resultado_linea if linea.tipo_movimiento == 'haber' else 0

        if omitir_cero and debe == 0 and haber == 0:
            continue

        total_debe += debe
        total_haber += haber
        lineas_calculadas.append({
            'cuenta_codigo': linea.cuenta.codigo,
            'cuenta_nombre': linea.cuenta.nombre,
            'debe': debe,
            'haber': haber,
        })

    if not lineas_calculadas:
        return None

    if total_debe != total_haber:
        raise ValueError(
            f'Plantilla «{plantilla.nombre}»: descuadre. '
            f'Debe ${total_debe:,} | Haber ${total_haber:,}.'
        )

    return {
        'plantilla': plantilla,
        'plantilla_id': plantilla.id,
        'plantilla_nombre': plantilla.nombre,
        'lineas_calculadas': lineas_calculadas,
        'total_debe': total_debe,
        'total_haber': total_haber,
    }
