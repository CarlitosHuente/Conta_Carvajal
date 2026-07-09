from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import AsientoContable, DocumentoCompraRCV
from .rcv_sync import liberar_documentos_rcv_de_asiento
from .rcv_sugerencias import sincronizar_inteligencia_proveedores


@receiver(pre_delete, sender=AsientoContable)
def asiento_eliminado_liberar_rcv(sender, instance, **kwargs):
    empresa_ids = set(
        DocumentoCompraRCV.objects.filter(asiento=instance).values_list('empresa_id', flat=True)
    )
    liberar_documentos_rcv_de_asiento(instance)
    for empresa_id in empresa_ids:
        sincronizar_inteligencia_proveedores(empresa_id=empresa_id)
