import calendar
import math
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from .models import Liquidacion, ItemLiquidacion, IndicadorEconomico, NovedadMensual, ConceptoVariable


def etiqueta_descuento_salud(contrato):
    """Texto del ítem de liquidación, tipo AFP (nombre + dato entre paréntesis)."""
    nombre_sys = (contrato.sistema_salud.nombre or '').strip()
    base = f'Salud {nombre_sys}'
    if nombre_sys.upper() == 'FONASA':
        return f'{base} (7%)'
    plan = contrato.plan_salud_pactado
    if plan is not None and Decimal(str(plan)) > 0:
        if contrato.moneda_plan_salud == 'UF':
            d = Decimal(str(plan)).quantize(Decimal('0.001'))
            frac = format(d, 'f').rstrip('0').rstrip('.')
            return f'{base} ({frac} UF)'
        clp = int(round(float(plan)))
        miles = f'{clp:,}'.replace(',', '.')
        return f'{base} (plan ${miles})'
    return f'{base} (7%)'


def calcular_impuesto_unico(base_tributable, utm):
    """
    Calcula el Impuesto Único de Segunda Categoría según la tabla del SII.
    Recibe la Base Tributable (Imponible - Dctos Legales) y el valor de la UTM del mes.
    """
    if base_tributable <= 0 or utm <= 0:
        return 0
        
    factor = base_tributable / utm
    
    # Tramos legales chilenos actualizados
    if factor <= 13.5:
        return 0
    elif factor <= 30:
        rebaja = 0.54 * utm
        return max(0, round((base_tributable * 0.04) - float(rebaja)))
    elif factor <= 50:
        rebaja = 1.74 * utm
        return max(0, round((base_tributable * 0.08) - float(rebaja)))
    elif factor <= 70:
        rebaja = 4.49 * utm
        return max(0, round((base_tributable * 0.135) - float(rebaja)))
    elif factor <= 90:
        rebaja = 11.14 * utm
        return max(0, round((base_tributable * 0.23) - float(rebaja)))
    elif factor <= 120:
        rebaja = 17.80 * utm
        return max(0, round((base_tributable * 0.304) - float(rebaja)))
    elif factor <= 150:
        rebaja = 23.32 * utm
        return max(0, round((base_tributable * 0.35) - float(rebaja)))
    else:
        rebaja = 30.82 * utm
        return max(0, round((base_tributable * 0.40) - float(rebaja)))

@transaction.atomic
def procesar_liquidacion(contrato, mes, ano):
    """
    Cerebro del ERP: Genera la liquidación de sueldo respetando topes e impuestos.
    Usa transaction.atomic para que, si algo falla, no guarde datos a medias.
    """
    # 1. Búsqueda de Indicadores (Con fallback a la herencia más cercana)
    indicador = IndicadorEconomico.objects.filter(ano__lte=ano, mes__lte=mes).order_by('-ano', '-mes').first()
    if not indicador:
        raise ValueError("No existen indicadores económicos base para calcular la liquidación.")

    uf = float(indicador.uf)
    utm = float(indicador.utm)

    # 2. Búsqueda de Novedades del Mes
    novedad = NovedadMensual.objects.filter(trabajador=contrato.trabajador, mes=mes, ano=ano).first()
    dias_trabajados = novedad.dias_trabajados if novedad else 30
    if dias_trabajados <= 0:
        return None # No se emite liquidación si no trabajó ningún día

    # --- FASE 1: CÁLCULO DE HABERES ---
    items_a_guardar = []
    total_imponible = 0
    total_no_imponible = 0

    # A. Sueldo Base Proporcional
    sueldo_proporcional = round((contrato.sueldo_base / 30) * dias_trabajados)
    items_a_guardar.append(('Sueldo Base', sueldo_proporcional, 'HABER', True))
    total_imponible += sueldo_proporcional

    # B. Gross Up del Bono Esporádico Líquido (Aproximación estándar)
    if novedad and novedad.bono_esporadico > 0:
        # Calculamos cuánto debe ser el Bruto para que al quitarle AFP (aprox 11%), Salud (7%) y AFC (0.6%) quede el Líquido exacto
        factor_descuentos = (float(contrato.afp.tasa_dependiente) + 7.0 + 0.6) / 100
        bono_bruto = round(novedad.bono_esporadico / (1 - factor_descuentos))
        items_a_guardar.append(('Bono Producción (Brutificado)', bono_bruto, 'HABER', True))
        total_imponible += bono_bruto

    # C. Ítems Fijos del Contrato (Bonos extra)
    for item in contrato.items_recurrentes.filter(tipo='HABER'):
        items_a_guardar.append((item.nombre, item.monto, 'HABER', item.es_imponible))
        if item.es_imponible:
            total_imponible += item.monto
        else:
            total_no_imponible += item.monto

    # D. Gratificación Legal (Art. 47 / 50 — simplificación mensual en sistema)
    # Base del 25%: total_imponible acumulado hasta aquí (sueldo prop., bono brutif., ítems imponibles).
    # Tope mensual: (4,75 × sueldo_mínimo del indicador económico usado) / 12. Ese sueldo_mínimo es el
    # valor cargado en IndicadorEconomico para la fila seleccionada (misma que UF/UTM del cálculo).
    if contrato.tipo_gratificacion == 'LEGAL':
        tope_gratificacion = round((indicador.sueldo_minimo * 4.75) / 12)
        gratificacion = round(total_imponible * 0.25)
        gratificacion_final = min(gratificacion, tope_gratificacion)
        items_a_guardar.append(('Gratificación Legal (Art. 50)', gratificacion_final, 'HABER', True))
        total_imponible += gratificacion_final
    elif contrato.tipo_gratificacion == 'FIJA' and contrato.monto_gratificacion_fija > 0:
        items_a_guardar.append(('Gratificación Fija', contrato.monto_gratificacion_fija, 'HABER', True))
        total_imponible += contrato.monto_gratificacion_fija

    # E. No Imponibles Base (Colación y Movilización Proporcional)
    if contrato.colacion > 0:
        colacion_prop = round((contrato.colacion / 30) * dias_trabajados)
        items_a_guardar.append(('Colación', colacion_prop, 'HABER', False))
        total_no_imponible += colacion_prop
        
    if contrato.movilizacion > 0:
        movilizacion_prop = round((contrato.movilizacion / 30) * dias_trabajados)
        items_a_guardar.append(('Movilización', movilizacion_prop, 'HABER', False))
        total_no_imponible += movilizacion_prop
        
    # F. Haberes Variables (Comisiones, etc. desde el JSON)
    if novedad and novedad.datos_variables:
        for concepto_id, base_calculo in novedad.datos_variables.items():
            try:
                # La clave en el JSON es el ID del ConceptoVariable
                concepto = ConceptoVariable.objects.get(id=int(concepto_id))
                valor_calculado = 0
                if concepto.tipo_calculo == 'PORCENTAJE':
                    valor_calculado = round(int(base_calculo) * (float(concepto.porcentaje_calculo) / 100))
                elif concepto.tipo_calculo == 'TRAMOS':
                    # Monto ingresado = BRUTO (misma moneda que límites de tramo). Clasificación por bruto.
                    # Tasa del tramo × NETO entero, con IVA global (settings / env).
                    bruto_int = int(base_calculo)
                    iva_pct = float(
                        getattr(
                            settings,
                            'CONCEPTO_VARIABLE_TRAMOS_IVA_PORCIENTO',
                            19,
                        )
                    )
                    iva_pct = max(0.0, iva_pct)
                    factor_iva = 1 + (iva_pct / 100.0)
                    neto_int = max(0, round(bruto_int / factor_iva)) if factor_iva > 0 else bruto_int

                    tramo_encontrado = None
                    for tramo in concepto.tramos.all():
                        if bruto_int >= tramo.tramo_desde:
                            if tramo.tramo_hasta is None or bruto_int <= tramo.tramo_hasta:
                                tramo_encontrado = tramo
                                break

                    if tramo_encontrado:
                        valor_calculado = round(
                            neto_int * (float(tramo_encontrado.porcentaje) / 100)
                        )
                
                if valor_calculado > 0:
                    items_a_guardar.append((concepto.nombre, valor_calculado, 'HABER', concepto.es_imponible))
                    if concepto.es_imponible:
                        total_imponible += valor_calculado
                    else:
                        total_no_imponible += valor_calculado
            except (ConceptoVariable.DoesNotExist, ValueError, TypeError):
                continue # Si el concepto fue borrado o el dato es inválido, lo ignoramos

    # --- FASE 2: CÁLCULO DE DESCUENTOS LEGALES ---
    total_descuentos_legales = 0
    
    # APLICACIÓN DE TOPES
    imponible_afp_salud = min(total_imponible, indicador.tope_imponible_afp_pesos)
    imponible_cesantia = min(total_imponible, indicador.tope_imponible_cesantia_pesos)

    # A. AFP
    # Lógica dinámica para obtener la tasa correcta del período
    afp_nombre_normalizado = contrato.afp.nombre.lower().replace(' ', '_').replace('á', 'a').replace('é', 'e')
    tasa_field_name = f'tasa_afp_{afp_nombre_normalizado}'
    
    if not hasattr(indicador, tasa_field_name):
        raise ValueError(f"Error de configuración: El campo de tasa '{tasa_field_name}' no existe en el modelo IndicadorEconomico.")
        
    tasa_afp_historica = getattr(indicador, tasa_field_name)
    monto_afp = round(imponible_afp_salud * (float(tasa_afp_historica) / 100))
    items_a_guardar.append((f'AFP {contrato.afp.nombre} ({tasa_afp_historica}%)', monto_afp, 'DESCUENTO', False))
    total_descuentos_legales += monto_afp

    # B. Salud (7% Fonasa o Plan Isapre en UF)
    salud_7_pct = round(imponible_afp_salud * 0.07)
    monto_salud_final = salud_7_pct
    
    if contrato.sistema_salud.nombre != 'FONASA' and contrato.plan_salud_pactado > 0:
        if contrato.moneda_plan_salud == 'UF':
            costo_plan_pesos = round(float(contrato.plan_salud_pactado) * uf)
        else:
            costo_plan_pesos = float(contrato.plan_salud_pactado)
            
        # La ley exige que la Isapre cobre mínimo el 7%. Si el plan es mayor, se cobra la diferencia como "Adicional Isapre".
        monto_salud_final = max(salud_7_pct, costo_plan_pesos)
        
    items_a_guardar.append((etiqueta_descuento_salud(contrato), monto_salud_final, 'DESCUENTO', False))
    total_descuentos_legales += monto_salud_final

    # C. Seguro de Cesantía (0.6% si es indefinido)
    monto_cesantia = 0
    if not contrato.fecha_fin: # Es indefinido
        monto_cesantia = round(imponible_cesantia * 0.006)
        items_a_guardar.append(('Seguro de Cesantía (0.6%)', monto_cesantia, 'DESCUENTO', False))
        total_descuentos_legales += monto_cesantia

    # D. Impuesto Único de Segunda Categoría
    # Base tributable (art. 43 LIR criterio habitual): se rebajan AFP, cesantía y solo el 7% de salud
    # sobre el imponible tope, aunque el descuento de caja por Isapre/plan pactado sea mayor.
    descuentos_para_base_iu = monto_afp + salud_7_pct + monto_cesantia
    base_tributable = max(0, total_imponible - descuentos_para_base_iu)
    monto_impuesto = calcular_impuesto_unico(base_tributable, utm)
    if monto_impuesto > 0:
        items_a_guardar.append(('Impuesto Único 2da Cat.', monto_impuesto, 'DESCUENTO', False))
        total_descuentos_legales += monto_impuesto

    # --- FASE 3: DESCUENTOS VARIOS Y CIERRE ---
    total_descuentos_varios = 0
    
    # Aplicar descuentos fijos (Cuotas sindicales, etc.)
    for item in contrato.items_recurrentes.filter(tipo='DESCUENTO'):
        items_a_guardar.append((item.nombre, item.monto, 'DESCUENTO', False))
        total_descuentos_varios += item.monto
        
    # Descuento esporádico (Novedades)
    if novedad and novedad.descuento_esporadico > 0:
        items_a_guardar.append(('Descuento por Novedades', novedad.descuento_esporadico, 'DESCUENTO', False))
        total_descuentos_varios += novedad.descuento_esporadico

    # ALCANCE LÍQUIDO FINAL
    sueldo_liquido = (total_imponible + total_no_imponible) - (total_descuentos_legales + total_descuentos_varios)

    # 4. GUARDAR EN BASE DE DATOS (Fotografía inmutable)
    # Eliminamos si ya existía una generada en este mes para reemplazarla
    Liquidacion.objects.filter(contrato=contrato, mes=mes, ano=ano).delete()

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fecha_emision = date(ano, mes, ultimo_dia)

    liq = Liquidacion.objects.create(
        contrato=contrato, mes=mes, ano=ano, fecha_emision=fecha_emision,
        dias_trabajados=dias_trabajados,
        fecha_ingreso_contrato=contrato.fecha_inicio,
        cargo_contrato=(contrato.cargo or '')[:120],
        uf_valor=uf, utm_valor=utm, afp_nombre=contrato.afp.nombre, afp_tasa=tasa_afp_historica,
        salud_nombre=contrato.sistema_salud.nombre, total_haberes_imponibles=total_imponible,
        total_haberes_no_imponibles=total_no_imponible, total_descuentos_legales=total_descuentos_legales,
        total_descuentos_varios=total_descuentos_varios, sueldo_liquido=sueldo_liquido
    )

    for nombre, monto, tipo, es_imponible in items_a_guardar:
        ItemLiquidacion.objects.create(liquidacion=liq, nombre=nombre, monto=monto, tipo=tipo, es_imponible=es_imponible)
        
    return liq