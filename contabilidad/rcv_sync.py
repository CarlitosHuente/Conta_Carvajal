"""Sincronización RCV ↔ libro diario (una sola fuente de verdad)."""

from django.db import transaction
from django.db.models import Q

from .models import AsientoContable, DocumentoCompraRCV, ImportacionRCVCompra
from .rcv_sugerencias import sincronizar_inteligencia_proveedores


def reconciliar_documentos_rcv_huérfanos(*, empresa_id=None, importacion_id=None):
    """
    Documentos marcados contabilizados pero sin asiento (ej. asiento borrado en admin).
    """
    qs = DocumentoCompraRCV.objects.filter(estado='contabilizada', asiento__isnull=True)
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    if importacion_id:
        qs = qs.filter(importacion_id=importacion_id)
    return qs.update(estado='pendiente')


def liberar_documentos_rcv_de_asiento(asiento):
    """Vuelve a pendiente los documentos RCV ligados a un asiento."""
    return DocumentoCompraRCV.objects.filter(asiento=asiento).update(
        estado='pendiente', asiento=None,
    )


@transaction.atomic
def revertir_contabilizacion_importacion(importacion):
    """Elimina asientos RCV del lote y deja todos los documentos pendientes."""
    docs = list(
        importacion.documentos.filter(estado='contabilizada').exclude(asiento__isnull=True)
    )
    asiento_ids = [d.asiento_id for d in docs]
    if asiento_ids:
        AsientoContable.objects.filter(pk__in=asiento_ids).delete()
    reconciliar_documentos_rcv_huérfanos(importacion_id=importacion.pk)
    sincronizar_inteligencia_proveedores(empresa_id=importacion.empresa_id)
    return len(docs)


@transaction.atomic
def eliminar_importacion_rcv(importacion):
    """Elimina el lote RCV, sus documentos y los asientos contables generados."""
    asiento_ids = list(
        importacion.documentos.exclude(asiento__isnull=True).values_list('asiento_id', flat=True)
    )
    if asiento_ids:
        AsientoContable.objects.filter(pk__in=asiento_ids).delete()
    if asiento_ids:
        AsientoContable.objects.filter(pk__in=asiento_ids).delete()
    reconciliar_documentos_rcv_huérfanos(importacion_id=importacion.pk)
    empresa_id = importacion.empresa_id
    nombre = str(importacion)
    importacion.delete()
    sincronizar_inteligencia_proveedores(empresa_id=empresa_id)
    return nombre
