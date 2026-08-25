"""ETA simulada: FECHA del Excel (zarpe Ecuador) + días de viaje a SA / Valparaíso."""

from calendar import MONDAY, Calendar
from datetime import date, datetime
import unicodedata

import pandas as pd
import pytz
from django.utils import timezone

from invergesal.services.parametros_viaje import clave_buque, color_para_cajas, leer_dias_viaje

TZ_CHILE = pytz.timezone('America/Santiago')
PUERTO_SA = 'SAN ANTONIO'
PUERTO_VAP = 'VALPARAISO'


def _sin_tildes(texto):
    normalizado = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in normalizado if not unicodedata.combining(c))


def clasificar_puerto(nombre):
    limpio = ' '.join(_sin_tildes(nombre).upper().split())
    if 'SAN ANTONIO' in limpio:
        return PUERTO_SA
    if 'VALPARAISO' in limpio:
        return PUERTO_VAP
    return None


def _celda(dia, hoy, primer_dia, sa=None, vap=None, tramos=None):
    sa = sa or []
    vap = vap or []
    cajas = sum(n['cajas'] for n in sa) + sum(n['cajas'] for n in vap)
    naves = len(sa) + len(vap)
    color, oscuro = color_para_cajas(cajas, tramos)
    return {
        'fecha': dia,
        'iso': dia.isoformat(),
        'en_mes': dia.month == primer_dia.month and dia.year == primer_dia.year,
        'es_hoy': dia == hoy,
        'san_antonio': sa,
        'valparaiso': vap,
        'total_naves': naves,
        'total_cajas': cajas,
        'color': color,
        'texto_claro': oscuro,
    }


def _clave_mes(dia):
    return f'{dia.year:04d}-{dia.month:02d}'


def _sumar_meses(primer_dia, delta):
    mes = primer_dia.month - 1 + delta
    anio = primer_dia.year + mes // 12
    mes = mes % 12 + 1
    return date(anio, mes, 1)


def parse_mes(mes_txt, hoy=None):
    hoy = hoy or timezone.now().astimezone(TZ_CHILE).date()
    texto = (mes_txt or '').strip()
    if texto:
        try:
            anio_txt, mes_txt_n = texto.split('-', 1)
            anio, mes = int(anio_txt), int(mes_txt_n)
            if 2000 <= anio <= 2100 and 1 <= mes <= 12:
                return date(anio, mes, 1)
        except (TypeError, ValueError):
            pass
    return date(hoy.year, hoy.month, 1)


def _as_date(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    ts = pd.to_datetime(valor, errors='coerce')
    if pd.isna(ts):
        return None
    return ts.date()


def _texto(valor, vacio='(sin dato)'):
    if valor is None:
        return vacio
    try:
        if pd.isna(valor):
            return vacio
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none'):
        return vacio
    return texto


def _cajas_entero(valor):
    return int(round(float(valor or 0)))


def _como_naves(filas):
    naves = {}
    for row in filas:
        eta = _as_date(row['_eta_d'])
        if not eta:
            continue
        puerto = row['_puerto']
        clave = (eta, puerto, row['_nave'])
        if clave not in naves:
            naves[clave] = {
                'nave': row['_nave'],
                'naviera': row['_naviera'],
                'puerto': puerto,
                'puerto_corto': 'SA' if puerto == PUERTO_SA else 'Valparaíso',
                'dias_viaje': int(row['_dias']),
                'eta': eta,
                'cajas': 0,
                'salidas': [],
                'marcas': {},
            }
        nave = naves[clave]
        cajas = _cajas_entero(row['_cajas'])
        nave['cajas'] += cajas
        if row['_naviera'] and not nave['naviera']:
            nave['naviera'] = row['_naviera']
        salida = _as_date(row['_salida'])
        if salida and salida not in nave['salidas']:
            nave['salidas'].append(salida)
        marca_nom = row['_marca']
        marcas = nave['marcas']
        if marca_nom not in marcas:
            marcas[marca_nom] = {'marca': marca_nom, 'cajas': 0, 'consignatarios': {}}
        marcas[marca_nom]['cajas'] += cajas
        cons_nom = row['_consignatario']
        consignatarios = marcas[marca_nom]['consignatarios']
        if cons_nom not in consignatarios:
            consignatarios[cons_nom] = {'consignatario': cons_nom, 'cajas': 0}
        consignatarios[cons_nom]['cajas'] += cajas

    resultado = []
    for nave in naves.values():
        marcas = []
        for marca in nave['marcas'].values():
            consignatarios = sorted(
                marca['consignatarios'].values(),
                key=lambda item: (-item['cajas'], item['consignatario']),
            )
            marcas.append({
                'marca': marca['marca'],
                'cajas': marca['cajas'],
                'consignatarios': consignatarios,
            })
        marcas.sort(key=lambda item: (-item['cajas'], item['marca']))
        salidas = sorted(nave['salidas'])
        nave['marcas'] = marcas
        nave['fecha_excel'] = salidas[0] if salidas else None
        nave['varias_fechas'] = len(salidas) > 1
        del nave['salidas']
        resultado.append(nave)
    resultado.sort(key=lambda item: (-item['cajas'], item['nave']))
    return resultado


def listar_buques_config(df, dias_buques):
    nombres = {str(nombre).strip() for nombre in (dias_buques or {}) if str(nombre).strip()}
    if df is not None and not getattr(df, 'empty', True) and 'NAVE' in df.columns:
        work = df.copy()
        if 'PUERTO_DESCARGA' in work.columns:
            work['_puerto'] = work['PUERTO_DESCARGA'].map(clasificar_puerto)
            work = work[work['_puerto'].isin((PUERTO_SA, PUERTO_VAP))]
        for nombre in work['NAVE'].dropna().astype(str).str.strip().unique():
            if nombre:
                nombres.add(nombre)
    mapa = {clave_buque(nombre): (nombre, dias) for nombre, dias in (dias_buques or {}).items()}
    vistos = set()
    filas = []
    for nombre in sorted(nombres, key=lambda item: item.upper()):
        clave = clave_buque(nombre)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        guardado = mapa.get(clave)
        filas.append({
            'nombre': guardado[0] if guardado else nombre,
            'dias': guardado[1] if guardado else None,
        })
    return filas


def construir_simulacion(df, hoy=None, mes_txt=None):
    params = leer_dias_viaje()
    tramos = params['colores']
    ahora = timezone.now().astimezone(TZ_CHILE)
    hoy = hoy or ahora.date()
    primer_dia = parse_mes(mes_txt, hoy)
    semanas = Calendar(firstweekday=MONDAY).monthdatescalendar(primer_dia.year, primer_dia.month)
    dias_grid = [dia for semana in semanas for dia in semana]
    vacias = [_celda(d, hoy, primer_dia, tramos=tramos) for d in dias_grid]
    buques_config = listar_buques_config(df, params['dias_buques'])
    base = {
        'celdas': vacias,
        'primer_dia': primer_dia,
        'mes_clave': _clave_mes(primer_dia),
        'mes_anterior': _clave_mes(_sumar_meses(primer_dia, -1)),
        'mes_siguiente': _clave_mes(_sumar_meses(primer_dia, 1)),
        'dias_viaje': params,
        'colores': tramos,
        'buques': buques_config,
        'hay_en_mes': False,
        'meses_con_llegadas': [],
        'filas_usadas': 0,
        'fecha_excel_min': None,
        'fecha_excel_max': None,
    }
    if df is None or getattr(df, 'empty', True):
        return base
    if 'FECHA' not in df.columns or 'PUERTO_DESCARGA' not in df.columns:
        return base

    work = df.copy()
    work['_puerto'] = work['PUERTO_DESCARGA'].map(clasificar_puerto)
    work = work[work['_puerto'].isin((PUERTO_SA, PUERTO_VAP))]
    work['_fecha'] = pd.to_datetime(work['FECHA'], errors='coerce')
    work = work[work['_fecha'].notna()]
    if work.empty:
        return base

    dias_por_puerto = {
        PUERTO_SA: params['dias_san_antonio'],
        PUERTO_VAP: params['dias_valparaiso'],
    }
    mapa_buques = params['dias_buques_norm']
    work['_nave'] = work['NAVE'].fillna('').astype(str).str.strip() if 'NAVE' in work.columns else ''
    work.loc[work['_nave'] == '', '_nave'] = '(sin nave)'
    work['_dias'] = [
        mapa_buques.get(clave_buque(nave), dias_por_puerto[puerto])
        for nave, puerto in zip(work['_nave'], work['_puerto'])
    ]
    work['_salida'] = work['_fecha'].dt.date
    work['_eta_d'] = (
        pd.to_datetime(work['_salida']) + pd.to_timedelta(work['_dias'], unit='D')
    ).dt.date
    if 'NAVIERA' in work.columns:
        work['_naviera'] = work['NAVIERA'].fillna('').astype(str).str.strip()
    else:
        work['_naviera'] = ''
    work['_cajas'] = pd.to_numeric(work['CAJAS'], errors='coerce').fillna(0) if 'CAJAS' in work.columns else 0
    work['_marca'] = work['MARCA'].map(lambda v: _texto(v, '(sin marca)')) if 'MARCA' in work.columns else '(sin marca)'
    work['_consignatario'] = (
        work['CONSIGNATARIO'].map(lambda v: _texto(v, '(sin consignatario)'))
        if 'CONSIGNATARIO' in work.columns else '(sin consignatario)'
    )

    agrupado = (
        work.groupby(
            ['_nave', '_naviera', '_puerto', '_salida', '_eta_d', '_dias', '_marca', '_consignatario'],
            dropna=False,
        )['_cajas']
        .sum()
        .reset_index()
    )
    naves = _como_naves(agrupado.to_dict('records'))
    for nave in naves:
        nave['dias_personalizado'] = clave_buque(nave['nave']) in mapa_buques

    por_dia = {}
    meses_con = set()
    for nave in naves:
        eta = nave['eta']
        meses_con.add(_clave_mes(eta))
        por_dia.setdefault(eta, {PUERTO_SA: [], PUERTO_VAP: []})
        por_dia[eta][nave['puerto']].append(nave)

    hay_en_mes = False
    celdas = []
    for dia in dias_grid:
        grupos = por_dia.get(dia, {PUERTO_SA: [], PUERTO_VAP: []})
        sa = grupos[PUERTO_SA]
        vap = grupos[PUERTO_VAP]
        for indice, nave in enumerate(sa):
            nave['id'] = f'{dia.isoformat()}-sa-{indice}'
            for indice_marca, marca in enumerate(nave['marcas']):
                marca['id'] = f"{nave['id']}-m-{indice_marca}"
        for indice, nave in enumerate(vap):
            nave['id'] = f'{dia.isoformat()}-vap-{indice}'
            for indice_marca, marca in enumerate(nave['marcas']):
                marca['id'] = f"{nave['id']}-m-{indice_marca}"
        celda = _celda(dia, hoy, primer_dia, sa, vap, tramos=tramos)
        if celda['en_mes'] and (celda['total_cajas'] or celda['total_naves']):
            hay_en_mes = True
        celdas.append(celda)

    meses_con_llegadas = []
    for clave in sorted(meses_con):
        anio, mes = (int(p) for p in clave.split('-'))
        meses_con_llegadas.append({
            'clave': clave,
            'fecha': date(anio, mes, 1),
        })

    return {
        'celdas': celdas,
        'primer_dia': primer_dia,
        'mes_clave': _clave_mes(primer_dia),
        'mes_anterior': _clave_mes(_sumar_meses(primer_dia, -1)),
        'mes_siguiente': _clave_mes(_sumar_meses(primer_dia, 1)),
        'dias_viaje': params,
        'colores': tramos,
        'buques': buques_config,
        'hay_en_mes': hay_en_mes,
        'meses_con_llegadas': meses_con_llegadas,
        'filas_usadas': len(naves),
        'fecha_excel_min': _as_date(work['_salida'].min()),
        'fecha_excel_max': _as_date(work['_salida'].max()),
    }
