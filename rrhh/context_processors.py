import logging
from datetime import datetime, timedelta

import requests

from rrhh.models import IndicadorEconomico

logger = logging.getLogger(__name__)


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
        return data
    data['uf'] = _fmt_uf(ind.uf)
    data['utm'] = _fmt_utm(ind.utm)
    data['uf_mensual'] = _fmt_uf(ind.uf)
    data['fecha'] = f'{hoy.year}-{hoy.month:02d}'
    return data, ind


def indicadores_globales(request):
    data = {'uf': '0', 'uf_mensual': '0', 'utm': '0', 'fecha': ''}
    ind_global = None
    hoy = datetime.now()
    ultimo_dia = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    api_ok = False

    try:
        response = requests.get('https://mindicador.cl/api', timeout=5)
        if response.status_code == 200:
            mind = response.json()
            data['uf'] = _fmt_uf(mind['uf']['valor'])
            data['utm'] = _fmt_utm(mind['utm']['valor'])
            data['fecha'] = mind['uf']['fecha'][:10]
            api_ok = True

        fecha_str = ultimo_dia.strftime('%d-%m-%Y')
        res_mensual = requests.get(f'https://mindicador.cl/api/uf/{fecha_str}', timeout=5)
        if res_mensual.status_code == 200:
            mind_m = res_mensual.json()
            if mind_m.get('serie'):
                data['uf_mensual'] = _fmt_uf(mind_m['serie'][0]['valor'])
    except Exception as exc:
        logger.warning('mindicador.cl no disponible: %s', exc)

    if not api_ok or data['uf'] == '0':
        result = _cargar_desde_db(data, hoy)
        if isinstance(result, tuple):
            data, ind_global = result
        else:
            data = result
    else:
        ind_global = _indicador_db(hoy.month, hoy.year)

    return {'ind_api': data, 'ind_global': ind_global}
