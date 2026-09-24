import csv
import io
import logging
from datetime import datetime

import pytz
import requests
from django.conf import settings
from django.core.cache import cache

from invergesal.services.conexiones_saldos import url_csv
from invergesal.services.parametros_gastos import monto_gasto

logger = logging.getLogger(__name__)

CSV_URL_BANAGREEN = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vTebUVntcwTrub69mvm-Kvstg2tH0A8hQN1tRcXUaonP8Bh3xt7DjQyTxOGDI_Z7Q/'
    'pub?gid=780129547&single=true&output=csv'
)
CSV_URL_CORPROBAN = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vQxsc3moRN_zu-NmIp236fgyFWv3lSijASotWh1OAtkNkh0y-gzZt8q05_6bdH_Dg/'
    'pub?gid=598736898&single=true&output=csv'
)
FUENTE_DEFAULT = 'banagreen'
FUENTES = {
    'banagreen': {
        'id': 'banagreen',
        'nombre': 'BANAGREEN',
        'setting': 'INVERGESAL_SALDOS_ECUADOR_CSV_URL',
        'url_default': CSV_URL_BANAGREEN,
    },
    'corproban': {
        'id': 'corproban',
        'nombre': 'CORPROBAN',
        'setting': 'INVERGESAL_SALDOS_ECUADOR_CORPROBAN_CSV_URL',
        'url_default': CSV_URL_CORPROBAN,
    },
}
CACHE_TIMEOUT = 60 * 60 * 6
FETCH_TIMEOUT_DEFAULT = 45

_NAVE_OMITIR_EXACTAS = {
    'NO EMBARCA',
    'NO SE CARGA',
}
_NAVE_OMITIR_SUBCADENA = (
    'DESCUENTO',
    'NO EMBARCA',
    'NO SE CARGA',
    'IMPORTACION',
)


def normalizar_fuente(valor):
    clave = str(valor or '').strip().lower()
    return clave if clave in FUENTES else FUENTE_DEFAULT


def lista_fuentes():
    return [dict(item) for item in FUENTES.values()]


def pestanas_saldos():
    return lista_fuentes() + [{'id': 'liquidacion', 'nombre': 'Liquidacion'}]


def es_fuente_csv(valor):
    return str(valor or '').strip().lower() in FUENTES


def normalizar_pestana(valor):
    clave = str(valor or '').strip().lower()
    if clave == 'liquidacion':
        return 'liquidacion'
    return clave if clave in FUENTES else FUENTE_DEFAULT


def _cache_key_filas(fuente):
    return f'invergesal_saldos_ecuador_filas_{normalizar_fuente(fuente)}'


def _cache_key_info(fuente):
    return f'invergesal_saldos_ecuador_info_{normalizar_fuente(fuente)}'


def get_csv_url(fuente=FUENTE_DEFAULT):
    return url_csv(normalizar_fuente(fuente))


def get_fetch_timeout():
    return int(getattr(settings, 'INVERGESAL_SALDOS_ECUADOR_CSV_TIMEOUT', FETCH_TIMEOUT_DEFAULT))


def parse_numero_chileno(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, bool):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(' ', '').replace('$', '')
    if not texto or texto.upper() in ('NONE', 'NAN', '-', 'NA'):
        return 0.0
    try:
        if ',' in texto:
            return float(texto.replace('.', '').replace(',', '.'))
        if texto.count('.') > 1:
            return float(texto.replace('.', ''))
        if '.' in texto:
            decimales = texto.split('.')[-1]
            if len(decimales) == 3 and decimales.isdigit():
                return float(texto.replace('.', ''))
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


def _norm_header(celda):
    texto = str(celda or '').strip().upper()
    texto = texto.replace('º', '').replace('°', '')
    return ' '.join(texto.split())


def _parse_anio(valor):
    texto = str(valor or '').strip()
    if not texto:
        return None
    try:
        anio = int(float(texto.replace(',', '.')))
    except (TypeError, ValueError):
        return None
    if 2000 <= anio <= 2100:
        return anio
    return None


def _parse_semana(valor):
    texto = str(valor or '').strip()
    if not texto:
        return None
    try:
        semana = int(float(texto.replace(',', '.')))
    except (TypeError, ValueError):
        return None
    if 0 <= semana <= 53:
        return semana
    return None


def _parse_di(valor):
    """Normaliza DI para todas las fuentes (BANAGREEN, CORPROBAN y Liquidación).

    En la planilla a veces viene con miles chilenos (198.575). En pantalla y en
    agrupación siempre queda sin separador: 198575.
    """
    texto = str(valor or '').strip().replace(' ', '')
    if not texto:
        return ''
    numero = parse_numero_chileno(texto)
    if numero <= 0:
        return ''
    entero = int(round(numero))
    if entero <= 0:
        return ''
    return str(entero)


def _nave_valida(nave):
    texto = (nave or '').strip()
    if not texto:
        return False
    mayus = texto.upper()
    if mayus in _NAVE_OMITIR_EXACTAS:
        return False
    if mayus.startswith('SALDO') or mayus.startswith('ABONO'):
        return False
    for fragmento in _NAVE_OMITIR_SUBCADENA:
        if fragmento in mayus:
            return False
    return True


def _indices_columnas(encabezado):
    normas = [_norm_header(c) for c in encabezado]
    requeridas = {
        'sem': 'SEM',
        'ano': 'ANO',
        'nave': 'NAVES',
        'naviera': 'NAVIERA',
        'bl': 'N B/L',
        'contenedor': 'CONTENEDORES',
        'cajas': 'CAJAS',
        'valor_unit': 'VALOR UNIT',
        'total': 'TOTAL',
        'di': 'DI',
    }
    aliases = {
        'ANO': ('ANO', 'AÑO', 'ANIO'),
        'N B/L': ('N B/L', 'N° B/L', 'Nº B/L', 'NO B/L', 'N BL'),
    }
    indices = {}
    usados = set()
    for clave, nombre in requeridas.items():
        candidatos = aliases.get(nombre, (nombre,))
        hallado = None
        for i, norma in enumerate(normas):
            if i in usados:
                continue
            if norma in candidatos or norma == nombre:
                hallado = i
                break
        if hallado is None:
            return None
        indices[clave] = hallado
        usados.add(hallado)
    return indices


_EXTRA_NOMBRES = {
    'IVA': 'iva',
    'GASTOS': 'gastos',
    'FLETE MAR': 'flete_mar',
    'FOB FACTURA': 'fob_factura',
    'COMPLEMENTO US$': 'complemento_usd',
    'TOTAL NAVE': 'total_nave',
    'ABONOS DESGLOS X NAVE': 'abonos_desglos',
    'ABONOS DESGLOS': 'abonos_desglos',
    'T/C PAGADO': 'tc_pagado',
    'TC PAGADO': 'tc_pagado',
    'T/C DI': 'tc_di',
    'TOT FOB DI US$': 'tot_fob_di_usd',
    'TOT COMPL NAVE US$': 'tot_compl_nave_usd',
    'TOT FOB DI $': 'tot_fob_di_pesos',
    'TOT COMPL NAVE $': 'tot_compl_nave_pesos',
    'T/C ADUANERO': 'tc_aduanero',
    'FOB ADUANERO EN PESOS': 'fob_aduanero_pesos',
    'T/C SEMANA PARA (LIQUID)': 'tc_semana_liquid',
    'FACT SERV FRIO': 'fact_serv_frio',
    'FACT SERVICIO FRIO': 'fact_serv_frio',
    'FLETE MARITIMO': 'flete_maritimo_pesos',
    'GASTO ADUANA': 'gasto_aduana',
    'FACTURA': 'factura',
}


def _indices_extras(encabezado, indices_req):
    usados = set(indices_req.values())
    normas = [_norm_header(c) for c in encabezado]
    extras = {}
    tc_count = 0
    for i, norma in enumerate(normas):
        if i in usados:
            continue
        if norma == 'T/C':
            tc_count += 1
            extras['tc_fruta' if tc_count == 1 else 'tc_flete'] = i
            continue
        clave = _EXTRA_NOMBRES.get(norma)
        if clave and clave not in extras:
            extras[clave] = i
            continue
        if 'abonos_desglos' not in extras and 'ABONOS DESGLOS' in norma:
            extras['abonos_desglos'] = i
            continue
        if 'tc_pagado' not in extras and 'PAGADO' in norma and norma.startswith('T/C'):
            extras['tc_pagado'] = i
    return extras


def parsear_csv(texto):
    """Devuelve filas del bloque moderno (SEM, ANO, ..., DI)."""
    lector = csv.reader(io.StringIO(texto or ''))
    filas_csv = list(lector)
    header_idx = None
    indices = None
    extras_idx = None
    for i, fila in enumerate(filas_csv):
        celdas = [_norm_header(c) for c in fila]
        if not celdas or celdas[0] != 'SEM':
            continue
        if len(celdas) < 2 or celdas[1] not in ('ANO', 'AÑO', 'ANIO'):
            continue
        hallados = _indices_columnas(fila)
        if hallados:
            header_idx = i
            indices = hallados
            extras_idx = _indices_extras(fila, hallados)
    if header_idx is None or indices is None:
        raise ValueError('No se encontró el bloque SEM / AÑO / DI en el CSV publicado.')
    extras_idx = extras_idx or {}

    filas = []
    for fila in filas_csv[header_idx + 1:]:
        if not fila:
            continue
        primera = _norm_header(fila[0] if fila else '')
        if primera == 'SEM':
            continue
        def _celda(clave):
            idx = indices[clave]
            return fila[idx].strip() if idx < len(fila) else ''

        di = _parse_di(_celda('di'))
        if not di:
            continue
        anio = _parse_anio(_celda('ano'))
        if anio is None:
            continue
        semana = _parse_semana(_celda('sem'))
        if semana is None:
            continue
        nave = _celda('nave')
        if not _nave_valida(nave):
            continue
        contenedor = _celda('contenedor')
        cajas = parse_numero_chileno(_celda('cajas'))
        if not contenedor and cajas <= 0:
            continue
        registro = {
            'sem': semana,
            'ano': anio,
            'nave': nave.strip(),
            'naviera': _celda('naviera'),
            'bl': _celda('bl'),
            'contenedor': contenedor,
            'cajas': cajas,
            'valor_unit': parse_numero_chileno(_celda('valor_unit')),
            'total': parse_numero_chileno(_celda('total')),
            'di': di,
        }
        for clave, idx in extras_idx.items():
            crudo = fila[idx].strip() if idx < len(fila) else ''
            if clave in ('factura', 'fact_serv_frio'):
                registro[clave] = crudo
            else:
                registro[clave] = parse_numero_chileno(crudo)
        filas.append(registro)
    return filas


def _unicos(valores):
    vistos = []
    for valor in valores:
        texto = (valor or '').strip()
        if texto and texto not in vistos:
            vistos.append(texto)
    return vistos


def anios_disponibles(filas):
    return sorted({fila['ano'] for fila in filas}, reverse=True)


def agrupar_por_di(filas, anio):
    grupos = {}
    for fila in filas:
        if fila.get('ano') != anio:
            continue
        grupos.setdefault(fila['di'], []).append(fila)

    resumen = []
    for di, items in grupos.items():
        items_ordenados = sorted(
            items,
            key=lambda f: (-(f.get('sem') or 0), f.get('nave') or '', f.get('contenedor') or ''),
        )
        semanas = sorted({item['sem'] for item in items_ordenados if item.get('sem') is not None})
        naves = _unicos(item['nave'] for item in items_ordenados)
        navieras = _unicos(item['naviera'] for item in items_ordenados)
        resumen.append({
            'di': di,
            'semanas': semanas,
            'semanas_txt': ', '.join(str(s) for s in semanas),
            'naves': naves,
            'naves_txt': ', '.join(naves),
            'navieras': navieras,
            'navieras_txt': ', '.join(navieras),
            'num_contenedores': len(items_ordenados),
            'cajas': sum(item['cajas'] for item in items_ordenados),
            'total': round(sum(item['total'] for item in items_ordenados), 2),
            'semana_max': max(semanas) if semanas else 0,
            'filas': items_ordenados,
        })
    resumen.sort(
        key=lambda g: (
            -(g['semana_max'] or 0),
            -(int(g['di']) if str(g['di']).isdigit() else 0),
        )
    )
    return resumen


PRECIO_CONT_REF = 12.0
_TC_MIN, _TC_MAX = 700.0, 1300.0


def codigo_liquidacion(anio, semana):
    return f'{int(anio) % 100:02d}{int(semana):02d}'


def semanas_disponibles(filas, anio):
    return sorted({fila['sem'] for fila in filas if fila.get('ano') == anio}, reverse=True)


def _filas_semana(filas, anio, semana):
    return [fila for fila in filas if fila.get('ano') == anio and fila.get('sem') == semana]


def _vunit_clave(valor):
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _linea_embarque(proveedor, filas, vunit=None):
    cajas = sum(f['cajas'] for f in filas)
    valor = round(sum(f['total'] for f in filas), 2)
    if vunit is None:
        vunit = round(valor / cajas, 2) if cajas else 0.0
    return {
        'proveedor': proveedor,
        'cont': len(filas),
        'cajas': cajas,
        'vunit': vunit,
        'valor': valor,
        'alerta_cont': False,
    }


def _lineas_embarque_marca(nombre, filas):
    """Una fila por V/UN: mismo precio se suma; precios distintos no se promedian."""
    grupos = {}
    for fila in filas:
        grupos.setdefault(_vunit_clave(fila.get('valor_unit')), []).append(fila)
    if not grupos:
        return [
            _linea_embarque(f'{nombre} CONT', []),
            _linea_embarque(f'{nombre} SPOT', []),
        ]
    v_cont = min(grupos, key=lambda v: (abs(v - PRECIO_CONT_REF), -len(grupos[v])))
    lineas = [_linea_embarque(f'{nombre} CONT', grupos[v_cont], vunit=v_cont)]
    spots = sorted((v for v in grupos if v != v_cont), key=lambda v: (-len(grupos[v]), v))
    if not spots:
        lineas.append(_linea_embarque(f'{nombre} SPOT', []))
        return lineas
    for vunit in spots:
        lineas.append(_linea_embarque(f'{nombre} SPOT', grupos[vunit], vunit=vunit))
    return lineas


def _valor_unico_por_di(filas, campo):
    por_di = {}
    for fila in filas:
        valor = fila.get(campo)
        if isinstance(valor, str):
            if valor.strip():
                por_di[fila['di']] = valor.strip()
            continue
        if valor:
            por_di[fila['di']] = valor
    if not por_di:
        return 0.0 if campo not in ('factura', 'fact_serv_frio') else ''
    if campo in ('factura', 'fact_serv_frio'):
        return ', '.join(str(v) for v in por_di.values())
    return sum(por_di.values())


def _tc_valido(valor):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return None
    if _TC_MIN <= numero <= _TC_MAX:
        return numero
    return None


def _tramos_csv_semana(filas, marca):
    tramos = []
    vistos = set()
    for fila in filas:
        usd = fila.get('abonos_desglos') or 0
        tc = _tc_valido(fila.get('tc_pagado'))
        if not usd or tc is None:
            continue
        usd = round(float(usd), 2)
        nave = (fila.get('nave') or '').strip()
        clave = (marca, nave, usd, tc)
        if clave in vistos:
            continue
        vistos.add(clave)
        tramos.append({
            'marca': marca,
            'nave': nave,
            'usd': usd,
            'tc': tc,
            'origen': 'csv',
        })
    return tramos


def _numero_extra(valor):
    if valor in (None, ''):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    return parse_numero_chileno(valor)


def _tramos_extra_limpios(extras):
    limpios = []
    for item in extras or []:
        try:
            usd = _numero_extra(item.get('usd'))
            tc = _numero_extra(item.get('tc'))
        except (TypeError, ValueError, AttributeError):
            continue
        if usd == 0 and tc == 0:
            continue
        limpios.append({
            'marca': (item.get('marca') or 'AJUSTE').strip() or 'AJUSTE',
            'nave': (item.get('nave') or '').strip(),
            'usd': round(usd, 2),
            'tc': round(tc, 2),
            'origen': 'extra',
        })
    return limpios


def calcular_tc_embarque(tramos, total_embarque):
    numerador = sum((t.get('usd') or 0) * (t.get('tc') or 0) for t in tramos)
    usd_cubierto = round(sum(t.get('usd') or 0 for t in tramos), 2)
    tc = round(numerador / total_embarque, 2) if total_embarque else None
    return {
        'tc': tc,
        'numerador': round(numerador, 2),
        'usd_cubierto': usd_cubierto,
        'usd_falta': round((total_embarque or 0) - usd_cubierto, 2),
        'embarque': total_embarque,
        'fob': round(numerador, 0) if numerador else None,
    }


def construir_liquidacion(filas_por_marca, anio, semana, extras=None, tarifas=None):
    """Arma EMBARQUE + GASTOS combinando BANAGREEN y CORPROBAN de una semana."""
    orden_marcas = [
        ('banagreen', 'BANAGREEN'),
        ('corproban', 'CORPROBAN'),
    ]
    lineas = []
    todas = []
    tramos_csv = []
    for clave, nombre in orden_marcas:
        filas = _filas_semana(filas_por_marca.get(clave) or [], anio, semana)
        todas.extend(filas)
        tramos_csv.extend(_tramos_csv_semana(filas, nombre))
        lineas.extend(_lineas_embarque_marca(nombre, filas))

    cajas = sum(l['cajas'] for l in lineas)
    valor = round(sum(l['valor'] for l in lineas), 2)
    subtotal = {
        'proveedor': 'SUB TOTAL',
        'cont': sum(l['cont'] for l in lineas),
        'cajas': cajas,
        'vunit': round(valor / cajas, 2) if cajas else 0.0,
        'valor': valor,
    }

    tc_flete = None
    for fila in todas:
        tc = _tc_valido(fila.get('tc_flete') or fila.get('tc_fruta'))
        if tc is not None:
            tc_flete = tc
            break
    flete_usd = _valor_unico_por_di(todas, 'flete_mar')
    f_naviero = round(flete_usd * tc_flete, 0) if tc_flete else 0.0

    tramos_extra = _tramos_extra_limpios(extras)
    tc_calc = calcular_tc_embarque(tramos_csv + tramos_extra, valor)
    tc_fob = tc_calc['tc']
    fob = tc_calc['fob']
    iva = round(_valor_unico_por_di(todas, 'iva'), 0)
    prov_aduana = round(_valor_unico_por_di(todas, 'gastos'), 0)
    tarifas = tarifas or {}
    f_terres = monto_gasto(tarifas.get('flete_terrestre'), subtotal['cont'])
    ser_frio = monto_gasto(tarifas.get('servicio_frio'), subtotal['cajas'])
    despacho = monto_gasto(tarifas.get('despacho'), subtotal['cajas'])

    gastos_tc = [
        {'concepto': 'FOB', 'valor': fob or None, 'tc': tc_fob, 'tc_alerta': True, 'es_tc_fob': True},
        {'concepto': 'F.NAVIERO', 'valor': f_naviero or None, 'tc': tc_flete, 'tc_alerta': False, 'es_tc_fob': False},
        {'concepto': 'IVA INTERNACION', 'valor': iva or None, 'tc': None, 'tc_alerta': False, 'es_tc_fob': False},
        {'concepto': 'PROV ADUANA', 'valor': prov_aduana or None, 'tc': None, 'tc_alerta': False, 'es_tc_fob': False},
    ]
    gastos_fact = [
        {'concepto': 'F.TERRES', 'valor': f_terres, 'factura': ''},
        {'concepto': 'DIF. IVA INT', 'valor': None, 'factura': ''},
        {'concepto': 'DIF. AGENCIA', 'valor': None, 'factura': ''},
        {'concepto': 'DUPOL', 'valor': None, 'factura': ''},
        {'concepto': 'SER FRIO', 'valor': ser_frio, 'factura': _valor_unico_por_di(todas, 'fact_serv_frio')},
        {'concepto': 'DESPACHO', 'valor': despacho, 'factura': ''},
        {'concepto': 'COMISION', 'valor': None, 'factura': ''},
        {'concepto': 'ENCHUFAJE', 'valor': None, 'factura': ''},
    ]

    return {
        'codigo': codigo_liquidacion(anio, semana),
        'anio': anio,
        'semana': semana,
        'embarque': lineas,
        'subtotal': subtotal,
        'gastos_tc': gastos_tc,
        'gastos_fact': gastos_fact,
        'tiene_datos': bool(todas),
        'tc_panel': {
            'codigo': codigo_liquidacion(anio, semana),
            'anio': anio,
            'semana': semana,
            'embarque': valor,
            'tramos_csv': tramos_csv,
            'tramos_extra': tramos_extra,
            'numerador': tc_calc['numerador'],
            'usd_cubierto': tc_calc['usd_cubierto'],
            'usd_falta': tc_calc['usd_falta'],
            'tc': tc_fob,
            'fob': fob,
        },
    }


def descargar_csv(fuente=FUENTE_DEFAULT):
    url = get_csv_url(fuente)
    timeout = get_fetch_timeout()
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; ContaCarvajal/SaldosEcuador)',
        'Accept': 'text/csv,text/plain,*/*',
    }
    ultimo_error = None
    sesion = requests.Session()
    sesion.trust_env = False
    for intento in range(2):
        try:
            respuesta = sesion.get(url, timeout=timeout, headers=headers)
            respuesta.raise_for_status()
            respuesta.encoding = respuesta.apparent_encoding or 'utf-8'
            texto = respuesta.text
            if not texto or not texto.strip():
                raise ValueError('El CSV publicado está vacío.')
            return texto
        except Exception as exc:
            ultimo_error = exc
            logger.warning('No se pudo bajar Saldos Ecuador (intento %s): %s', intento + 1, exc)
    raise ultimo_error


def _ahora_local():
    return datetime.now(pytz.timezone('America/Santiago')).strftime('%d/%m/%Y %H:%M:%S')


def cargar_saldos_ecuador(fuente=FUENTE_DEFAULT, force_refresh=False):
    fuente = normalizar_fuente(fuente)
    key_filas = _cache_key_filas(fuente)
    key_info = _cache_key_info(fuente)
    if not force_refresh:
        filas = cache.get(key_filas)
        if filas is not None:
            return True, '', filas
    try:
        texto = descargar_csv(fuente)
        filas = parsear_csv(texto)
    except Exception as exc:
        logger.exception('Error cargando Saldos Ecuador (%s)', fuente)
        filas_cache = cache.get(key_filas)
        if filas_cache is not None:
            return True, f'No se pudo actualizar; se muestran datos en caché. ({exc})', filas_cache
        return False, f'No se pudo leer el CSV publicado: {exc}', []

    cache.set(key_filas, filas, CACHE_TIMEOUT)
    cache.set(key_info, {
        'modifiedTimeLocal': _ahora_local(),
        'filas': len(filas),
        'fuente': fuente,
    }, CACHE_TIMEOUT)
    return True, f'Se cargaron {len(filas)} filas de embarque.', filas


def cargar_todas_las_marcas(force_refresh=False):
    datos = {}
    mensajes = []
    ok = True
    for clave, meta in FUENTES.items():
        success, message, filas = cargar_saldos_ecuador(clave, force_refresh=force_refresh)
        datos[clave] = filas
        if not success:
            ok = False
            mensajes.append(f'{meta["nombre"]}: {message}')
        elif message:
            mensajes.append(f'{meta["nombre"]}: {message}')
    return ok, ' '.join(mensajes), datos


def get_saldos_cache_info(fuente=FUENTE_DEFAULT):
    return cache.get(_cache_key_info(fuente)) or {}


def clear_saldos_cache(fuente=None):
    if fuente:
        cache.delete(_cache_key_filas(fuente))
        cache.delete(_cache_key_info(fuente))
        return
    for clave in FUENTES:
        cache.delete(_cache_key_filas(clave))
        cache.delete(_cache_key_info(clave))
