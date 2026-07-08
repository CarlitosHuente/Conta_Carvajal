"""Centralización contable de remuneraciones mensuales."""

import calendar
from datetime import date

from django.db import transaction

from contabilidad.models import AsientoContable, CuentaContable, LineaAsiento
from .models import Liquidacion


CUENTAS_SUGERIDAS = {
    'gasto_remuneraciones': ('4.1.01.01', 'Gasto Remuneraciones'),
    'sueldos_por_pagar': ('2.1.01.01', 'Sueldos por Pagar'),
    'cotizaciones_por_pagar': ('2.1.02.01', 'Cotizaciones por Pagar'),
    'sis_por_pagar': ('2.1.02.02', 'SIS por Pagar'),
    'afc_empleador_por_pagar': ('2.1.02.03', 'AFC Empleador por Pagar'),
}


def _get_or_create_cuenta(empresa, codigo, nombre, tipo='pasivo'):
    cuenta, _ = CuentaContable.objects.get_or_create(
        empresa=empresa,
        codigo=codigo,
        defaults={'nombre': nombre, 'tipo': tipo},
    )
    return cuenta


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
    return {
        'cantidad': liquidaciones.count(),
        'total_haberes': total_haberes,
        'total_leyes': total_leyes,
        'total_varios': total_varios,
        'total_liquido': total_liquido,
        'total_sis': total_sis,
        'total_afc_empleador': total_afc_emp,
        'total_cotizaciones_empleador': total_sis + total_afc_emp,
        'total_gasto': total_haberes + total_sis + total_afc_emp,
    }


@transaction.atomic
def generar_asiento_remuneraciones(empresa, mes, ano, cuentas_map=None):
    """
    Crea asiento contable del período de remuneraciones.
    Debe: Gasto remuneraciones + SIS + AFC empleador
    Haber: Cotizaciones por pagar (leyes+varios) + Sueldos por pagar (líquido)
    """
    if AsientoContable.objects.filter(
        empresa=empresa, origen_rrhh_mes=mes, origen_rrhh_ano=ano
    ).exists():
        raise ValueError('Ya existe un asiento de remuneraciones para este período.')

    resumen = resumen_liquidaciones_periodo(empresa, mes, ano)
    if resumen['cantidad'] == 0:
        raise ValueError('No hay liquidaciones emitidas en el período.')

    cuentas_map = cuentas_map or {}
    cuentas = {}
    for key, (codigo, nombre) in CUENTAS_SUGERIDAS.items():
        cod = cuentas_map.get(key, codigo)
        nom = cuentas_map.get(f'{key}_nombre', nombre)
        tipo = 'perdida' if key == 'gasto_remuneraciones' else 'pasivo'
        cuentas[key] = _get_or_create_cuenta(empresa, cod, nom, tipo)

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fecha_asiento = date(ano, mes, ultimo_dia)
    glosa = f'Centralización remuneraciones {mes:02d}/{ano}'

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha_asiento,
        glosa=glosa,
        origen_rrhh_mes=mes,
        origen_rrhh_ano=ano,
    )

    gasto_total = resumen['total_gasto']
    cotizaciones_trab = resumen['total_leyes'] + resumen['total_varios']

    LineaAsiento.objects.create(
        asiento=asiento, cuenta=cuentas['gasto_remuneraciones'], debe=gasto_total, haber=0,
    )
    if resumen['total_sis'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['sis_por_pagar'], debe=0, haber=resumen['total_sis'],
        )
    if resumen['total_afc_empleador'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['afc_empleador_por_pagar'], debe=0, haber=resumen['total_afc_empleador'],
        )
    if cotizaciones_trab > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['cotizaciones_por_pagar'], debe=0, haber=cotizaciones_trab,
        )
    if resumen['total_liquido'] > 0:
        LineaAsiento.objects.create(
            asiento=asiento, cuenta=cuentas['sueldos_por_pagar'], debe=0, haber=resumen['total_liquido'],
        )

    return asiento, resumen
