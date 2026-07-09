from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import AsientoContable
from .rcv_sync import liberar_documentos_rcv_de_asiento


@receiver(pre_delete, sender=AsientoContable)
def asiento_eliminado_liberar_rcv(sender, instance, **kwargs):
    liberar_documentos_rcv_de_asiento(instance)
