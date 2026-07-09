"""Campos auxiliares por línea de asiento (RUT, documento, centro de costo)."""

from collections import defaultdict

from .models import LineaAsiento


def aux_rcv_documento(documento):
    return {
        'auxiliar_rut': documento.proveedor.rut,
        'auxiliar_doc': f'{documento.tipo_doc}-{documento.folio}',
        'centro_costo': '',
    }


def aux_desde_linea(linea):
    rut = (linea.auxiliar_rut or '').strip()
    doc = (linea.auxiliar_doc or '').strip()
    if rut or doc:
        return {
            'auxiliar_rut': rut,
            'auxiliar_doc': doc,
            'centro_costo': (linea.centro_costo or '').strip(),
        }
    doc_rcv = getattr(linea.asiento, 'documento_rcv_compra', None)
    if doc_rcv:
        return aux_rcv_documento(doc_rcv)
    return {'auxiliar_rut': '', 'auxiliar_doc': '', 'centro_costo': ''}


def crear_linea_asiento(asiento, cuenta, debe=0, haber=0, aux=None):
    extra = aux or {}
    return LineaAsiento.objects.create(
        asiento=asiento,
        cuenta=cuenta,
        debe=debe,
        haber=haber,
        auxiliar_rut=extra.get('auxiliar_rut', '') or '',
        auxiliar_doc=extra.get('auxiliar_doc', '') or '',
        centro_costo=extra.get('centro_costo', '') or '',
    )


def etiqueta_auxiliar(linea):
    aux = aux_desde_linea(linea)
    partes = [p for p in (aux['auxiliar_rut'], aux['auxiliar_doc']) if p]
    if aux.get('centro_costo'):
        partes.append(f"CC:{aux['centro_costo']}")
    return ' · '.join(partes)
