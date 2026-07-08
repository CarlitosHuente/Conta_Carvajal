"""Centralización contable de remuneraciones mensuales."""

import calendar
from datetime import date

from django.db import transaction

from contabilidad.models import AsientoContable, CuentaContable, LineaAsiento
from .liquidacion_items import descuentos_trabajador_por_institucion
from .models import Liquidacion, ConfiguracionCentralizacionRRHH


CUENTAS_DEFAULT = {
    'gasto_remuneraciones': ('4.02.01', 'Remuneraciones', 'perdida'),
    'sueldos_por_pagar': ('2.02.01', 'Remuneraciones por Pagar', 'pasivo'),
    'previred_por_pagar': ('2.02.02', 'Cotizaciones Previred por Pagar', 'pasivo'),
    'sis_por_pagar': ('2.02.03', 'SIS por Pagar', 'pasivo'),
    'afc_empleador_por_pagar': ('2.02.04', 'AFC Empleador por Pagar', 'pasivo'),
    'impuesto_unico_por_pagar': ('2.02.05', 'Impuesto Único por Pagar (SII)', 'pasivo'),
    'otros_descuentos': ('2.02.06', 'Otros Descuentos al Personal', 'pasivo'),
}


def _get_or_create_cuenta(empresa, codigo, nombre, tipo):
    cuenta, _ = CuentaContable.objects.get_or_create(
        empresa=empresa,
        codigo=codigo,
        defaults={'nombre': nombre, 'tipo': tipo},
    )
    return cuenta


def obtener_o_crear_configuracion(empresa):
    """Devuelve la config guardada o crea una con cuentas por defecto del plan."""
    try:
        return empresa.config_centralizacion_rrhh
    except ConfiguracionCentralizacionRRHH.DoesNotExist:
        pass

    cuentas = {}
    for key, (codigo, nombre, tipo) in CUENTAS_DEFAULT.items():
        cuentas[key] = _get_or_create_cuenta(empresa, codigo, nombre, tipo)

    return ConfiguracionCentralizacionRRHH.objects.create(
        empresa=empresa,
        cuenta_gasto=cuentas['gasto_remuneraciones'],
        cuenta_sueldos_por_pagar=cuentas['sueldos_por_pagar'],
        cuenta_previred_por_pagar=cuentas['previred_por_pagar'],
        cuenta_impuesto_unico_por_pagar=cuentas['impuesto_unico_por_pagar'],
        cuenta_otros_descuentos=cuentas['otros_descuentos'],
        cuenta_sis_por_pagar=cuentas['sis_por_pagar'],
        cuenta_afc_empleador_por_pagar=cuentas['afc_empleador_por_pagar'],
    )


def cuentas_desde_config(config):
    return {
        'gasto_remuneraciones': config.cuenta_gasto,
        'sueldos_por_pagar': config.cuenta_sueldos_por_pagar,
        'previred_por_pagar': config.cuenta_previred_por_pagar,
        'impuesto_unico_por_pagar': config.cuenta_impuesto_unico_por_pagar,
        'otros_descuentos': config.cuenta_otros_descuentos,
        'sis_por_pagar': config.cuenta_sis_por_pagar,
        'afc_empleador_por_pagar': config.cuenta_afc_empleador_por_pagar,
    }


def resumen_liquidaciones_periodo(empresa, mes, ano):
    liquidaciones = Liquidacion.objects.filter(
        contrato__trabajador__empresa=empresa,
        mes=mes,
        ano=ano,
    ).prefetch_related('items')

    total_haberes = 0
    total_leyes = 0
    total_varios = 0
    total_liquido = 0
    total_sis = 0
    total_afc_emp = 0
    total_previred = 0
    total_impuesto_unico = 0

    for liq in liquidaciones:
        total_haberes += liq.total_haberes_imponibles + liq.total_haberes_no_imponibles
        total_leyes += liq.total_descuentos_legales
        total_varios += liq.total_descuentos_varios
        total_liquido += liq.sueldo_liquido
        total_sis += liq.cotizacion_sis_empleador
        total_afc_emp += liq.cotizacion_afc_empleador
        previred, iu = descuentos_trabajador_por_institucion(liq.items.all())
        total_previred += previred
        total_impuesto_unico += iu

    total_debe = total_haberes + total_sis + total_afc_emp
    total_haber = (
        total_sis + total_afc_emp + total_previred + total_impuesto_unico
        + total_varios + total_liquido
    )

    return {
        'cantidad': liquidaciones.count(),
        'total_haberes': total_haberes,
        'total_leyes': total_leyes,
        'total_varios': total_varios,
        'total_liquido': total_liquido,
        'total_previred': total_previred,
        'total_impuesto_unico': total_impuesto_unico,
        'total_sis': total_sis,
        'total_afc_empleador': total_afc_emp,
        'total_cotizaciones_empleador': total_sis + total_afc_emp,
        'total_gasto': total_debe,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'cuadra': total_debe == total_haber,
    }


def lineas_haber_asiento(resumen, cuentas):
    """Líneas al haber del asiento con cuenta asignada."""
    lineas = []
    if resumen['total_sis'] > 0:
        lineas.append({
            'cuenta': cuentas['sis_por_pagar'],
            'concepto': 'SIS empleador por pagar (Previred)',
            'monto': resumen['total_sis'],
        })
    if resumen['total_afc_empleador'] > 0:
        lineas.append({
            'cuenta': cuentas['afc_empleador_por_pagar'],
            'concepto': 'AFC empleador por pagar (Previred)',
            'monto': resumen['total_afc_empleador'],
        })
    if resumen['total_previred'] > 0:
        lineas.append({
            'cuenta': cuentas['previred_por_pagar'],
            'concepto': 'Cotizaciones Previred (AFP, salud, cesantía trabajador)',
            'monto': resumen['total_previred'],
        })
    if resumen['total_impuesto_unico'] > 0:
        lineas.append({
            'cuenta': cuentas['impuesto_unico_por_pagar'],
            'concepto': 'Impuesto único por pagar (SII)',
            'monto': resumen['total_impuesto_unico'],
        })
    if resumen['total_varios'] > 0:
        lineas.append({
            'cuenta': cuentas['otros_descuentos'],
            'concepto': 'Otros descuentos al personal (préstamos, sindicato, etc.)',
            'monto': resumen['total_varios'],
        })
    if resumen['total_liquido'] > 0:
        lineas.append({
            'cuenta': cuentas['sueldos_por_pagar'],
            'concepto': 'Sueldos por pagar (líquido)',
            'monto': resumen['total_liquido'],
        })
    return lineas


def vista_previa_asiento(resumen, config=None):
    """Líneas del asiento que se generarán (para mostrar en pantalla)."""
    lineas = [{
        'lado': 'debe',
        'concepto': 'Gasto remuneraciones (haberes + SIS + AFC empl.)',
        'monto': resumen['total_gasto'],
        'cuenta': config.cuenta_gasto if config else None,
    }]
    if config:
        for lh in lineas_haber_asiento(resumen, cuentas_desde_config(config)):
            lineas.append({
                'lado': 'haber',
                'concepto': lh['concepto'],
                'monto': lh['monto'],
                'cuenta': lh['cuenta'],
            })
    else:
        if resumen['total_sis'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'SIS empleador por pagar', 'monto': resumen['total_sis']})
        if resumen['total_afc_empleador'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'AFC empleador por pagar', 'monto': resumen['total_afc_empleador']})
        if resumen['total_previred'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'Cotizaciones Previred', 'monto': resumen['total_previred']})
        if resumen['total_impuesto_unico'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'Impuesto único (SII)', 'monto': resumen['total_impuesto_unico']})
        if resumen['total_varios'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'Otros descuentos al personal', 'monto': resumen['total_varios']})
        if resumen['total_liquido'] > 0:
            lineas.append({'lado': 'haber', 'concepto': 'Sueldos por pagar (líquido)', 'monto': resumen['total_liquido']})
    return lineas


@transaction.atomic
def generar_asiento_remuneraciones(empresa, mes, ano, config=None):
    """
    Crea asiento contable del período de remuneraciones.
    Debe: Gasto = haberes + SIS + AFC empleador
    Haber: pasivos por institución (Previred, SII, otros) + sueldos líquidos
    """
    if AsientoContable.objects.filter(
        empresa=empresa, origen_rrhh_mes=mes, origen_rrhh_ano=ano,
    ).exists():
        raise ValueError('Ya existe un asiento de remuneraciones para este período.')

    resumen = resumen_liquidaciones_periodo(empresa, mes, ano)
    if resumen['cantidad'] == 0:
        raise ValueError('No hay liquidaciones emitidas en el período.')
    if not resumen['cuadra']:
        raise ValueError(
            f'El resumen no cuadra: Debe ${resumen["total_debe"]:,} vs Haber ${resumen["total_haber"]:,}. '
            'Revisa las liquidaciones del período.'
        )

    config = config or obtener_o_crear_configuracion(empresa)
    cuentas = cuentas_desde_config(config)

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fecha_asiento = date(ano, mes, ultimo_dia)
    glosa = f'Centralización remuneraciones {mes:02d}/{ano}'

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha_asiento,
        glosa=glosa,
        origen_rrhh_mes=mes,
        origen_rrhh_ano=ano,
        tipo_asiento='rrhh',
    )

    LineaAsiento.objects.create(
        asiento=asiento, cuenta=cuentas['gasto_remuneraciones'],
        debe=resumen['total_gasto'], haber=0,
    )
    for lh in lineas_haber_asiento(resumen, cuentas):
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=lh['cuenta'],
            debe=0, haber=lh['monto'],
        )

    return asiento, resumen
