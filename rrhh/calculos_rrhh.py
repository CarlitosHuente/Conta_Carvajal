"""Funciones auxiliares de cálculo RR.HH."""


def valor_hora_contrato(contrato):
    """Valor hora ordinaria según sueldo mensual y jornada del contrato."""
    horas_semanales = contrato.horas_semanales or 45
    dias_semana = contrato.dias_semana or 5
    if horas_semanales <= 0 or dias_semana <= 0:
        return 0
    horas_mes = (horas_semanales / dias_semana) * 30
    if horas_mes <= 0:
        return 0
    return contrato.sueldo_base / horas_mes


def calcular_horas_extras(contrato, horas_50, horas_100):
    """Monto imponible por horas extras 50% y 100%."""
    valor_hora = valor_hora_contrato(contrato)
    if valor_hora <= 0:
        return 0, []
    items = []
    total = 0
    if horas_50 and horas_50 > 0:
        monto = round(valor_hora * 1.5 * horas_50)
        items.append((f'Horas Extras 50% ({horas_50} h)', monto))
        total += monto
    if horas_100 and horas_100 > 0:
        monto = round(valor_hora * 2.0 * horas_100)
        items.append((f'Horas Extras 100% ({horas_100} h)', monto))
        total += monto
    return total, items


def calcular_asignacion_familiar(indicador, total_imponible, num_cargas):
    """Asignación familiar mensual según tramo de renta imponible."""
    if num_cargas <= 0 or total_imponible <= 0:
        return 0
    if total_imponible <= indicador.asig_familiar_tramo_a_limite:
        monto_carga = indicador.asig_familiar_tramo_a_monto
    elif total_imponible <= indicador.asig_familiar_tramo_b_limite:
        monto_carga = indicador.asig_familiar_tramo_b_monto
    elif total_imponible <= indicador.asig_familiar_tramo_c_limite:
        monto_carga = indicador.asig_familiar_tramo_c_monto
    else:
        return 0
    return monto_carga * num_cargas


def tasa_afc_empleador(contrato):
    """Tasa AFC empleador: 2,4% indefinido, 3% plazo fijo."""
    if contrato.fecha_fin:
        return 0.03
    return 0.024


def saldo_vacaciones_trabajador(trabajador, hasta_fecha=None):
    """
    Saldo de vacaciones en días: devengados (1,25/mes) menos gozados y ajustes.
  """
    from datetime import date
    from decimal import Decimal

    hasta = hasta_fecha or date.today()
    contrato = (
        trabajador.contratos.filter(fecha_inicio__lte=hasta)
        .order_by('-fecha_inicio')
        .first()
    )
    if not contrato:
        return Decimal('0')

    inicio = contrato.fecha_inicio
    if hasta < inicio:
        return Decimal('0')

    meses = (hasta.year - inicio.year) * 12 + (hasta.month - inicio.month)
    if hasta.day >= inicio.day:
        meses += 1
    meses = max(0, meses)
    devengados_auto = Decimal(str(meses)) * Decimal('1.25')

    movs = trabajador.movimientos_vacaciones.filter(fecha__lte=hasta)
    devengados_extra = sum(m.dias for m in movs.filter(tipo='DEVENGADO'))
    gozados = sum(m.dias for m in movs.filter(tipo='GOZADO'))
    ajustes = sum(m.dias for m in movs.filter(tipo='AJUSTE'))

    return devengados_auto + devengados_extra - gozados + ajustes
