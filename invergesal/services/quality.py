"""Resumen de datos omitidos o dudosos. No cambia qué filas entran al cálculo."""

from __future__ import annotations

import pandas as pd

CALIDAD_SHEET = 'Calidad'
CALIDAD_COLUMNS = ['archivo', 'fecha', 'motivo', 'cantidad', 'detalle']


def fmt_fecha(val):
    try:
        if val is None or pd.isna(val):
            return '—'
    except (TypeError, ValueError):
        pass
    if hasattr(val, 'strftime'):
        try:
            return val.strftime('%d/%m/%Y')
        except (ValueError, OSError):
            pass
    text = str(val).strip()
    if not text or text.lower() in ('nat', 'nan', 'none', 'nattype'):
        return '—'
    return text


def _fechas_muestra(series, n=5):
    if series is None:
        return '—'
    vistos = []
    for val in series.head(20):
        texto = fmt_fecha(val)
        if texto != '—' and texto not in vistos:
            vistos.append(texto)
        if len(vistos) >= n:
            break
    return ', '.join(vistos) if vistos else '—'


def _texto_celda(val):
    try:
        if val is None or pd.isna(val):
            return '—'
    except (TypeError, ValueError):
        pass
    texto = str(val).strip()
    if not texto or texto.lower() in ('nan', 'none', 'nat', 'nattype'):
        return '—'
    return texto


def _puerto_fila(row):
    for col in ('PUERTO_DESCARGA', 'PUERTO_CARGA'):
        try:
            val = row.get(col)
        except Exception:
            val = None
        texto = _texto_celda(val)
        if texto != '—':
            return texto
    return '—'


def _filas_detalle(subset):
    filas = []
    if subset is None or subset.empty:
        return filas
    for _, row in subset.iterrows():
        fecha_iso = ''
        try:
            ts = pd.to_datetime(row.get('FECHA'), errors='coerce')
            if ts is not None and not pd.isna(ts):
                fecha_iso = ts.strftime('%Y-%m-%d')
        except Exception:
            fecha_iso = ''
        filas.append({
            'fecha': fmt_fecha(row.get('FECHA')),
            'fecha_iso': fecha_iso,
            'nave': _texto_celda(row.get('NAVE')),
            'puerto': _puerto_fila(row),
            'cajas': _texto_celda(row.get('CAJAS')),
        })
    filas.sort(key=lambda f: (f.get('fecha_iso') or '', f.get('nave') or '', f.get('puerto') or ''))
    return filas


def _puertos_unicos(filas):
    vistos = []
    for fila in filas:
        puerto = fila.get('puerto') or '—'
        if puerto not in vistos:
            vistos.append(puerto)
    return vistos


def _puertos_resumen(filas):
    conteo = {}
    orden = []
    for fila in filas:
        puerto = fila.get('puerto') or '—'
        if puerto not in conteo:
            orden.append(puerto)
            conteo[puerto] = 0
        conteo[puerto] += 1
    return [{'nombre': puerto, 'cantidad': conteo[puerto]} for puerto in orden]


class QualityReport:
    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, archivo, motivo, cantidad=1, fecha='—', detalle='', puertos=None, filas=None):
        if cantidad <= 0:
            return
        self.items.append({
            'archivo': archivo or '—',
            'fecha': fecha or '—',
            'motivo': motivo,
            'cantidad': int(cantidad),
            'detalle': detalle or '',
            'puertos': list(puertos or []),
            'filas': list(filas or []),
        })

    def add_filas(self, subset, archivo, motivo, fechas=None, extra_detalle=''):
        if subset is None or subset.empty:
            return
        serie_fechas = fechas if fechas is not None else (subset['FECHA'] if 'FECHA' in subset.columns else None)
        filas = _filas_detalle(subset)
        resumen_puertos = _puertos_resumen(filas)
        nombres = [p['nombre'] for p in resumen_puertos]
        detalle = ('Puertos: ' + ', '.join(nombres)) if nombres else ''
        if extra_detalle and not filas:
            detalle = f'{detalle} · {extra_detalle}'.strip(' ·')
        self.add(
            archivo=archivo,
            motivo=motivo,
            cantidad=len(subset),
            fecha=_fechas_muestra(serie_fechas),
            detalle=detalle,
            puertos=resumen_puertos,
            filas=filas,
        )

    def extend(self, other):
        if not other:
            return
        existentes = {(i.get('archivo'), i.get('motivo'), i.get('fecha')) for i in self.items}
        for item in other.items if isinstance(other, QualityReport) else other:
            key = (item.get('archivo'), item.get('motivo'), item.get('fecha'))
            if key not in existentes:
                self.items.append(item)
                existentes.add(key)

    def to_dataframe(self):
        if not self.items:
            return pd.DataFrame(columns=CALIDAD_COLUMNS)
        return pd.DataFrame(self.items, columns=CALIDAD_COLUMNS)

    def to_payload(self):
        return {
            'items': self.items,
            'tiene_alertas': bool(self.items),
            'total_alertas': len(self.items),
            'filas_afectadas': sum(int(i.get('cantidad') or 0) for i in self.items),
        }

    @classmethod
    def from_dataframe(cls, df):
        report = cls()
        if df is None or df.empty:
            return report
        for _, row in df.iterrows():
            try:
                cantidad = int(float(row.get('cantidad') or 1))
            except (TypeError, ValueError):
                cantidad = 1
            report.add(
                archivo=str(row.get('archivo') or '—'),
                motivo=str(row.get('motivo') or ''),
                cantidad=cantidad,
                fecha=fmt_fecha(row.get('fecha')),
                detalle=str(row.get('detalle') or ''),
            )
        return report

    @classmethod
    def empty_payload(cls):
        return cls().to_payload()


def leer_hoja_calidad(file_bytes):
    try:
        file_bytes.seek(0)
        xl = pd.ExcelFile(file_bytes)
        if CALIDAD_SHEET not in xl.sheet_names:
            return QualityReport()
        return QualityReport.from_dataframe(xl.parse(CALIDAD_SHEET))
    except Exception:
        return QualityReport()


def leer_hoja_datos(file_bytes):
    file_bytes.seek(0)
    xl = pd.ExcelFile(file_bytes)
    for name in xl.sheet_names:
        if name != CALIDAD_SHEET:
            return xl.parse(name)
    return xl.parse(xl.sheet_names[0])


def escribir_consolidado(df, report):
    """Escribe Datos (+ Calidad si hay alertas). Si falla el libro doble, cae al Excel simple."""
    import io

    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Datos')
            if report and report.items:
                report.to_dataframe().to_excel(writer, index=False, sheet_name=CALIDAD_SHEET)
        buffer.seek(0)
        return buffer
    except Exception:
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)
        return buffer


def agrupar_por_archivo(df):
    if df is None or df.empty:
        return []
    if 'ARCHIVO_ORIGEN' not in df.columns:
        return [('Reporte_Consolidado.xlsx', df)]
    grupos = []
    for archivo, subset in df.groupby(df['ARCHIVO_ORIGEN'].fillna('Reporte_Consolidado.xlsx')):
        grupos.append((str(archivo), subset))
    return grupos
