"""Tests auxiliares y pagos agrupados por RUT."""

from django.test import TestCase

from core.models import Empresa
from contabilidad.auxiliares import aux_rcv_documento, etiqueta_auxiliar
from contabilidad.cobros_pagos import registrar_pago_o_cobro
from contabilidad.models import (
    AsientoContable,
    CuentaContable,
    LineaAsiento,
    AccionRapida,
    CuentaAccionRapida,
    LineaAccionRapida,
)
from unittest.mock import Mock


class AuxiliarLineaTests(TestCase):
    def test_etiqueta_auxiliar(self):
        cuenta = Mock(codigo='2.01.01')
        asiento = Mock(documento_rcv_compra=None)
        linea = Mock(
            auxiliar_rut='76123456-7',
            auxiliar_doc='33-100',
            centro_costo='ADM',
            cuenta=cuenta,
            asiento=asiento,
        )
        self.assertEqual(etiqueta_auxiliar(linea), '76123456-7 · 33-100 · CC:ADM')

    def test_aux_rcv_documento(self):
        doc = Mock(
            proveedor=Mock(rut='76123456-7'),
            tipo_doc=33,
            folio=1037877,
        )
        aux = aux_rcv_documento(doc)
        self.assertEqual(aux['auxiliar_rut'], '76123456-7')
        self.assertEqual(aux['auxiliar_doc'], '33-1037877')


class PagoMasivoPorRutTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            razon_social='Test SPA', rut='76111111-1', correo_contacto='test@test.cl',
        )
        self.proveedores = CuentaContable.objects.create(
            empresa=self.empresa, codigo='2.01.01', nombre='Proveedores',
            tipo='pasivo', requiere_auxiliar=True,
        )
        self.banco = CuentaContable.objects.create(
            empresa=self.empresa, codigo='1.01.02', nombre='Banco',
            tipo='activo', subtipo_operacion='banco',
        )
        accion = AccionRapida.objects.create(
            empresa=self.empresa, nombre='Pagar', tipo='pago', lado_pendiente='haber',
        )
        LineaAccionRapida.objects.create(accion=accion, cuenta=self.banco, orden=0)
        CuentaAccionRapida.objects.create(cuenta=self.proveedores, accion=accion, orden=0)

    def _linea_factura(self, rut, doc, monto):
        asiento = AsientoContable.objects.create(
            empresa=self.empresa, fecha='2026-01-10', glosa=f'Fact {doc}', tipo_asiento='rcv',
        )
        return LineaAsiento.objects.create(
            asiento=asiento,
            cuenta=self.proveedores,
            debe=0,
            haber=monto,
            auxiliar_rut=rut,
            auxiliar_doc=doc,
        )

    def test_pago_cuatro_ruts_genera_ocho_lineas(self):
        lineas = [
            self._linea_factura('11111111-1', '33-1', 10000),
            self._linea_factura('22222222-2', '33-2', 20000),
            self._linea_factura('33333333-3', '33-3', 30000),
            self._linea_factura('44444444-4', '33-4', 40000),
        ]
        asiento, total, tipo = registrar_pago_o_cobro(
            self.empresa,
            self.proveedores,
            lineas,
            [{'cuenta_id': self.banco.id, 'monto': 100000}],
            '2026-01-15',
        )
        self.assertEqual(total, 100000)
        self.assertEqual(asiento.lineas.count(), 8)
        debe_prov = asiento.lineas.filter(cuenta=self.proveedores, debe__gt=0)
        haber_banco = asiento.lineas.filter(cuenta=self.banco, haber__gt=0)
        self.assertEqual(debe_prov.count(), 4)
        self.assertEqual(haber_banco.count(), 4)
        ruts_banco = {l.auxiliar_rut for l in haber_banco}
        self.assertEqual(len(ruts_banco), 4)

    def test_pago_mismo_rut_una_linea_banco(self):
        lineas = [
            self._linea_factura('11111111-1', '33-10', 50000),
            self._linea_factura('11111111-1', '33-11', 30000),
        ]
        asiento, total, _ = registrar_pago_o_cobro(
            self.empresa,
            self.proveedores,
            lineas,
            [{'cuenta_id': self.banco.id, 'monto': 80000}],
            '2026-01-15',
        )
        self.assertEqual(asiento.lineas.filter(cuenta=self.proveedores).count(), 2)
        self.assertEqual(asiento.lineas.filter(cuenta=self.banco).count(), 1)
        self.assertEqual(total, 80000)
