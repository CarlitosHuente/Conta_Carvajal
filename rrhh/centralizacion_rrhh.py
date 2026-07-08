"""Centralización contable de remuneraciones mensuales."""

import calendar
from datetime import date

from django.db import transaction

from contabilidad.models import AsientoContable, CuentaContable, LineaAsiento
from .models import Liquidacion, ConfiguracionCentralizacionRRHH


CUENTAS_DEFAULT = {
    'gasto_remuneraciones': ('4.02.01', 'Remuneraciones', 'perdida'),
    'sueldos_por_pagar': ('2.02.01', 'Remuneraciones por Pagar', 'pasivo'),
    'cotizaciones_por_pagar': ('2.02.02', 'Cotizaciones Previsionales por Pagar', 'pasivo'),
    'sis_por_pagar': ('2.02.03', 'SIS por Pagar', 'pasivo'),
    'afc_empleador_por_pagar': ('2.02.04', 'AFC Empleador por Pagar', 'pasivo'),
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
        cuenta_cotizaciones_por_pagar=cuentas['cotizaciones_por_pagar'],
        cuenta_sis_por_pagar=cuentas['sis_por_pagar'],
        cuenta_afc_empleador_por_pagar=cuentas['afc_empleador_por_pagar'],
    )


def cuentas_desde_config(config):
    return {
        'gasto_remuneraciones': config.cuenta_gasto,
        'sueldos_por_pagar': config.cuenta_sueldos_por_pagar,
        'cotizaciones_por_pagar': config.cuenta_cotizaciones_por_pagar,
        'sis_por_pagar': config.cuenta_sis_por_pagar,
        'afc_empleador_por_pagar': config.cuenta_afc_empleador_por_pagar,
    }


def resumen_liquidaciones_periodo(empresa, mes, ano):
    liquidaciones = Liquidacion.objects.filter(
        contrato__trabajador__empresa=empresa,
        mes=mes,
        ano=ano,
    )
    total_haberes = sum(liq.total_haberes_imponibles + liq.total_haberes_no_imponibles for liq in liquidaciones)
    total_leyes = sum(liq.total_descuentos_legales for liq in liquidaciones)
    total_varios = sum(liq.total_descuentos_varios for liq in liquidaciones)
    total_liquido = sum(liq.sueldo_liquido for liq in liquidaciones)
    total_sis = sum(liq.cotizacion_sis_empleador for liq in liquidaciones)
    total_afc_emp = sum(liq.cotizacion_afc_empleador for liq in liquidaciones)

    total_debe = total_haberes + total_sis + total_afc_emp
    total_haber = total_sis + total_afc_emp + total_leyes + total_varios + total_liquido

    return {
        'cantidad': liquidaciones.count(),
        'total_haberes': total_haberes,
        'total_leyes': total_leyes,
        'total_varios': total_varios,
        'total_liquido': total_liquido,
        'total_sis': total_sis,
        'total_afc_empleador': total_afc_emp,
        'total_cotizaciones_empleador': total_sis + total_afc_emp,
        'total_gasto': total_debe,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'cuadra': total_debe == total_haber,
    }


def vista_previa_asiento(resumen):
    """Líneas del asiento que se generarán (para mostrar en pantalla)."""
    lineas = [
        {
            'lado': 'debe',
            'concepto': 'Gasto remuneraciones (haberes + SIS + AFC empl.)',
            'monto': resumen['total_gasto'],
        },
    ]
    if resumen['total_sis'] > 0:
        lineas.append({'lado': 'haber', 'concepto': 'SIS empleador por pagar', 'monto': resumen['total_sis']})
    if resumen['total_afc_empleador'] > 0:
        lineas.append({
            'lado': 'haber', 'concepto': 'AFC empleador por pagar',
            'monto': resumen['total_afc_empleador'],
        })
    cotizaciones_trab = resumen['total_leyes'] + resumen['total_varios']
    if cotizaciones_trab > 0:
        lineas.append({
            'lado': 'haber',
            'concepto': 'Cotizaciones por pagar (AFP, salud, cesantía, IU, otros)',
            'monto': cotizaciones_trab,
        })
    if resumen['total_liquido'] > 0:
        lineas.append({'lado': 'haber', 'concepto': 'Sueldos por pagar (líquido)', 'monto': resumen['total_liquido']})
    return lineas


@transaction.atomic
def generar_asiento_remuneraciones(empresa, mes, ano, config=None):
    """
    Crea asiento contable del período de remuneraciones.
    Debe: Gasto = haberes + SIS + AFC empleador
    Haber: SIS + AFC + cotizaciones trabajador + sueldos líquidos
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

    cotizaciones_trab = resumen['total_leyes'] + resumen['total_varios']

    LineaAsiento.objects.create(
        asiento=asiento, cuenta=cuentas['gasto_remuneraciones'],
        debe=resumen['total_gasto'], haber=0,
    )
    if resumen['total_sis'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['sis_por_pagar'],
            debe=0, haber=resumen['total_sis'],
        )
    if resumen['total_afc_empleador'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['afc_empleador_por_pagar'],
            debe=0, haber=resumen['total_afc_empleador'],
        )
    if cotizaciones_trab > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['cotizaciones_por_pagar'],
            debe=0, haber=cotizaciones_trab,
        )
    if resumen['total_liquido'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['sueldos_por_pagar'],
            debe=0, haber=resumen['total_liquido'],
        )

    return asiento, resumen
