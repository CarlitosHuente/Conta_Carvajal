"""Exportación CSV para declaración Previred / respaldo contable."""

import csv
import io

from .liquidacion_items import item_monto as _item_monto
from .models import Liquidacion


def generar_csv_previred(empresa, mes, ano):
    """
    Genera CSV con separador ; (Excel Chile) con datos de liquidaciones del período.
    """
    liquidaciones = (
        Liquidacion.objects.filter(
            contrato__trabajador__empresa=empresa,
            mes=mes,
            ano=ano,
        )
        .select_related('contrato__trabajador', 'contrato__afp')
        .prefetch_related('items')
        .order_by('contrato__trabajador__apellido_paterno')
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow([
        'RUT',
        'Nombre',
        'Días trabajados',
        'Renta imponible',
        'Renta no imponible',
        'Asignación familiar',
        'Cotización AFP trabajador',
        'Cotización salud trabajador',
        'Cotización cesantía trabajador',
        'Impuesto único',
        'Otros descuentos',
        'Líquido',
        'Cotización SIS empleador',
        'Cotización AFC empleador',
        'AFP',
        'Sistema salud',
    ])

    for liq in liquidaciones:
        t = liq.contrato.trabajador
        descuentos = [i for i in liq.items.all() if i.tipo == 'DESCUENTO']
        monto_afp = _item_monto(descuentos, ['AFP '])
        monto_salud = _item_monto(descuentos, ['Salud '])
        monto_cesantia = _item_monto(descuentos, ['Seguro de Cesantía'])
        monto_iu = _item_monto(descuentos, ['Impuesto Único'])

        writer.writerow([
            t.rut,
            t.nombre_completo,
            liq.dias_trabajados,
            liq.total_haberes_imponibles,
            liq.total_haberes_no_imponibles,
            liq.total_asignacion_familiar,
            monto_afp,
            monto_salud,
            monto_cesantia,
            monto_iu,
            liq.total_descuentos_varios,
            liq.sueldo_liquido,
            liq.cotizacion_sis_empleador,
            liq.cotizacion_afc_empleador,
            liq.afp_nombre,
            liq.salud_nombre,
        ])

    return buffer.getvalue()
