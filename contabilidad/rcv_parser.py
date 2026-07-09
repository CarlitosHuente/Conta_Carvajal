"""Parser CSV RCV compras formato SII."""

import csv
import io
import re
from datetime import datetime

from .models import DocumentoCompraRCV


def normalizar_rut(rut):
    return (rut or '').strip().upper().replace('.', '')


def inferir_periodo_desde_nombre(nombre_archivo):
    """Extrae (mes, año) de RCV_COMPRA_REGISTRO_RUT_YYYYMM.csv"""
    match = re.search(r'_(\d{4})(\d{2})\.csv$', nombre_archivo, re.IGNORECASE)
    if match:
        ano = int(match.group(1))
        mes = int(match.group(2))
        if 1 <= mes <= 12:
            return mes, ano
    return None, None


def _parse_fecha(valor):
    valor = (valor or '').strip()
    if not valor:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y'):
        try:
            return datetime.strptime(valor, fmt)
        except ValueError:
            continue
    return None


def _parse_entero(valor):
    valor = (valor or '').strip()
    if not valor:
        return 0
    try:
        return int(float(valor.replace(',', '.')))
    except ValueError:
        return 0


def parsear_csv_rcv_compras(contenido, encoding='utf-8-sig'):
    """
    Lee CSV SII compras. Retorna lista de dicts normalizados.
    Lanza ValueError si el formato no es válido.
    """
    if isinstance(contenido, bytes):
        for enc in (encoding, 'utf-8-sig', 'latin-1', 'cp1252'):
            try:
                texto = contenido.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError('No se pudo leer el archivo CSV (codificación).')
    else:
        texto = contenido

    reader = csv.DictReader(io.StringIO(texto), delimiter=';')
    if not reader.fieldnames:
        raise ValueError('El CSV está vacío o no tiene encabezados.')

    campos_req = {'Tipo Doc', 'RUT Proveedor', 'Razon Social', 'Folio', 'Fecha Docto', 'Monto Total'}
    if not campos_req.issubset(set(reader.fieldnames)):
        raise ValueError(
            'Formato RCV no reconocido. Se esperan columnas del registro de compras del SII.'
        )

    filas = []
    for i, row in enumerate(reader, start=1):
        tipo_doc = _parse_entero(row.get('Tipo Doc'))
        if tipo_doc not in (33, 34, 56, 61):
            continue

        rut = normalizar_rut(row.get('RUT Proveedor'))
        if not rut:
            continue

        fecha_dt = _parse_fecha(row.get('Fecha Docto'))
        if not fecha_dt:
            raise ValueError(f'Fila {i}: fecha de documento inválida.')

        fecha_recep = _parse_fecha(row.get('Fecha Recepcion'))

        filas.append({
            'tipo_doc': tipo_doc,
            'tipo_compra': (row.get('Tipo Compra') or '').strip(),
            'rut_proveedor': rut,
            'razon_social': (row.get('Razon Social') or '').strip(),
            'folio': _parse_entero(row.get('Folio')),
            'fecha_docto': fecha_dt.date(),
            'fecha_recepcion': fecha_recep,
            'monto_exento': _parse_entero(row.get('Monto Exento')),
            'monto_neto': _parse_entero(row.get('Monto Neto')),
            'monto_iva_recuperable': _parse_entero(row.get('Monto IVA Recuperable')),
            'monto_otro_impuesto': _parse_entero(row.get('Valor Otro Impuesto')),
            'monto_total': _parse_entero(row.get('Monto Total')),
        })

    if not filas:
        raise ValueError('No se encontraron documentos de compra válidos en el CSV.')

    return filas


def clave_documento(empresa_id, fila, proveedor_id):
    return (empresa_id, fila['tipo_doc'], fila['folio'], proveedor_id)


def documento_ya_existe(empresa_id, tipo_doc, folio, proveedor_id):
    return DocumentoCompraRCV.objects.filter(
        empresa_id=empresa_id,
        tipo_doc=tipo_doc,
        folio=folio,
        proveedor_id=proveedor_id,
    ).exists()
