"""Tests sincronización RCV al eliminar asientos."""

from django.test import TestCase

from contabilidad.models import AsientoContable, DocumentoCompraRCV
from contabilidad.rcv_sync import reconciliar_documentos_rcv_huérfanos
from core.models import Empresa
from contabilidad.models import ImportacionRCVCompra, ProveedorGlobal


class RCVSyncTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            rut='11111111-1', razon_social='Test', correo_contacto='t@test.cl',
        )
        self.proveedor = ProveedorGlobal.objects.create(rut='22222222-2', razon_social='Prov')
        self.importacion = ImportacionRCVCompra.objects.create(
            empresa=self.empresa, mes=1, ano=2026, filas_nuevas=1,
        )
        self.asiento = AsientoContable.objects.create(
            empresa=self.empresa,
            fecha='2026-01-15',
            glosa='RCV test',
            tipo_asiento='rcv',
            origen_importacion_rcv=self.importacion,
        )
        self.documento = DocumentoCompraRCV.objects.create(
            empresa=self.empresa,
            importacion=self.importacion,
            proveedor=self.proveedor,
            tipo_doc=33,
            folio=100,
            fecha_docto='2026-01-10',
            monto_total=1000,
            estado='contabilizada',
            asiento=self.asiento,
        )

    def test_eliminar_asiento_deja_documento_pendiente(self):
        self.asiento.delete()
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, 'pendiente')
        self.assertIsNone(self.documento.asiento_id)

    def test_reconciliar_huérfanos(self):
        self.documento.asiento = None
        self.documento.save(update_fields=['asiento'])
        n = reconciliar_documentos_rcv_huérfanos(importacion_id=self.importacion.pk)
        self.assertEqual(n, 1)
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.estado, 'pendiente')
