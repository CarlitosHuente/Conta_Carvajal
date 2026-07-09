"""Vistas RCV compras y proveedores globales."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Empresa
from core.permissions import ensure_empresa_operativa, require_access

from .models import (
    CuentaContable, DocumentoCompraRCV, EmpresaProveedor,
    ImportacionRCVCompra, ProveedorGlobal,
)
from .rcv_centralizacion import contabilizar_documentos_rcv
from .rcv_import import importar_csv_rcv_compra
from .rcv_parser import inferir_periodo_desde_nombre
from .rcv_sugerencias import (
    cuentas_gasto_qs, sugerir_cuenta_gasto, sugerir_cuentas_para_proveedores,
    sincronizar_inteligencia_proveedores,
)
from .rcv_sync import (
    eliminar_importacion_rcv,
    reconciliar_documentos_rcv_huérfanos,
    revertir_contabilizacion_importacion,
)


def _empresa_rcv(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return None, redirect_response
    empresa = get_object_or_404(Empresa, id=empresa_id)
    return empresa, None


@login_required
@require_access('contabilidad', 'f29', 'ver')
def rcv_lista_view(request):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    importaciones = ImportacionRCVCompra.objects.filter(empresa=empresa).prefetch_related('documentos')
    return render(request, 'contabilidad/rcv/lista.html', {
        'empresa': empresa,
        'importaciones': importaciones,
    })


@login_required
@require_access('contabilidad', 'f29', 'crear')
def rcv_subir_view(request):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    if request.method == 'GET':
        return render(request, 'contabilidad/rcv/subir.html', {'empresa': empresa})

    archivo = request.FILES.get('archivo_csv')
    if not archivo:
        messages.error(request, 'Selecciona un archivo CSV del SII.')
        return render(request, 'contabilidad/rcv/subir.html', {'empresa': empresa})

    mes = request.POST.get('mes')
    ano = request.POST.get('ano')
    mes_inf, ano_inf = inferir_periodo_desde_nombre(archivo.name)
    try:
        mes = int(mes or mes_inf)
        ano = int(ano or ano_inf)
    except (TypeError, ValueError):
        messages.error(request, 'Indica mes y año del período RCV.')
        return render(request, 'contabilidad/rcv/subir.html', {'empresa': empresa})

    try:
        contenido = archivo.read()
        importacion, nuevas, duplicadas = importar_csv_rcv_compra(
            empresa, contenido, archivo.name, mes, ano, usuario=request.user,
        )
    except ValueError as e:
        messages.error(request, str(e))
        return render(request, 'contabilidad/rcv/subir.html', {'empresa': empresa})

    if nuevas == 0:
        messages.warning(
            request,
            f'No se importaron documentos nuevos. {duplicadas} ya existían en el sistema.',
        )
        if duplicadas and importacion.documentos.exists() is False:
            importacion.delete()
            return redirect('contabilidad:rcv_lista')
    else:
        messages.success(
            request,
            f'Importados {nuevas} documentos. Omitidos {duplicadas} duplicados.',
        )

    return redirect('contabilidad:rcv_preview', pk=importacion.pk)


@login_required
@require_access('contabilidad', 'f29', 'ver')
def rcv_preview_view(request, pk):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    importacion = get_object_or_404(ImportacionRCVCompra, pk=pk, empresa=empresa)
    reconciliar_documentos_rcv_huérfanos(importacion_id=importacion.pk)

    filtro = request.GET.get('estado', 'pendiente')
    documentos = importacion.documentos.select_related('proveedor', 'cuenta_gasto', 'asiento').order_by(
        'fecha_docto', 'folio',
    )
    if filtro in ('pendiente', 'contabilizada', 'omitida', 'todos'):
        if filtro == 'pendiente':
            documentos = documentos.filter(
                Q(estado='pendiente') | Q(estado='contabilizada', asiento__isnull=True),
            )
        elif filtro == 'contabilizada':
            documentos = documentos.filter(estado='contabilizada', asiento__isnull=False)
        elif filtro == 'omitida':
            documentos = documentos.filter(estado='omitida')

    cuentas_gasto = cuentas_gasto_qs(empresa)
    docs_list = list(documentos)
    pendientes = [d for d in docs_list if d.estado == 'pendiente']
    sugerencias_por_prov = sugerir_cuentas_para_proveedores(
        empresa, [d.proveedor_id for d in pendientes],
    )
    sugerencias = {}
    for doc in pendientes:
        cuenta, fuente, detalle = sugerencias_por_prov.get(doc.proveedor_id, (None, '', ''))
        sugerencias[doc.id] = {'cuenta': cuenta, 'fuente': fuente, 'detalle': detalle}

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'asignar_masivo':
            cuenta_id = request.POST.get('cuenta_masiva')
            ids = request.POST.getlist('doc_ids')
            if cuenta_id and ids:
                CuentaContable.objects.get(pk=cuenta_id, empresa=empresa)
                DocumentoCompraRCV.objects.filter(
                    pk__in=ids, importacion=importacion, estado='pendiente',
                ).update(cuenta_gasto_id=cuenta_id)
                messages.success(request, f'Cuenta asignada a {len(ids)} documento(s).')
            return redirect('contabilidad:rcv_preview', pk=pk)

        if accion == 'guardar_cuentas':
            for doc in documentos.filter(estado='pendiente'):
                key = f'cuenta_{doc.id}'
                cuenta_id = request.POST.get(key)
                if cuenta_id:
                    doc.cuenta_gasto_id = int(cuenta_id)
                    doc.save(update_fields=['cuenta_gasto'])
            messages.success(request, 'Cuentas actualizadas.')
            return redirect('contabilidad:rcv_preview', pk=pk)

        if accion == 'omitir':
            ids = request.POST.getlist('doc_ids')
            DocumentoCompraRCV.objects.filter(
                pk__in=ids, importacion=importacion, estado='pendiente',
            ).update(estado='omitida')
            messages.info(request, f'{len(ids)} documento(s) omitidos.')
            return redirect('contabilidad:rcv_preview', pk=pk)

        if accion == 'contabilizar':
            ids = request.POST.getlist('doc_ids')
            for doc in DocumentoCompraRCV.objects.filter(pk__in=ids, estado='pendiente'):
                key = f'cuenta_{doc.id}'
                cuenta_id = request.POST.get(key) or doc.cuenta_gasto_id
                if cuenta_id:
                    doc.cuenta_gasto_id = int(cuenta_id)
                    doc.save(update_fields=['cuenta_gasto'])

            docs = list(
                DocumentoCompraRCV.objects.filter(
                    pk__in=ids, importacion=importacion, estado='pendiente',
                ).select_related('proveedor', 'cuenta_gasto', 'importacion', 'empresa')
            )
            creados, errores = contabilizar_documentos_rcv(docs)
            if creados:
                messages.success(request, f'Contabilizados {len(creados)} documento(s).')
            for doc, err in errores:
                messages.error(request, f'Doc {doc.folio}: {err}')
            return redirect('contabilidad:rcv_preview', pk=pk)

    for doc in docs_list:
        sug = sugerencias.get(doc.id, {})
        doc.sugerencia = sug
        if not doc.cuenta_gasto_id and sug.get('cuenta'):
            doc.cuenta_sugerida_id = sug['cuenta'].id
        else:
            doc.cuenta_sugerida_id = doc.cuenta_gasto_id

    return render(request, 'contabilidad/rcv/preview.html', {
        'importacion': importacion,
        'documentos': docs_list,
        'cuentas_gasto': cuentas_gasto,
        'filtro': filtro,
        'pendientes': importacion.pendientes,
        'contabilizados': importacion.contabilizados,
        'omitidos': importacion.documentos.filter(estado='omitida').count(),
    })


@login_required
@require_access('contabilidad', 'f29', 'crear')
def rcv_revertir_view(request, pk):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    importacion = get_object_or_404(ImportacionRCVCompra, pk=pk, empresa=empresa)
    if request.method != 'POST':
        return redirect('contabilidad:rcv_preview', pk=pk)

    n = revertir_contabilizacion_importacion(importacion)
    messages.success(
        request,
        f'Se revirtieron {n} contabilización(es). Los documentos quedaron pendientes.',
    )
    return redirect('contabilidad:rcv_preview', pk=pk)


@login_required
@require_access('contabilidad', 'f29', 'crear')
def rcv_eliminar_view(request, pk):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    importacion = get_object_or_404(ImportacionRCVCompra, pk=pk, empresa=empresa)
    if request.method != 'POST':
        return redirect('contabilidad:rcv_lista')

    nombre = eliminar_importacion_rcv(importacion)
    messages.success(request, f'Importación RCV eliminada: {nombre}.')
    return redirect('contabilidad:rcv_lista')


@login_required
def contabilidad_completa_toggle_view(request):
    if request.method != 'POST':
        return redirect('contabilidad:hub')

    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    empresa.contabilidad_completa = request.POST.get('contabilidad_completa') == 'on'
    empresa.save(update_fields=['contabilidad_completa'])
    estado = 'activada' if empresa.contabilidad_completa else 'desactivada'
    messages.success(request, f'Contabilidad completa (RCV) {estado}.')
    return redirect('contabilidad:hub')


@login_required
def proveedor_global_lista_view(request):
    if request.user.perfil.rol != 'admin' and not request.user.is_superuser:
        messages.error(request, 'Solo administradores pueden ver el catálogo global de proveedores.')
        return redirect('contabilidad:hub')

    q = request.GET.get('q', '').strip()
    proveedores = ProveedorGlobal.objects.annotate(
        num_empresas=Count('vinculos_empresa', distinct=True),
        num_documentos=Count('documentos_compra', distinct=True),
    )
    if q:
        proveedores = proveedores.filter(Q(razon_social__icontains=q) | Q(rut__icontains=q))

    return render(request, 'contabilidad/proveedores/global_lista.html', {
        'proveedores': proveedores.order_by('razon_social')[:500],
        'q': q,
    })


@login_required
def proveedor_global_detalle_view(request, pk):
    if request.user.perfil.rol != 'admin' and not request.user.is_superuser:
        messages.error(request, 'Acceso denegado.')
        return redirect('contabilidad:hub')

    proveedor = get_object_or_404(ProveedorGlobal, pk=pk)
    if request.method == 'POST':
        proveedor.razon_social = request.POST.get('razon_social', proveedor.razon_social).strip()
        proveedor.rubro = request.POST.get('rubro', proveedor.rubro)
        proveedor.notas = request.POST.get('notas', '')
        proveedor.save()
        messages.success(request, 'Proveedor actualizado.')
        return redirect('contabilidad:proveedor_global_detalle', pk=pk)

    vinculos = proveedor.vinculos_empresa.select_related('empresa', 'cuenta_gasto_habitual')
    stats = proveedor.stats_cuentas.select_related('cuenta', 'empresa').order_by('-contador')[:20]
    totales_empresa = (
        proveedor.documentos_compra.values('empresa__razon_social')
        .annotate(total=Sum('monto_total'), cantidad=Count('id'))
        .order_by('-total')
    )

    return render(request, 'contabilidad/proveedores/global_detalle.html', {
        'proveedor': proveedor,
        'vinculos': vinculos,
        'stats': stats,
        'totales_empresa': totales_empresa,
    })


@login_required
@require_access('contabilidad', 'f29', 'ver')
def proveedor_empresa_lista_view(request):
    empresa, redirect_response = _empresa_rcv(request)
    if redirect_response:
        return redirect_response

    vinculos = EmpresaProveedor.objects.filter(empresa=empresa).select_related(
        'proveedor', 'cuenta_gasto_habitual',
    ).order_by('proveedor__razon_social')

    return render(request, 'contabilidad/proveedores/empresa_lista.html', {
        'empresa': empresa,
        'vinculos': vinculos,
    })
