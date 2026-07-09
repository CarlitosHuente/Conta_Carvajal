"""Cálculo de finiquito simplificado (Chile)."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .calculos_rrhh import saldo_vacaciones_trabajador


def _anos_servicio(fecha_inicio, fecha_termino):
    dias = (fecha_termino - fecha_inicio).days
    if dias <= 0:
        return Decimal('0')
    return Decimal(str(dias)) / Decimal('365.25')


def calcular_indemnizacion_anos_servicio(contrato, fecha_termino, motivo):
    """
    Indemnización por años de servicio (Art. 163 CT) — aplica en despido y mutuo acuerdo.
    30 días de remuneración por año, tope 11 años (330 días).
    """
    if motivo not in ('DESPIDO', 'MUTUO_ACUERDO'):
        return 0
    anos = _anos_servicio(contrato.fecha_inicio, fecha_termino)
    if anos <= 0:
        return 0
    dias_indemnizacion = min(anos * Decimal('30'), Decimal('330'))
    sueldo_diario = Decimal(contrato.sueldo_base_efectivo()) / Decimal('30')
    return int((dias_indemnizacion * sueldo_diario).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calcular_finiquito(contrato, fecha_termino, motivo, incluir_ultimo_mes=False, mes_ultimo=None, ano_ultimo=None):
    """
    Devuelve dict con montos del finiquito sin persistir.
    """
    trabajador = contrato.trabajador
    dias_vac = saldo_vacaciones_trabajador(trabajador, fecha_termino)
    if dias_vac < 0:
        dias_vac = Decimal('0')
    sueldo_diario = Decimal(contrato.sueldo_base_efectivo()) / Decimal('30')
    monto_vacaciones = int((dias_vac * sueldo_diario).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    monto_indemnizacion = calcular_indemnizacion_anos_servicio(contrato, fecha_termino, motivo)
    monto_ultimo_sueldo = 0
    if incluir_ultimo_mes and mes_ultimo and ano_ultimo:
        from .models import Liquidacion
        liq = Liquidacion.objects.filter(
            contrato=contrato, mes=mes_ultimo, ano=ano_ultimo
        ).first()
        if liq:
            monto_ultimo_sueldo = liq.sueldo_liquido
    total = monto_vacaciones + monto_indemnizacion + monto_ultimo_sueldo
    return {
        'dias_vacaciones_pendientes': dias_vac,
        'monto_vacaciones': monto_vacaciones,
        'monto_indemnizacion': monto_indemnizacion,
        'monto_ultimo_sueldo': monto_ultimo_sueldo,
        'total_bruto_finiquito': total,
    }
