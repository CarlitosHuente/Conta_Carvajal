import requests
from datetime import datetime, timedelta

def indicadores_globales(request):
    data = {'uf': '0', 'uf_mensual': '0', 'utm': '0', 'fecha': ''}
    hoy = datetime.now()
    # Calculamos el último día del mes actual
    ultimo_dia = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    
    try:
        # 1. UF de hoy y UTM
        response = requests.get('https://mindicador.cl/api', timeout=2)
        if response.status_code == 200:
            mind = response.json()
            data['uf'] = f"{mind['uf']['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            data['utm'] = f"{mind['utm']['valor']:,.0f}".replace(",", ".")
            data['fecha'] = mind['uf']['fecha'][:10]
        
        # 2. UF del último día del mes (UF Mensual)
        fecha_str = ultimo_dia.strftime('%d-%m-%Y')
        res_mensual = requests.get(f'https://mindicador.cl/api/uf/{fecha_str}', timeout=2)
        if res_mensual.status_code == 200:
            mind_m = res_mensual.json()
            if mind_m['serie']:
                val_m = mind_m['serie'][0]['valor']
                data['uf_mensual'] = f"{val_m:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        pass
    return {'ind_api': data}