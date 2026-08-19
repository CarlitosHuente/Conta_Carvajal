import os
from datetime import datetime

import pandas as pd
import pytz
from django.conf import settings
from django.core.cache import cache

from invergesal.services import drive
from invergesal.services.data_processor import (
    CONSOLIDATED_FILENAME,
    escanear_cajas_no_numericas_origen,
)
from invergesal.services.quality import (
    QualityReport,
    agrupar_por_archivo,
    leer_hoja_calidad,
    leer_hoja_datos,
    _filas_detalle,
)

CACHE_KEY_DF = 'invergesal_df'
CACHE_KEY_INFO = 'invergesal_file_info'
CACHE_KEY_CALIDAD = 'invergesal_calidad'
CACHE_KEY_SCAN_CAJAS = 'invergesal_scan_cajas_origen'
CACHE_TIMEOUT = 60 * 60 * 6


def get_folder_id():
    return getattr(settings, 'INVERGESAL_GDRIVE_FOLDER_ID', None) or os.environ.get('GDRIVE_FOLDER_ID')


def convert_utc_to_local(utc_str, timezone_str='America/Santiago'):
    try:
        utc_dt = datetime.strptime(utc_str, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.utc)
    except ValueError:
        try:
            utc_dt = datetime.strptime(utc_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.utc)
        except Exception:
            return utc_str
    except Exception:
        return utc_str
    local_dt = utc_dt.astimezone(pytz.timezone(timezone_str))
    return local_dt.strftime('%d/%m/%Y %H:%M:%S')


def expandir_marcas_multiples(df: pd.DataFrame) -> pd.DataFrame:
    nuevas_filas = []
    for _, row in df.iterrows():
        fila_original = row.to_dict()
        marca = fila_original.get('MARCA')
        if isinstance(marca, str) and '/' in marca:
            if marca.upper() == 'S/M':
                nuevas_filas.append(fila_original)
                continue
            marcas = [m.strip() for m in marca.split('/')]
            if marcas:
                cajas_divididas = fila_original.get('CAJAS', 0) / len(marcas)
                for marca_individual in marcas:
                    nueva_fila = fila_original.copy()
                    nueva_fila['MARCA'] = marca_individual
                    nueva_fila['CAJAS'] = cajas_divididas
                    nuevas_filas.append(nueva_fila)
            else:
                nuevas_filas.append(fila_original)
        else:
            nuevas_filas.append(fila_original)
    return pd.DataFrame(nuevas_filas)


def _ya_reportado_semana(report, archivo):
    archivo = str(archivo)
    for item in report.items:
        if str(item.get('archivo')) != archivo:
            continue
        motivo = (item.get('motivo') or '').lower()
        if 'semana' in motivo or 'fecha inválida' in motivo or 'sin fecha' in motivo:
            return True
    return False


def _valores_cajas_raw(subset, n=8):
    if subset is None or subset.empty or 'CAJAS' not in subset.columns:
        return ''
    vistos = []
    for val in subset['CAJAS'].head(20):
        texto = str(val).strip()
        if texto and texto.lower() not in ('nan', 'none') and texto not in vistos:
            vistos.append(texto)
        if len(vistos) >= n:
            break
    return ('CAJAS leído como: ' + ', '.join(vistos)) if vistos else ''


def _reportar_cajas_no_numericas(report, mal, folder_id=None):
    motivo = 'Valor de CAJAS no numérico: se interpretó como 0 (la fila sí se muestra)'
    if mal is None or mal.empty:
        return
    for archivo, grupo in agrupar_por_archivo(mal):
        report.add_filas(grupo, archivo, motivo)


def _analizar_carga(df, report_previo=None):
    report = QualityReport()
    if df is None or df.empty:
        return report
    req = ['MARCA', 'CONSIGNATARIO', 'SEMANA', 'CAJAS']
    if not all(c in df.columns for c in req):
        return report

    faltantes = df[df[req].isna().any(axis=1)].copy()
    if not faltantes.empty:
        faltantes['_faltan'] = faltantes.apply(
            lambda row: ', '.join(col for col in req if pd.isna(row.get(col))),
            axis=1,
        )
        previo = report_previo or QualityReport()
        for archivo, grupo in agrupar_por_archivo(faltantes):
            for campos, sub in grupo.groupby('_faltan'):
                if campos == 'SEMANA' and _ya_reportado_semana(previo, archivo):
                    continue
                report.add_filas(
                    sub.drop(columns=['_faltan'], errors='ignore'),
                    archivo,
                    f'Fila no se muestra: falta {campos}',
                )

    cajas_num = pd.to_numeric(df['CAJAS'], errors='coerce')
    mal = df[cajas_num.isna() & df['CAJAS'].notna()]
    _reportar_cajas_no_numericas(report, mal)
    return report


def set_calidad(payload):
    cache.set(CACHE_KEY_CALIDAD, payload or QualityReport.empty_payload(), CACHE_TIMEOUT)


def get_calidad():
    return cache.get(CACHE_KEY_CALIDAD) or QualityReport.empty_payload()


def merge_calidad(*payloads):
    report = QualityReport()
    for payload in payloads:
        if not payload:
            continue
        items = payload.get('items') if isinstance(payload, dict) else payload
        report.extend(QualityReport(items))
    set_calidad(report.to_payload())
    return get_calidad()


def _serializar_hallazgos_cajas(hallados):
    filas = []
    for nombre, grupo in hallados:
        detalle = _filas_con_archivo(grupo, nombre)
        filas.extend(detalle)
    filas.sort(key=lambda f: (f.get('fecha_iso') or '', f.get('archivo') or '', f.get('nave') or ''))
    return filas


def _recomendacion_cajas(valor):
    texto = str(valor or '').strip()
    compacto = texto.replace(' ', '').replace('\xa0', '')
    if not texto or texto in ('—', '-') or set(compacto) <= set('-_.') or texto.lower() in (
        'n/a', 'na', 's/n', 'nan', 'none',
    ):
        return 'No conviene modificar: no hay un número que recuperar (ya cuenta como 0).'
    solo_num = compacto.replace('.', '').replace(',', '')
    if solo_num.isdigit():
        return 'Conviene corregir: parece un número mal escrito.'
    return 'Revisar: corrige solo si en el Excel debería ser un número.'


def _filas_con_archivo(subset, archivo):
    filas = _filas_detalle(subset)
    for fila in filas:
        fila['archivo'] = archivo
        fila['recomendacion'] = _recomendacion_cajas(fila.get('cajas'))
    return filas


def _scan_cajas_origen_cached():
    cached = cache.get(CACHE_KEY_SCAN_CAJAS)
    if cached is not None:
        return cached
    hallados = escanear_cajas_no_numericas_origen(get_folder_id())
    filas = _serializar_hallazgos_cajas(hallados)
    cache.set(CACHE_KEY_SCAN_CAJAS, filas, CACHE_TIMEOUT)
    return filas


def obtener_detalle_cajas_por_puerto(puerto):
    """Al pulsar Ver detalle: busca en Drive el Excel de origen de ese puerto."""
    puerto_norm = (puerto or '').strip().upper()
    if not puerto_norm:
        return []
    filas = _scan_cajas_origen_cached()
    return [f for f in filas if (f.get('puerto') or '').strip().upper() == puerto_norm]


def cargar_datos_en_cache(force_refresh=False):
    folder_id = get_folder_id()
    if not folder_id:
        return False, 'El ID de la carpeta de Google Drive no está configurado.'

    drive_file_info = drive.find_file_by_name(CONSOLIDATED_FILENAME, folder_id)
    if not drive_file_info:
        cache.delete_many([CACHE_KEY_DF, CACHE_KEY_INFO, CACHE_KEY_CALIDAD, CACHE_KEY_SCAN_CAJAS])
        return False, "El archivo 'Reporte_Consolidado.xlsx' no se encontró en Google Drive. Por favor, genérelo primero."

    cached_info = cache.get(CACHE_KEY_INFO) or {}
    cached_df = cache.get(CACHE_KEY_DF)
    is_stale = cached_df is None or cached_info.get('modifiedTime') != drive_file_info['modifiedTime']

    if force_refresh or is_stale:
        cache.delete(CACHE_KEY_SCAN_CAJAS)
        try:
            file_bytes = drive.download_file(drive_file_info['id'])
            if not file_bytes:
                return False, 'Error al descargar el reporte desde Drive.'

            report = leer_hoja_calidad(file_bytes)
            df = expandir_marcas_multiples(leer_hoja_datos(file_bytes))
            report.extend(_analizar_carga(df, report_previo=report))
            df = df.dropna(subset=['MARCA', 'CONSIGNATARIO', 'SEMANA', 'CAJAS'])
            df['SEMANA'] = df['SEMANA'].astype(str)
            df['CAJAS'] = pd.to_numeric(df['CAJAS'], errors='coerce').fillna(0)
            cache.set(CACHE_KEY_DF, df, CACHE_TIMEOUT)
            cache.set(CACHE_KEY_INFO, drive_file_info, CACHE_TIMEOUT)
            set_calidad(report.to_payload())
        except Exception as exc:
            return False, f'Error al procesar el archivo Excel: {exc}'

    return True, 'Datos cargados correctamente.'


def get_cached_df():
    return cache.get(CACHE_KEY_DF)


def get_cache_info():
    info = dict(cache.get(CACHE_KEY_INFO) or {})
    if info.get('modifiedTime'):
        info['modifiedTimeLocal'] = convert_utc_to_local(info['modifiedTime'])
    return info


def clear_cache():
    cache.delete_many([CACHE_KEY_DF, CACHE_KEY_INFO, CACHE_KEY_CALIDAD, CACHE_KEY_SCAN_CAJAS])


def filtros_desde_request(request, defaults=None):
    defaults = defaults or {}
    if request.method == 'POST':
        return {
            'semanas': request.POST.getlist('semanas'),
            'puertos': request.POST.getlist('puertos'),
            'naviera': request.POST.get('naviera') or 'TODAS',
            'consignatario': request.POST.get('consignatario_search', '').strip(),
        }
    return {
        'semanas': defaults.get('semanas', []),
        'puertos': defaults.get('puertos', ['SAN ANTONIO', 'VALPARAISO']),
        'naviera': defaults.get('naviera', 'TODAS'),
        'consignatario': defaults.get('consignatario', ''),
    }


def aplicar_filtros(df, semanas, puertos, naviera, consignatario):
    df_filtrado = df.copy()
    if semanas:
        df_filtrado = df_filtrado[df_filtrado['SEMANA'].isin(semanas)]
    if puertos:
        df_filtrado = df_filtrado[df_filtrado['PUERTO_DESCARGA'].isin(puertos)]
    if naviera and naviera != 'TODAS':
        df_filtrado = df_filtrado[df_filtrado['NAVIERA'] == naviera]
    if consignatario:
        df_filtrado = df_filtrado[df_filtrado['CONSIGNATARIO'].str.contains(consignatario, case=False, na=False)]
    return df_filtrado


def construir_tabla(df_filtrado, semanas_seleccionadas):
    tabla_final = {'gran_total': {}, 'marcas': []}
    if df_filtrado.empty:
        return tabla_final

    pivote = pd.pivot_table(
        df_filtrado,
        values='CAJAS',
        index=['MARCA', 'CONSIGNATARIO'],
        columns='SEMANA',
        aggfunc='sum',
        fill_value=0,
    )
    if pivote.empty:
        return tabla_final

    pivote = pivote.reindex(columns=semanas_seleccionadas, fill_value=0)
    tabla_final['gran_total'] = pivote.sum(axis=0).to_dict()
    pivote['TOTAL_CAJAS_SORTER'] = pivote.sum(axis=1)
    pivote = pivote.sort_values(by=['MARCA', 'TOTAL_CAJAS_SORTER'], ascending=[True, False])
    for marca, df_marca in pivote.groupby(level='MARCA', sort=False):
        total_marca = df_marca.sum(axis=0)
        consignatarios = []
        for (_marca_idx, consignatario), series in df_marca.iterrows():
            consignatarios.append({'nombre': consignatario, 'cajas_por_semana': series.to_dict()})
        tabla_final['marcas'].append({
            'nombre': marca,
            'total_marca': total_marca.to_dict(),
            'consignatarios': consignatarios,
        })
    tabla_final['marcas'] = sorted(
        tabla_final['marcas'],
        key=lambda x: x['total_marca'].get('TOTAL_CAJAS_SORTER', 0),
        reverse=True,
    )
    return tabla_final
