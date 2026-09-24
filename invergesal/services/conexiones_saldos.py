from pathlib import Path
from threading import Lock
from urllib.parse import urlparse
import json

from django.conf import settings

_LOCK = Lock()

URL_BANAGREEN_DEFAULT = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vTebUVntcwTrub69mvm-Kvstg2tH0A8hQN1tRcXUaonP8Bh3xt7DjQyTxOGDI_Z7Q/'
    'pub?gid=780129547&single=true&output=csv'
)
URL_CORPROBAN_DEFAULT = (
    'https://docs.google.com/spreadsheets/d/e/'
    '2PACX-1vQxsc3moRN_zu-NmIp236fgyFWv3lSijASotWh1OAtkNkh0y-gzZt8q05_6bdH_Dg/'
    'pub?gid=598736898&single=true&output=csv'
)
DEFAULTS = {
    'banagreen': URL_BANAGREEN_DEFAULT,
    'corproban': URL_CORPROBAN_DEFAULT,
}


def ruta_json():
    configurada = getattr(settings, 'INVERGESAL_CONEXIONES_SALDOS_JSON', None)
    if configurada:
        return Path(configurada)
    return Path(settings.BASE_DIR) / 'invergesal_data' / 'conexiones_saldos.json'


def _archivo_vacio():
    return dict(DEFAULTS)


def _leer_crudo():
    ruta = ruta_json()
    if not ruta.exists():
        return _archivo_vacio()
    try:
        data = json.loads(ruta.read_text(encoding='utf-8') or '{}')
    except (OSError, json.JSONDecodeError):
        return _archivo_vacio()
    if not isinstance(data, dict):
        return _archivo_vacio()
    return data


def _escribir_crudo(data):
    ruta = ruta_json()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(ruta)


def normalizar_url(valor):
    return str(valor or '').strip()


def url_valida(valor):
    texto = normalizar_url(valor)
    parsed = urlparse(texto)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return False
    return True


def url_csv(fuente):
    clave = str(fuente or '').strip().lower()
    data = _leer_crudo()
    guardada = normalizar_url(data.get(clave))
    if url_valida(guardada):
        return guardada
    setting = {
        'banagreen': 'INVERGESAL_SALDOS_ECUADOR_CSV_URL',
        'corproban': 'INVERGESAL_SALDOS_ECUADOR_CORPROBAN_CSV_URL',
    }.get(clave)
    if setting:
        desde_settings = normalizar_url(getattr(settings, setting, '') or '')
        if url_valida(desde_settings):
            return desde_settings
    return DEFAULTS.get(clave) or DEFAULTS['banagreen']


def urls_actuales():
    return {
        'banagreen': url_csv('banagreen'),
        'corproban': url_csv('corproban'),
    }


def serializar_conexiones():
    urls = urls_actuales()
    return {
        'banagreen': urls['banagreen'],
        'corproban': urls['corproban'],
    }


def guardar_urls(banagreen, corproban):
    banagreen = normalizar_url(banagreen)
    corproban = normalizar_url(corproban)
    if not url_valida(banagreen):
        return False, 'La URL de BANAGREEN no es válida. Debe empezar con http:// o https://.'
    if not url_valida(corproban):
        return False, 'La URL de CORPROBAN no es válida. Debe empezar con http:// o https://.'
    with _LOCK:
        _escribir_crudo({
            'banagreen': banagreen,
            'corproban': corproban,
        })
    return True, 'Conexiones guardadas.'
