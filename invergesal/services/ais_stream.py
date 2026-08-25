"""Colector corto de AISStream para escalas a San Antonio y Valparaíso."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from django.conf import settings
from django.utils import timezone

AIS_URL = 'wss://stream.aisstream.io/v0/stream'
TZ_CHILE = pytz.timezone('America/Santiago')

# [lat, lon] esquinas SW y NE, como pide AISStream.
CAJA_SAN_ANTONIO = [[-33.70, -71.75], [-33.48, -71.50]]
CAJA_VALPARAISO = [[-33.12, -71.75], [-32.95, -71.50]]
# Caja amplia del Pacífico/Sudamérica: las cajas chicas de Chile no entregan mensajes.
CAJA_APROXIMACION = [[-56.00, -82.00], [12.00, -34.00]]
BOUNDING_BOXES = [CAJA_APROXIMACION]

PUERTO_COORDS = {
    'SAN ANTONIO': (-33.58, -71.62),
    'VALPARAISO': (-33.04, -71.63),
}

TIPOS_AIS = {
    0: 'No declarado',
    30: 'Pesquero',
    31: 'Remolcador',
    33: 'Dragado',
    34: 'Práctico',
    35: 'Militar',
    36: 'Yate',
    37: 'Recreo',
    40: 'Alta velocidad',
    50: 'Práctico',
    51: 'SAR',
    52: 'Remolcador',
    53: 'Puerto',
    54: 'Antipollution',
    55: 'Patrulla',
    60: 'Pasajeros',
    70: 'Carga',
    71: 'Carga',
    72: 'Carga',
    73: 'Carga',
    74: 'Carga',
    75: 'Carga',
    76: 'Carga',
    77: 'Carga',
    78: 'Carga',
    79: 'Carga',
    80: 'Tanquero',
    81: 'Tanquero',
    82: 'Tanquero',
    83: 'Tanquero',
    84: 'Tanquero',
    85: 'Tanquero',
    86: 'Tanquero',
    87: 'Tanquero',
    88: 'Tanquero',
    89: 'Tanquero',
    90: 'Otro',
}


def get_api_key():
    key = (getattr(settings, 'INVERGESAL_AISSTREAM_API_KEY', '') or '').strip()
    if key:
        return key
    path = Path(getattr(settings, 'INVERGESAL_AISSTREAM_API_KEY_FILE', '') or '')
    if path and path.exists():
        return path.read_text(encoding='utf-8').strip()
    fallback = Path(settings.BASE_DIR) / 'aisstream_api_key.txt'
    if fallback.exists():
        return fallback.read_text(encoding='utf-8').strip()
    return ''


def _sin_acentos(texto):
    texto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in texto if not unicodedata.combining(c)).upper()


def puerto_desde_destino(destino):
    t = _sin_acentos(destino)
    if not t or t in ('-', '????', 'N/A', 'NA'):
        return ''
    if 'SAN ANTONIO' in t or 'CLSAI' in t:
        return 'SAN ANTONIO'
    if 'VALPARAISO' in t or 'CLVAP' in t or ' VALPO' in t or t.endswith('VALPO') or t.startswith('VALPO'):
        return 'VALPARAISO'
    return ''


def _en_caja(lat, lon, caja):
    (lat1, lon1), (lat2, lon2) = caja
    lat_min, lat_max = min(lat1, lat2), max(lat1, lat2)
    lon_min, lon_max = min(lon1, lon2), max(lon1, lon2)
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def puerto_desde_posicion(lat, lon):
    if lat is None or lon is None:
        return '', False
    if _en_caja(lat, lon, CAJA_SAN_ANTONIO):
        return 'SAN ANTONIO', True
    if _en_caja(lat, lon, CAJA_VALPARAISO):
        return 'VALPARAISO', True
    return '', False


def millas_nauticas(lat1, lon1, lat2, lon2):
    r = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_ais_eta(eta_obj, ahora=None):
    if not isinstance(eta_obj, dict):
        return None
    month = int(eta_obj.get('Month') or 0)
    day = int(eta_obj.get('Day') or 0)
    hour = int(eta_obj.get('Hour') or 0)
    minute = int(eta_obj.get('Minute') or 0)
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    ahora = ahora or timezone.now()
    hour = 0 if hour > 23 else hour
    minute = 0 if minute > 59 else minute
    try:
        dt = datetime(ahora.year, month, day, hour, minute, tzinfo=pytz.UTC)
    except ValueError:
        return None
    if dt < ahora - timedelta(days=2):
        try:
            dt = datetime(ahora.year + 1, month, day, hour, minute, tzinfo=pytz.UTC)
        except ValueError:
            return None
    return dt


def eta_por_distancia(lat, lon, puerto, nudos, ahora=None):
    if lat is None or lon is None or not puerto or not nudos or nudos < 1:
        return None
    dest = PUERTO_COORDS.get(puerto)
    if not dest:
        return None
    horas = millas_nauticas(float(lat), float(lon), dest[0], dest[1]) / float(nudos)
    ahora = ahora or timezone.now()
    return ahora + timedelta(hours=horas)


def tipo_texto(codigo):
    if codigo is None:
        return ''
    codigo = int(codigo)
    if codigo in TIPOS_AIS:
        return TIPOS_AIS[codigo]
    base = (codigo // 10) * 10
    return TIPOS_AIS.get(base, 'Otro')


def _mmsi_de(meta, body):
    raw = (meta or {}).get('MMSI') or (body or {}).get('UserID')
    if raw is None:
        return ''
    return str(raw).strip()


def _punto(meta, body):
    lat = (meta or {}).get('latitude')
    lon = (meta or {}).get('longitude')
    if lat is None:
        lat = (body or {}).get('Latitude')
    if lon is None:
        lon = (body or {}).get('Longitude')
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None, None
    if abs(lat) > 90 or abs(lon) > 180:
        return None, None
    return lat, lon


def aplicar_mensaje(acumulado, payload):
    if not isinstance(payload, dict):
        return
    tipo = payload.get('MessageType') or ''
    if tipo == 'SubscriptionConfirmation':
        return
    meta = payload.get('MetaData') or {}
    mensaje = payload.get('Message') or {}
    body = mensaje.get(tipo) or {}
    mmsi = _mmsi_de(meta, body)
    if not mmsi:
        return
    fila = acumulado.setdefault(mmsi, {'mmsi': mmsi})
    nombre = (body.get('Name') or meta.get('ShipName') or '').strip()
    if nombre:
        fila['nombre'] = ' '.join(nombre.split())
    lat, lon = _punto(meta, body)
    if lat is not None:
        fila['lat'] = lat
        fila['lon'] = lon
    if body.get('Cog') is not None:
        fila['rumbo'] = body.get('Cog')
    if body.get('Sog') is not None:
        fila['nudos'] = body.get('Sog')
    if body.get('Type') is not None:
        try:
            fila['tipo_ais'] = int(body.get('Type'))
        except (TypeError, ValueError):
            fila['tipo_ais'] = None
        fila['tipo_texto'] = tipo_texto(fila.get('tipo_ais'))
    dest = body.get('Destination')
    if dest:
        fila['destino_ais'] = str(dest).strip()
        puerto = puerto_desde_destino(dest)
        if puerto:
            fila['puerto_previsto'] = puerto
    eta = parse_ais_eta(body.get('Eta'))
    if eta:
        fila['eta'] = eta
    fila['visto_en'] = timezone.now()


def _es_relevante(fila):
    lat, lon = fila.get('lat'), fila.get('lon')
    puerto_pos, en_puerto = puerto_desde_posicion(lat, lon) if lat is not None else ('', False)
    puerto_dest = fila.get('puerto_previsto') or puerto_desde_destino(fila.get('destino_ais') or '')
    if en_puerto:
        fila['en_zona_puerto'] = True
        fila['puerto_previsto'] = puerto_dest or puerto_pos
        return bool(fila.get('puerto_previsto'))
    fila['en_zona_puerto'] = False
    if puerto_dest:
        fila['puerto_previsto'] = puerto_dest
        return True
    return False


def _completar_eta(fila):
    if fila.get('eta'):
        return
    estimada = eta_por_distancia(
        fila.get('lat'), fila.get('lon'), fila.get('puerto_previsto'), fila.get('nudos'),
    )
    if estimada:
        fila['eta'] = estimada
    elif fila.get('en_zona_puerto'):
        fila['eta'] = timezone.now()


def _decimal(valor, places):
    if valor is None:
        return None
    try:
        return round(Decimal(str(valor)), places)
    except (InvalidOperation, ValueError, TypeError):
        return None


def guardar_escalas(acumulado):
    from invergesal.models import EscalaNave

    guardadas = 0
    for fila in acumulado.values():
        if not _es_relevante(fila):
            continue
        _completar_eta(fila)
        defaults = {
            'nombre': (fila.get('nombre') or '')[:120],
            'tipo_ais': fila.get('tipo_ais'),
            'tipo_texto': (fila.get('tipo_texto') or '')[:40],
            'puerto_previsto': fila['puerto_previsto'],
            'destino_ais': (fila.get('destino_ais') or '')[:80],
            'eta': fila.get('eta'),
            'lat': _decimal(fila.get('lat'), 5),
            'lon': _decimal(fila.get('lon'), 5),
            'rumbo': _decimal(fila.get('rumbo'), 1),
            'nudos': _decimal(fila.get('nudos'), 1),
            'en_zona_puerto': bool(fila.get('en_zona_puerto')),
            'visto_en': fila.get('visto_en') or timezone.now(),
        }
        EscalaNave.objects.update_or_create(mmsi=fila['mmsi'], defaults=defaults)
        guardadas += 1
    return guardadas


def recolectar_ais(segundos=None):
    """Abre AISStream unos segundos, persiste escalas y cierra (apto para cron)."""
    try:
        from websocket import WebSocketApp
    except ImportError:
        return 0, 'Falta el paquete websocket-client. Instálalo con pip.'

    api_key = get_api_key()
    if not api_key:
        return 0, (
            'Falta la API key de AISStream. Crea una cuenta gratis en aisstream.io '
            'y deja la clave en aisstream_api_key.txt (junto a manage.py) '
            'o en INVERGESAL_AISSTREAM_API_KEY.'
        )

    segundos = int(segundos or getattr(settings, 'INVERGESAL_AIS_LISTEN_SECONDS', 90) or 90)
    segundos = max(20, min(segundos, 180))
    acumulado = {}
    error = {'msg': ''}

    def on_message(ws, message):
        try:
            aplicar_mensaje(acumulado, json.loads(message))
        except Exception:
            pass

    def on_open(ws):
        ws.send(json.dumps({
            'APIKey': api_key,
            'BoundingBoxes': BOUNDING_BOXES,
            'FilterMessageTypes': ['PositionReport', 'ShipStaticData'],
        }))

    def on_error(ws, err):
        error['msg'] = str(err)

    ws = WebSocketApp(
        AIS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )

    def cerrar():
        time.sleep(segundos)
        try:
            ws.close()
        except Exception:
            pass

    threading.Thread(target=cerrar, daemon=True).start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    if error['msg'] and not acumulado:
        return 0, f'No se pudo conectar a AISStream: {error["msg"]}'
    n = guardar_escalas(acumulado)
    oidas = len(acumulado)
    if n:
        return n, (
            f'Se actualizaron {n} nave(s) con destino o presencia en San Antonio / Valparaíso '
            f'(se oyeron {oidas} en la zona).'
        )
    if oidas:
        return 0, (
            f'AIS conectó y se oyeron {oidas} nave(s) en Sudamérica, pero ninguna declaraba '
            f'San Antonio o Valparaíso ni estaba en la zona de esos puertos en esta pasada. '
            f'La cobertura AIS en Chile es irregular; vuelve a consultar más tarde si lo necesitas.'
        )
    return 0, 'AIS conectó, pero no llegaron posiciones en esta pasada. Reintenta.'


def construir_calendario(hoy=None):
    from invergesal.models import EscalaNave

    ahora = timezone.now().astimezone(TZ_CHILE)
    hoy = hoy or ahora.date()
    dias = [hoy + timedelta(days=i) for i in range(7)]
    corte = ahora - timedelta(hours=36)
    naves = list(EscalaNave.objects.filter(visto_en__gte=corte))
    por_dia = {d: {'SAN ANTONIO': [], 'VALPARAISO': []} for d in dias}

    for nave in naves:
        eta = nave.eta.astimezone(TZ_CHILE) if nave.eta else ahora
        dia = eta.date()
        if dia < hoy:
            dia = hoy
        if dia not in por_dia:
            continue
        por_dia[dia][nave.puerto_previsto].append(nave)

    celdas = []
    for dia in dias:
        sa = sorted(por_dia[dia]['SAN ANTONIO'], key=lambda n: (n.eta or ahora, n.nombre or n.mmsi))
        vap = sorted(por_dia[dia]['VALPARAISO'], key=lambda n: (n.eta or ahora, n.nombre or n.mmsi))
        total = len(sa) + len(vap)
        celdas.append({
            'fecha': dia,
            'san_antonio': sa,
            'valparaiso': vap,
            'total': total,
            'nivel': _nivel_color(total),
        })
    ultima = None
    if naves:
        ultima = max(n.visto_en for n in naves).astimezone(TZ_CHILE)
    return {
        'celdas': celdas,
        'hay_key': bool(get_api_key()),
        'ultima_vista': ultima,
        'total_naves': len(naves),
    }


def _nivel_color(total):
    if total <= 0:
        return 'vacio'
    if total <= 2:
        return 'bajo'
    if total <= 5:
        return 'medio'
    return 'alto'
