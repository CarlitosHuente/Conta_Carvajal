from pathlib import Path
from threading import Lock
import json
import re

from django.conf import settings

DIAS_SAN_ANTONIO_DEFAULT = 10
DIAS_VALPARAISO_DEFAULT = 11
DIAS_MIN = 1
DIAS_MAX = 40

COLORES_DEFAULT = [
    {'hasta': 0, 'color': '#eef3f8'},
    {'hasta': 19999, 'color': '#d1fae5'},
    {'hasta': 49999, 'color': '#fde68a'},
    {'hasta': None, 'color': '#fecaca'},
]

_LOCK = Lock()
_HEX = re.compile(r'^#?[0-9A-Fa-f]{6}$')


def ruta_json():
    configurada = getattr(settings, 'INVERGESAL_PARAMETROS_VIAJE_JSON', None)
    if configurada:
        return Path(configurada)
    return Path(settings.BASE_DIR) / 'invergesal_data' / 'parametros_viaje.json'


def clave_buque(nombre):
    return ' '.join(str(nombre or '').strip().upper().split())


def parse_dias(valor):
    try:
        dias = int(valor)
    except (TypeError, ValueError):
        return None
    if dias < DIAS_MIN or dias > DIAS_MAX:
        return None
    return dias


def parse_hex(valor):
    texto = str(valor or '').strip()
    if not _HEX.fullmatch(texto):
        return None
    return '#' + texto.lstrip('#').lower()


def parse_hasta(valor, permitir_vacio=False):
    texto = str(valor if valor is not None else '').strip()
    if texto == '' or texto.lower() in ('none', 'null'):
        return None if permitir_vacio else False
    try:
        numero = int(str(texto).replace('.', '').replace(',', ''))
    except (TypeError, ValueError):
        return False
    if numero < 0:
        return False
    return numero


def _fmt_cajas(numero):
    return f'{int(numero):,}'.replace(',', '.')


def _etiquetas(tramos):
    prev = None
    salida = []
    for tramo in tramos:
        hasta = tramo['hasta']
        color = tramo['color']
        if hasta == 0:
            etiqueta = '0 cajas'
        elif hasta is None:
            inicio = 1 if prev in (None, 0) else prev + 1
            etiqueta = f'{_fmt_cajas(inicio)} o más'
        else:
            inicio = 1 if prev in (None, 0) else prev + 1
            etiqueta = f'{_fmt_cajas(inicio)}–{_fmt_cajas(hasta)}'
        salida.append({'hasta': hasta, 'color': color, 'etiqueta': etiqueta})
        if hasta is not None:
            prev = hasta
    return salida


def _normalizar_colores(crudo):
    if not isinstance(crudo, list) or len(crudo) < 2:
        return _etiquetas(COLORES_DEFAULT)
    limpios = []
    for i, item in enumerate(crudo):
        if not isinstance(item, dict):
            return _etiquetas(COLORES_DEFAULT)
        color = parse_hex(item.get('color'))
        if not color:
            return _etiquetas(COLORES_DEFAULT)
        es_ultimo = i == len(crudo) - 1
        hasta = parse_hasta(item.get('hasta'), permitir_vacio=es_ultimo)
        if hasta is False:
            return _etiquetas(COLORES_DEFAULT)
        if i == 0 and hasta != 0:
            return _etiquetas(COLORES_DEFAULT)
        if i > 0 and i < len(crudo) - 1 and hasta is None:
            return _etiquetas(COLORES_DEFAULT)
        limpios.append({'hasta': hasta, 'color': color})
    previos = [t['hasta'] for t in limpios[:-1]]
    if previos != sorted(previos) or len(set(previos)) != len(previos):
        return _etiquetas(COLORES_DEFAULT)
    if limpios[-1]['hasta'] is not None and limpios[-1]['hasta'] <= previos[-1]:
        return _etiquetas(COLORES_DEFAULT)
    return _etiquetas(limpios)


def _normalizar_buques(crudo):
    if not isinstance(crudo, dict):
        return {}
    salida = {}
    for nombre, valor in crudo.items():
        clave = clave_buque(nombre)
        dias = parse_dias(valor)
        if not clave or dias is None:
            continue
        salida[str(nombre).strip()] = dias
    return salida


def _defaults():
    return {
        'dias_san_antonio': DIAS_SAN_ANTONIO_DEFAULT,
        'dias_valparaiso': DIAS_VALPARAISO_DEFAULT,
        'dias_buques': {},
        'colores': [dict(item) for item in COLORES_DEFAULT],
    }


def _leer_crudo():
    ruta = ruta_json()
    if not ruta.exists():
        return _defaults()
    try:
        data = json.loads(ruta.read_text(encoding='utf-8') or '{}')
    except (OSError, json.JSONDecodeError):
        return _defaults()
    if not isinstance(data, dict):
        return _defaults()
    return data


def _escribir_crudo(data):
    ruta = ruta_json()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(ruta)


def leer_dias_viaje():
    crudo = _leer_crudo()
    sa = parse_dias(crudo.get('dias_san_antonio')) or DIAS_SAN_ANTONIO_DEFAULT
    vap = parse_dias(crudo.get('dias_valparaiso')) or DIAS_VALPARAISO_DEFAULT
    buques = _normalizar_buques(crudo.get('dias_buques'))
    return {
        'dias_san_antonio': sa,
        'dias_valparaiso': vap,
        'dias_buques': buques,
        'dias_buques_norm': {clave_buque(nombre): dias for nombre, dias in buques.items()},
        'colores': _normalizar_colores(crudo.get('colores')),
    }


def _parsear_colores_post(hastas, colores):
    if not hastas or not colores or len(hastas) != len(colores):
        return None, 'Los tramos de color no son válidos.'
    if len(hastas) < 2:
        return None, 'Debe haber al menos el tramo 0 y el tramo final.'
    limpios = []
    for i, (hasta_raw, color_raw) in enumerate(zip(hastas, colores)):
        color = parse_hex(color_raw)
        if not color:
            return None, 'Hay un color inválido.'
        es_ultimo = i == len(hastas) - 1
        hasta = parse_hasta(hasta_raw, permitir_vacio=es_ultimo)
        if hasta is False:
            return None, 'Los topes de cajas deben ser números enteros.'
        if i == 0 and hasta != 0:
            return None, 'El primer tramo debe ser 0 cajas.'
        if not es_ultimo and hasta is None:
            return None, 'Solo el último tramo puede quedar abierto (o más).'
        limpios.append({'hasta': hasta, 'color': color})
    previos = [t['hasta'] for t in limpios[:-1]]
    if previos != sorted(previos) or len(set(previos)) != len(previos):
        return None, 'Los topes de cajas deben ir de menor a mayor, sin repetir.'
    if limpios[-1]['hasta'] is not None and limpios[-1]['hasta'] <= previos[-1]:
        return None, 'El último tope debe ser mayor que el anterior.'
    return limpios, None


def _parsear_buques_post(nombres, dias_valores):
    salida = {}
    for nombre, dias_raw in zip(nombres, dias_valores):
        nombre = str(nombre or '').strip()
        if not nombre:
            continue
        texto = str(dias_raw or '').strip()
        if texto == '':
            continue
        dias = parse_dias(texto)
        if dias is None:
            return None, f'Los días de "{nombre}" deben ser un número entre {DIAS_MIN} y {DIAS_MAX}.'
        salida[nombre] = dias
    return salida, None


def guardar_parametros_viaje(dias_san_antonio, dias_valparaiso, nombres_buques, dias_buques, hastas, colores):
    sa = parse_dias(dias_san_antonio)
    vap = parse_dias(dias_valparaiso)
    if sa is None or vap is None:
        return False, f'Los días de viaje deben ser un número entre {DIAS_MIN} y {DIAS_MAX}.'
    buques, error = _parsear_buques_post(nombres_buques, dias_buques)
    if error:
        return False, error
    tramos, error = _parsear_colores_post(hastas, colores)
    if error:
        return False, error
    with _LOCK:
        _escribir_crudo({
            'dias_san_antonio': sa,
            'dias_valparaiso': vap,
            'dias_buques': buques,
            'colores': tramos,
        })
    return True, 'Parámetros de proyección guardados.'


def color_para_cajas(cajas, tramos=None):
    tramos = tramos or leer_dias_viaje()['colores']
    cantidad = max(int(cajas or 0), 0)
    elegido = tramos[-1]
    for tramo in tramos:
        hasta = tramo['hasta']
        if hasta is None or cantidad <= hasta:
            elegido = tramo
            break
    color = elegido['color']
    return color, _es_oscuro(color)


def _es_oscuro(hex_color):
    texto = (hex_color or '').lstrip('#')
    if len(texto) != 6:
        return False
    rojo = int(texto[0:2], 16)
    verde = int(texto[2:4], 16)
    azul = int(texto[4:6], 16)
    return ((rojo * 299) + (verde * 587) + (azul * 114)) / 1000 < 140
