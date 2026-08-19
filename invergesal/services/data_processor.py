import io
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from invergesal.services import drive
from invergesal.services.quality import (
    QualityReport,
    agrupar_por_archivo,
    escribir_consolidado,
)

CONSOLIDATED_FILENAME = 'Reporte_Consolidado.xlsx'
COLUMN_NAMES = [
    'NAVE', 'FECHA', 'NAVIERA', 'PUERTO_CARGA', 'EXPORTADOR', 'CAJAS',
    'N.N', 'REEFER', 'TIPO_DE_REEFER', 'MARCA', 'PUERTO_DESCARGA', 'CONSIGNATARIO',
]


def consolidar_archivos_drive(folder_id: str):
    report = QualityReport()
    service = drive.get_drive_service()
    if not service:
        return None, 'No se pudo conectar con la API de Google Drive.', report

    query = (
        f"'{folder_id}' in parents and "
        "mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' and "
        'trashed=false'
    )
    response = service.files().list(q=query, fields='files(id, name)').execute()
    all_files = response.get('files', [])
    files_to_process = [f for f in all_files if f['name'] != CONSOLIDATED_FILENAME]

    if not files_to_process:
        return None, 'No se encontraron archivos Excel para procesar en la carpeta.', report

    dfs = []
    for file_info in files_to_process:
        nombre = file_info['name']
        file_bytes = drive.download_file(file_info['id'])
        if not file_bytes:
            report.add(
                archivo=nombre,
                motivo='No se pudo descargar desde Google Drive. El archivo no se incorporó.',
            )
            continue
        try:
            df = pd.read_excel(file_bytes)
        except Exception as exc:
            report.add(
                archivo=nombre,
                motivo='Excel ilegible o dañado. El archivo no se incorporó.',
                detalle=str(exc)[:200],
            )
            continue
        if len(df.columns) != len(COLUMN_NAMES):
            cols = ', '.join(str(c) for c in list(df.columns)[:8])
            extra = '…' if len(df.columns) > 8 else ''
            report.add(
                archivo=nombre,
                motivo=(
                    f'Tiene {len(df.columns)} columnas; se esperan {len(COLUMN_NAMES)}. '
                    'No se incorporó el archivo (formato distinto).'
                ),
                detalle=f'Columnas: {cols}{extra}',
            )
            continue
        df.columns = COLUMN_NAMES
        df['ARCHIVO_ORIGEN'] = nombre
        sin_fecha = df[df['FECHA'].isna()]
        report.add_filas(sin_fecha, nombre, 'Fila sin fecha: no entra al consolidado')
        df = df.dropna(subset=['FECHA'])
        dfs.append(df)

    if not dfs:
        return None, 'Ningún archivo pudo ser procesado correctamente.', report

    return pd.concat(dfs, ignore_index=True), 'Archivos consolidados con éxito.', report


def obtener_semana(fecha):
    if pd.isna(fecha):
        return None
    anio = fecha.year % 100
    semana = fecha.isocalendar()[1]
    return f'{anio:02d}{semana:02d}'


def agregar_columna_semana(df: pd.DataFrame, report=None):
    fecha_original = df['FECHA'].copy()
    df['FECHA'] = pd.to_datetime(df['FECHA'], dayfirst=True, errors='coerce')
    if report is not None:
        invalidas = df['FECHA'].isna()
        if invalidas.any():
            subset = df.loc[invalidas]
            for archivo, grupo in agrupar_por_archivo(subset):
                report.add_filas(
                    grupo,
                    archivo,
                    'Fecha inválida: no se calculó semana; la fila no se mostrará en la tabla',
                    fechas=fecha_original.loc[grupo.index],
                )
    df['SEMANA'] = df['FECHA'].apply(obtener_semana)
    return df, "Columna 'SEMANA' agregada."


def _cajas_no_numericas_de_archivo(file_info):
    nombre = file_info.get('name') or ''
    try:
        file_bytes = drive.download_file(file_info['id'])
        if not file_bytes:
            return None
        df = pd.read_excel(file_bytes)
    except Exception:
        return None
    if len(df.columns) != len(COLUMN_NAMES):
        return None
    df.columns = COLUMN_NAMES
    df['ARCHIVO_ORIGEN'] = nombre
    cajas_num = pd.to_numeric(df['CAJAS'], errors='coerce')
    mal = df[cajas_num.isna() & df['CAJAS'].notna()].copy()
    if mal.empty:
        return None
    return nombre, mal


def escanear_cajas_no_numericas_origen(folder_id: str):
    """
    Busca en cada Excel de origen (no el consolidado) filas cuya CAJAS no es número.
    No altera el consolidado: solo identifica el nombre exacto del archivo.
    """
    hallazgos = []
    if not folder_id:
        return hallazgos
    try:
        files = drive.list_xlsx_files(folder_id, exclude_names={CONSOLIDATED_FILENAME})
    except Exception:
        return hallazgos

    workers = min(8, max(1, len(files)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = [pool.submit(_cajas_no_numericas_de_archivo, f) for f in files]
        for futuro in as_completed(futuros):
            try:
                resultado = futuro.result()
            except Exception:
                continue
            if resultado:
                hallazgos.append(resultado)
    return hallazgos


def generar_reporte_consolidado(folder_id: str):
    df_consolidado, msg1, report = consolidar_archivos_drive(folder_id)
    if df_consolidado is None:
        return False, msg1, report.to_payload()

    df_final, _msg2 = agregar_columna_semana(df_consolidado, report=report)
    try:
        output_buffer = escribir_consolidado(df_final, report)
    except Exception:
        output_buffer = io.BytesIO()
        df_final.to_excel(output_buffer, index=False)
        output_buffer.seek(0)
    ok, msg = drive.upload_or_overwrite_file(CONSOLIDATED_FILENAME, folder_id, output_buffer)
    return ok, msg, report.to_payload()
