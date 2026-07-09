"""Generación de asientos contables por documento RCV."""

from datetime import date

from django.db import transaction

from .models import AsientoContable, CuentaContable, LineaAsiento
from .auxiliares import aux_rcv_documento, crear_linea_asiento
from .rcv_sugerencias import registrar_uso_cuenta


class RCVCentralizacionError(Exception):
    pass


def fecha_contabilizacion_rcv(documento):
    """
    Fecha del asiento según periodo del archivo RCV.
    Documentos con fecha de emisión en otro mes (ej. dic. recepcionado en ene.)
    se contabilizan el día 1 del mes del RCV para cuadrar con la centralización.
    """
    if documento.fuera_periodo:
        imp = documento.importacion
        return date(imp.ano, imp.mes, 1)
    return documento.fecha_docto


def _cuenta_empresa(empresa, codigo, nombre_fallback=None):
    try:
        return CuentaContable.objects.get(empresa=empresa, codigo=codigo)
    except CuentaContable.DoesNotExist as exc:
        raise RCVCentralizacionError(
            f'Falta la cuenta {codigo} ({nombre_fallback or codigo}) en el plan de la empresa.'
        ) from exc


def cuentas_sistema_rcv(empresa):
    return {
        'proveedores': _cuenta_empresa(empresa, '2.01.01', 'Proveedores'),
        'iva_cf': _cuenta_empresa(empresa, '1.01.05', 'IVA Crédito Fiscal'),
    }


@transaction.atomic
def contabilizar_documento_rcv(documento):
    """Crea asiento para un DocumentoCompraRCV pendiente."""
    if documento.estado == 'contabilizada':
        raise RCVCentralizacionError('El documento ya está contabilizado.')
    if not documento.cuenta_gasto_id:
        raise RCVCentralizacionError('Debe asignarse una cuenta de gasto o existencia.')

    empresa = documento.empresa
    cuentas = cuentas_sistema_rcv(empresa)
    gasto = documento.cuenta_gasto
    monto_gasto = documento.monto_gasto + documento.monto_otro_impuesto
    iva = documento.monto_iva_recuperable
    total = documento.monto_total

    if total <= 0 and monto_gasto <= 0:
        raise RCVCentralizacionError('El documento no tiene montos para contabilizar.')

    tipo_doc_label = 'NC' if documento.es_nota_credito else 'Fact'
    glosa = (
        f'RCV {tipo_doc_label} {documento.tipo_doc}-{documento.folio} '
        f'{documento.proveedor.razon_social}'
    )[:255]

    fecha_asiento = fecha_contabilizacion_rcv(documento)
    aux_prov = aux_rcv_documento(documento)

    asiento = AsientoContable.objects.create(
        empresa=empresa,
        fecha=fecha_asiento,
        glosa=glosa,
        tipo_asiento='rcv',
        origen_importacion_rcv=documento.importacion,
    )

    if documento.es_nota_credito:
        if total > 0:
            crear_linea_asiento(asiento, cuentas['proveedores'], debe=total, haber=0, aux=aux_prov)
        if monto_gasto > 0:
            LineaAsiento.objects.create(asiento=asiento, cuenta=gasto, debe=0, haber=monto_gasto)
        if iva > 0:
            LineaAsiento.objects.create(asiento=asiento, cuenta=cuentas['iva_cf'], debe=0, haber=iva)
    else:
        if monto_gasto > 0:
            LineaAsiento.objects.create(asiento=asiento, cuenta=gasto, debe=monto_gasto, haber=0)
        if iva > 0:
            LineaAsiento.objects.create(asiento=asiento, cuenta=cuentas['iva_cf'], debe=iva, haber=0)
        if total > 0:
            crear_linea_asiento(asiento, cuentas['proveedores'], debe=0, haber=total, aux=aux_prov)

    total_debe = sum(l.debe for l in asiento.lineas.all())
    total_haber = sum(l.haber for l in asiento.lineas.all())
    if total_debe != total_haber:
        raise RCVCentralizacionError(
            f'Asiento descuadrado: Debe ${total_debe:,} vs Haber ${total_haber:,}.'
        )

    documento.asiento = asiento
    documento.estado = 'contabilizada'
    documento.save(update_fields=['asiento', 'estado'])

    registrar_uso_cuenta(empresa, documento.proveedor, gasto, fecha_asiento)
    return asiento


@transaction.atomic
def contabilizar_documentos_rcv(documentos):
    """Contabiliza varios documentos; retorna (creados, errores)."""
    creados = []
    errores = []
    for doc in documentos:
        try:
            asiento = contabilizar_documento_rcv(doc)
            creados.append((doc, asiento))
        except RCVCentralizacionError as e:
            errores.append((doc, str(e)))
    return creados, errores
