"""Tests parser RCV SII."""

from django.test import SimpleTestCase

from contabilidad.rcv_parser import inferir_periodo_desde_nombre, normalizar_rut, parsear_csv_rcv_compras


SAMPLE_HEADER = (
    'Nro;Tipo Doc;Tipo Compra;RUT Proveedor;Razon Social;Folio;Fecha Docto;Fecha Recepcion;'
    'Fecha Acuse;Monto Exento;Monto Neto;Monto IVA Recuperable;Monto Iva No Recuperable;'
    'Codigo IVA No Rec.;Monto Total;Monto Neto Activo Fijo;IVA Activo Fijo;IVA uso Comun;'
    'Impto. Sin Derecho a Credito;IVA No Retenido;Tabacos Puros;Tabacos Cigarrillos;'
    'Tabacos Elaborados;NCE o NDE sobre Fact. de Compra;Codigo Otro Impuesto;Valor Otro Impuesto;'
    'Tasa Otro Impuesto\n'
)
SAMPLE_ROW = (
    '1;33;Del Giro;76389383-9;DROGUERIA GLOBAL PHARMA SPA;1037877;24/12/2025;24/12/2025 09:59:40;;'
    '0;69390;13184;;;82574;;;;;0;;;;0;;;;\n'
)


class RCVParserTests(SimpleTestCase):
    def test_normalizar_rut(self):
        self.assertEqual(normalizar_rut('76.389.383-9'), '76389383-9')

    def test_inferir_periodo(self):
        mes, ano = inferir_periodo_desde_nombre('RCV_COMPRA_REGISTRO_18243018-8_202601.csv')
        self.assertEqual((mes, ano), (1, 2026))

    def test_parsear_fila(self):
        filas = parsear_csv_rcv_compras(SAMPLE_HEADER + SAMPLE_ROW)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['tipo_doc'], 33)
        self.assertEqual(filas[0]['monto_neto'], 69390)
        self.assertEqual(filas[0]['monto_total'], 82574)
