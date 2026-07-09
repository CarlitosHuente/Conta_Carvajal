import logging
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import cache

from rrhh.models import IndicadorEconomico

logger = logging.getLogger(__name__)

CACHE_KEY_INDICADORES = 'ind_api_global_v1'
CACHE_TTL_INDICADORES = 3600  # 1 hora


def _fmt_uf(valor):
    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_utm(valor):
    return f"{float(valor):,.0f}".replace(",", ".")


def _indicador_db(mes, ano):
    try:
        return IndicadorEconomico.objects.get(mes=mes, ano=ano)
    except IndicadorEconomico.DoesNotExist:
        return IndicadorEconomico.objects.order_by('-ano', '-mes').first()


def _cargar_desde_db(data, hoy):
    ind = _indicador_db(hoy.month, hoy.year)
    if not ind:
        return data, None
    data['uf'] = _fmt_uf(ind.uf)
    data['utm'] = _fmt_utm(ind.utm)
    data['uf_mensual'] = _fmt_uf(ind.uf)
    data['fecha'] = f'{hoy.year}-{hoy.month:02d}'
    return data, ind


def _intentar_api(data, hoy):
    """Una sola llamada rápida; no bloquear la UI si falla."""
    ultimo_dia = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    timeout = getattr(settings, 'INDICADORES_API_TIMEOUT', 1.5)
    try:
        response = requests.get('https://mindicador.cl/api', timeout=timeout)
        if response.status_code != 200:
            return data, False
        mind = response.json()
        data['uf'] = _fmt_uf(mind['uf']['valor'])
        data['utm'] = _fmt_utm(mind['utm']['valor'])
        data['fecha'] = mind['uf']['fecha'][:10]

        fecha_str = ultimo_dia.strftime('%d-%m-%Y')
        res_mensual = requests.get(f'https://mindicador.cl/api/uf/{fecha_str}', timeout=timeout)
        if res_mensual.status_code == 200:
            mind_m = res_mensual.json()
            if mind_m.get('serie'):
                data['uf_mensual'] = _fmt_uf(mind_m['serie'][0]['valor'])
        return data, True
    except Exception as exc:
        logger.warning('mindicador.cl no disponible: %s', exc)
        return data, False


def indicadores_globales(request):
    cached = cache.get(CACHE_KEY_INDICADORES)
    if cached:
        return cached

    data = {'uf': '0', 'uf_mensual': '0', 'utm': '0', 'fecha': ''}
    hoy = datetime.now()
    ind_global = None

    data, ind_global = _cargar_desde_db(data, hoy)
    api_ok = data['uf'] != '0'

    if not api_ok and getattr(settings, 'INDICADORES_USAR_API', not getattr(settings, 'IN_PRODUCTION', False)):
        data, api_ok = _intentar_api(data, hoy)
        if api_ok:
            ind_global = _indicador_db(hoy.month, hoy.year)

    if not api_ok and data['uf'] == '0':
        data, ind_global = _cargar_desde_db(data, hoy)

    result = {'ind_api': data, 'ind_global': ind_global}
    cache.set(CACHE_KEY_INDICADORES, result, CACHE_TTL_INDICADORES)
    return result
