"""Importación de lotes RCV compras."""

from django.db import transaction

from .models import (
    DocumentoCompraRCV, EmpresaProveedor, ImportacionRCVCompra, ProveedorGlobal,
)
from .rcv_parser import documento_ya_existe, normalizar_rut, parsear_csv_rcv_compras
from .rcv_sugerencias import sugerir_cuenta_gasto


def obtener_o_crear_proveedor_global(rut, razon_social):
    rut = normalizar_rut(rut)
    proveedor, created = ProveedorGlobal.objects.get_or_create(
        rut=rut,
        defaults={'razon_social': razon_social, 'razon_social_sii': razon_social},
    )
    if not created and razon_social and len(razon_social) > len(proveedor.razon_social_sii or ''):
        proveedor.razon_social_sii = razon_social
        if not proveedor.razon_social or proveedor.razon_social == rut:
            proveedor.razon_social = razon_social
        proveedor.save(update_fields=['razon_social_sii', 'razon_social'])
    return proveedor


@transaction.atomic
def importar_csv_rcv_compra(empresa, contenido, nombre_archivo, mes, ano, usuario=None):
    filas = parsear_csv_rcv_compras(contenido)
    importacion = ImportacionRCVCompra.objects.create(
        empresa=empresa,
        mes=mes,
        ano=ano,
        nombre_archivo=nombre_archivo,
        total_filas=len(filas),
        usuario=usuario,
    )

    nuevas = 0
    duplicadas = 0

    for fila in filas:
        proveedor = obtener_o_crear_proveedor_global(fila['rut_proveedor'], fila['razon_social'])
        EmpresaProveedor.objects.get_or_create(empresa=empresa, proveedor=proveedor)

        if documento_ya_existe(empresa.id, fila['tipo_doc'], fila['folio'], proveedor.id):
            duplicadas += 1
            continue

        fuera = fila['fecha_docto'].month != mes or fila['fecha_docto'].year != ano
        cuenta, fuente, detalle = sugerir_cuenta_gasto(empresa, proveedor)

        DocumentoCompraRCV.objects.create(
            empresa=empresa,
            importacion=importacion,
            proveedor=proveedor,
            tipo_doc=fila['tipo_doc'],
            tipo_compra=fila['tipo_compra'],
            folio=fila['folio'],
            fecha_docto=fila['fecha_docto'],
            fecha_recepcion=fila['fecha_recepcion'],
            monto_exento=fila['monto_exento'],
            monto_neto=fila['monto_neto'],
            monto_iva_recuperable=fila['monto_iva_recuperable'],
            monto_otro_impuesto=fila['monto_otro_impuesto'],
            monto_total=fila['monto_total'],
            razon_social_csv=fila['razon_social'],
            cuenta_gasto=cuenta,
            fuera_periodo=fuera,
        )
        nuevas += 1

    importacion.filas_nuevas = nuevas
    importacion.filas_duplicadas = duplicadas
    importacion.save(update_fields=['filas_nuevas', 'filas_duplicadas'])

    return importacion, nuevas, duplicadas
