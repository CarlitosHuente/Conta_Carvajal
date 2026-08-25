from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import json

from django.conf import settings

FACTOR_IVA = Decimal('1.19')
FLETE_TERRESTRE = 'flete_terrestre'
SERVICIO_FRIO = 'servicio_frio'
DESPACHO = 'despacho'

CONCEPTOS = (
    {
        'id': FLETE_TERRESTRE,
        'nombre': 'Flete Terrestre',
        'gasto': 'F.TERRES',
        'base': 'cont',
        'base_txt': 'contenedores (CONT)',
        'regla': 'Valor × total de contenedores (CONT) × 1,19',
    },
    {
        'id': SERVICIO_FRIO,
        'nombre': 'Servicio de Frío',
        'gasto': 'SER FRIO',
        'base': 'cajas',
        'base_txt': 'cajas',
        'regla': 'Valor × total de cajas × 1,19',
    },
    {
        'id': DESPACHO,
        'nombre': 'Despacho',
        'gasto': 'DESPACHO',
        'base': 'cajas',
        'base_txt': 'cajas',
        'regla': 'Valor × total de cajas × 1,19',
    },
)
CONCEPTOS_POR_ID = {item['id']: item for item in CONCEPTOS}

_LOCK = Lock()


def ruta_json():
    configurada = getattr(settings, 'INVERGESAL_PARAMETROS_GASTOS_JSON', None)
    if configurada:
        return Path(configurada)
    return Path(settings.BASE_DIR) / 'invergesal_data' / 'parametros_gastos.json'


def _archivo_vacio():
    return {'siguiente_id': 1, 'periodos': []}


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
    periodos = data.get('periodos')
    if not isinstance(periodos, list):
        periodos = []
    try:
        siguiente = int(data.get('siguiente_id') or 1)
    except (TypeError, ValueError):
        siguiente = 1
    return {'siguiente_id': max(siguiente, 1), 'periodos': periodos}


def _escribir_crudo(data):
    ruta = ruta_json()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(ruta)


def _as_periodo(item):
    if not isinstance(item, dict):
        return None
    anio_desde = parse_anio(item.get('anio_desde'))
    semana_desde = parse_semana(item.get('semana_desde'))
    anio_hasta = parse_anio(item.get('anio_hasta'))
    semana_hasta = parse_semana(item.get('semana_hasta'))
    valor = parse_valor(item.get('valor'))
    concepto = (item.get('concepto') or '').strip()
    try:
        pk = int(item.get('id'))
    except (TypeError, ValueError):
        return None
    if None in (anio_desde, semana_desde, anio_hasta, semana_hasta, valor) or concepto not in CONCEPTOS_POR_ID:
        return None
    return SimpleNamespace(
        id=pk,
        concepto=concepto,
        anio_desde=anio_desde,
        semana_desde=semana_desde,
        anio_hasta=anio_hasta,
        semana_hasta=semana_hasta,
        valor=valor,
    )


def _periodos():
    filas = []
    for item in _leer_crudo()['periodos']:
        periodo = _as_periodo(item)
        if periodo:
            filas.append(periodo)
    filas.sort(key=lambda p: (p.concepto, clave_semana(p.anio_desde, p.semana_desde), p.id))
    return filas


def _dump_periodo(periodo):
    return {
        'id': periodo.id,
        'concepto': periodo.concepto,
        'anio_desde': periodo.anio_desde,
        'semana_desde': periodo.semana_desde,
        'anio_hasta': periodo.anio_hasta,
        'semana_hasta': periodo.semana_hasta,
        'valor': str(periodo.valor),
    }


def clave_semana(anio, semana):
    return int(anio) * 100 + int(semana)


def fmt_semana(anio, semana):
    return f'semana {int(semana)} de {int(anio)}'


def fmt_monto(valor):
    numero = Decimal(str(valor)).quantize(Decimal('0.0001')).normalize()
    if numero == numero.to_integral():
        return f'{int(numero):,}'.replace(',', '.')
    texto = f'{numero:,.4f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return texto.rstrip('0').rstrip(',')


def parse_anio(valor):
    try:
        anio = int(valor)
    except (TypeError, ValueError):
        return None
    if 2000 <= anio <= 2100:
        return anio
    return None


def parse_semana(valor):
    try:
        semana = int(valor)
    except (TypeError, ValueError):
        return None
    if 1 <= semana <= 53:
        return semana
    return None


def parse_valor(valor):
    if valor in (None, ''):
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace(' ', '').replace('$', '')
    if not texto:
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    elif texto.count('.') > 1:
        texto = texto.replace('.', '')
    elif '.' in texto:
        decimales = texto.split('.')[-1]
        if len(decimales) == 3 and decimales.isdigit():
            texto = texto.replace('.', '')
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return numero


def monto_gasto(valor_unitario, cantidad):
    if valor_unitario is None or not cantidad:
        return None
    total = Decimal(str(valor_unitario)) * Decimal(str(cantidad)) * FACTOR_IVA
    return int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _nombre_concepto(concepto):
    meta = CONCEPTOS_POR_ID.get(concepto)
    return meta['nombre'] if meta else concepto


def conflictos_periodo(concepto, anio_desde, semana_desde, anio_hasta, semana_hasta, excluir_id=None):
    inicio = clave_semana(anio_desde, semana_desde)
    fin = clave_semana(anio_hasta, semana_hasta)
    choques = []
    for otro in _periodos():
        if otro.concepto != concepto:
            continue
        if excluir_id and otro.id == excluir_id:
            continue
        otro_ini = clave_semana(otro.anio_desde, otro.semana_desde)
        otro_fin = clave_semana(otro.anio_hasta, otro.semana_hasta)
        if inicio <= otro_fin and otro_ini <= fin:
            choque_ini = max(inicio, otro_ini)
            choque_fin = min(fin, otro_fin)
            choques.append({
                'id': otro.id,
                'anio_desde': otro.anio_desde,
                'semana_desde': otro.semana_desde,
                'anio_hasta': otro.anio_hasta,
                'semana_hasta': otro.semana_hasta,
                'valor': otro.valor,
                'choque_desde': choque_ini,
                'choque_hasta': choque_fin,
            })
    return choques


def _anio_sem(clave):
    return divmod(int(clave), 100)


def mensaje_choque(concepto, anio_desde, semana_desde, anio_hasta, semana_hasta, choques):
    nombre = _nombre_concepto(concepto)
    lineas = [
        f'No se pudo guardar {nombre} de la {fmt_semana(anio_desde, semana_desde)} a la {fmt_semana(anio_hasta, semana_hasta)}.',
        'Las semanas se topan con un periodo ya ingresado del mismo concepto:',
    ]
    for choque in choques:
        c_anio_d, c_sem_d = _anio_sem(choque['choque_desde'])
        c_anio_h, c_sem_h = _anio_sem(choque['choque_hasta'])
        lineas.append(
            f'• Choca con {fmt_semana(choque["anio_desde"], choque["semana_desde"])} '
            f'a {fmt_semana(choque["anio_hasta"], choque["semana_hasta"])} '
            f'(valor {fmt_monto(choque["valor"])}): las semanas en conflicto son '
            f'de la {fmt_semana(c_anio_d, c_sem_d)} a la {fmt_semana(c_anio_h, c_sem_h)}.'
        )
    lineas.append('Los periodos del mismo concepto no pueden compartir ninguna semana de embarque. Ajusta el rango e inténtalo de nuevo.')
    return '\n'.join(lineas)


def crear_parametro(concepto, anio_desde, semana_desde, anio_hasta, semana_hasta, valor):
    if concepto not in CONCEPTOS_POR_ID:
        return False, 'Concepto no válido.', None
    if None in (anio_desde, semana_desde, anio_hasta, semana_hasta):
        return False, 'Indica año y semana de inicio, y año y semana de término.', None
    if clave_semana(anio_desde, semana_desde) > clave_semana(anio_hasta, semana_hasta):
        return False, (
            f'El inicio ({fmt_semana(anio_desde, semana_desde)}) no puede ser posterior '
            f'al término ({fmt_semana(anio_hasta, semana_hasta)}).'
        ), None
    if valor is None:
        return False, 'Indica el valor del parámetro.', None
    if valor < 0:
        return False, 'El valor no puede ser negativo.', None
    with _LOCK:
        choques = conflictos_periodo(concepto, anio_desde, semana_desde, anio_hasta, semana_hasta)
        if choques:
            return False, mensaje_choque(concepto, anio_desde, semana_desde, anio_hasta, semana_hasta, choques), None
        data = _leer_crudo()
        pk = int(data.get('siguiente_id') or 1)
        periodo = SimpleNamespace(
            id=pk,
            concepto=concepto,
            anio_desde=anio_desde,
            semana_desde=semana_desde,
            anio_hasta=anio_hasta,
            semana_hasta=semana_hasta,
            valor=valor,
        )
        data['periodos'].append(_dump_periodo(periodo))
        data['siguiente_id'] = pk + 1
        _escribir_crudo(data)
    return True, 'Parámetro guardado.', periodo


def eliminar_parametro(pk):
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return False, 'No se encontró ese parámetro.'
    with _LOCK:
        data = _leer_crudo()
        original = len(data['periodos'])
        data['periodos'] = [item for item in data['periodos'] if item.get('id') != pk]
        if len(data['periodos']) == original:
            return False, 'No se encontró ese parámetro.'
        _escribir_crudo(data)
    return True, 'Parámetro eliminado.'


def tarifa_vigente(concepto, anio, semana):
    try:
        clave = clave_semana(anio, semana)
    except (TypeError, ValueError):
        return None
    vigentes = [
        p for p in _periodos()
        if p.concepto == concepto
        and clave_semana(p.anio_desde, p.semana_desde) <= clave <= clave_semana(p.anio_hasta, p.semana_hasta)
    ]
    vigentes.sort(key=lambda p: clave_semana(p.anio_desde, p.semana_desde), reverse=True)
    return vigentes[0] if vigentes else None


def tarifas_para_semana(anio, semana):
    return {
        item['id']: getattr(tarifa_vigente(item['id'], anio, semana), 'valor', None)
        for item in CONCEPTOS
    }


def serializar_parametros(anio=None, semana=None):
    por_concepto = {item['id']: [] for item in CONCEPTOS}
    for fila in _periodos():
        por_concepto.setdefault(fila.concepto, []).append({
            'id': fila.id,
            'anio_desde': fila.anio_desde,
            'semana_desde': fila.semana_desde,
            'anio_hasta': fila.anio_hasta,
            'semana_hasta': fila.semana_hasta,
            'desde_txt': fmt_semana(fila.anio_desde, fila.semana_desde),
            'hasta_txt': fmt_semana(fila.anio_hasta, fila.semana_hasta),
            'valor': float(fila.valor),
        })
    conceptos = []
    for item in CONCEPTOS:
        vigente = None
        if anio and semana:
            hallado = tarifa_vigente(item['id'], anio, semana)
            if hallado:
                vigente = {
                    'id': hallado.id,
                    'desde_txt': fmt_semana(hallado.anio_desde, hallado.semana_desde),
                    'hasta_txt': fmt_semana(hallado.anio_hasta, hallado.semana_hasta),
                    'valor': float(hallado.valor),
                }
        conceptos.append({
            **item,
            'periodos': por_concepto.get(item['id'], []),
            'vigente': vigente,
        })
    return {
        'anio': anio,
        'semana': semana,
        'conceptos': conceptos,
        'factor_iva': float(FACTOR_IVA),
    }
