"""Tests fecha de asiento RCV."""

from datetime import date
from unittest.mock import Mock

from django.test import SimpleTestCase

from contabilidad.rcv_centralizacion import fecha_contabilizacion_rcv


class FechaContabilizacionRCVTests(SimpleTestCase):
    def test_fuera_periodo_usa_primer_dia_mes_rcv(self):
        doc = Mock(
            fuera_periodo=True,
            fecha_docto=date(2025, 12, 24),
            importacion=Mock(mes=1, ano=2026),
        )
        self.assertEqual(fecha_contabilizacion_rcv(doc), date(2026, 1, 1))

    def test_mismo_periodo_usa_fecha_docto(self):
        doc = Mock(
            fuera_periodo=False,
            fecha_docto=date(2026, 1, 15),
            importacion=Mock(mes=1, ano=2026),
        )
        self.assertEqual(fecha_contabilizacion_rcv(doc), date(2026, 1, 15))
