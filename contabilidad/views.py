import os
import re
import json
import calendar
from django.core import signing
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.http import FileResponse, Http404, JsonResponse

from .extractor import extraer_datos_f29
from .centralizacion import calcular_asiento_desde_plantilla
from .models import (
    CodigoF29, DeclaracionF29, CuentaContable, PlantillaCentralizacion,
    LineaPlantilla, AsientoContable, LineaAsiento, AccionRapida, LineaAccionRapida,
    CuentaAccionRapida,
)
from .forms import CuentaContableForm
from core.models import Empresa
from core.permissions import require_access
from .plan_base import PLAN_CUENTAS_BASE, TIPO_NOMBRES, ORDEN_TIPOS
from .plan_export import serializar_plan_empresa, importar_acciones_plan


def _ruta_pdf_temporal_segura(filename):
    """Resuelve la ruta del PDF temporal validando que quede dentro de media/tmp."""
    tmp_dir = os.path.realpath(os.path.join(settings.MEDIA_ROOT, 'tmp'))
    ruta = os.path.realpath(os.path.join(tmp_dir, os.path.basename(filename)))
    if not ruta.startswith(tmp_dir + os.sep):
        raise Http404('Ruta no permitida')
    if not os.path.isfile(ruta):
        raise Http404('Archivo no encontrado')
    return ruta


@login_required
@require_access('contabilidad', 'f29', 'crear')
def f29_pdf_temporal_view(request, token):
    """Sirve el PDF temporal durante la revisión (producción no expone /media/ con DEBUG=False)."""
    try:
        data = signing.loads(token, max_age=3600)
        filename = data['f']
    except signing.BadSignature:
        raise Http404('Enlace de vista previa inválido o expirado')
    return FileResponse(
        open(_ruta_pdf_temporal_segura(filename), 'rb'),
        content_type='application/pdf',
    )


@login_required
@require_access('contabilidad', 'f29', 'ver')
def f29_lista_view(request):
    """Muestra el historial de F29 cargados según el rol del usuario."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para ver sus declaraciones.")
        return redirect('core:home')
    
    declaraciones = DeclaracionF29.objects.filter(empresa_id=empresa_id).order_by('-ano', '-mes').prefetch_related(
        Prefetch(
            'asientos_generados',
            queryset=AsientoContable.objects.select_related('origen_plantilla').order_by('id'),
        )
    )
    return render(request, 'contabilidad/f29_lista.html', {'declaraciones': declaraciones})

@login_required
@require_access('contabilidad', 'f29', 'crear')
def f29_subir_view(request):
    """Recibe el PDF, extrae los datos y renderiza la pantalla dividida de revisión."""
    if request.method == 'GET':
        return render(request, 'contabilidad/f29_subir.html')

    if request.method == 'POST' and request.FILES.get('archivo_pdf'):
        archivo = request.FILES['archivo_pdf']
        
        # 1. Crear carpeta temporal si no existe y guardar el archivo
        tmp_dir = os.path.join(settings.MEDIA_ROOT, 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        
        fs = FileSystemStorage(location=tmp_dir)
        filename = fs.save(archivo.name, archivo)
        ruta_absoluta = fs.path(filename)
        token_pdf = signing.dumps({'f': filename})
        url_pdf = reverse('contabilidad:f29_pdf_temporal', kwargs={'token': token_pdf})
        
        # 2. Extraer datos del PDF
        datos_extraidos, texto_completo = extraer_datos_f29(ruta_absoluta)
        
        # 3. Analizar códigos conocidos vs desconocidos
        codigos_encontrados = list(datos_extraidos['codigos'].keys())
        codigos_db = CodigoF29.objects.filter(codigo__in=codigos_encontrados)
        diccionario_db = {c.codigo: c.descripcion for c in codigos_db}
        
        codigos_para_template = []
        for cod, valor in datos_extraidos['codigos'].items():
            glosa_extraida = datos_extraidos.get('glosas', {}).get(cod, '')
            codigos_para_template.append({
                'codigo': cod,
                'valor': valor,
                'conocido': cod in diccionario_db,
                'descripcion': diccionario_db.get(cod, glosa_extraida) # Si es nuevo, sugerimos la glosa del PDF
            })
            
        # 4. Obtener empresas para asignar
        if request.user.perfil.rol == 'admin':
            empresas = Empresa.objects.all()
        else:
            empresas = Empresa.objects.filter(id=request.user.perfil.empresa_id)

        context = {
            'url_pdf': url_pdf,
            'ruta_absoluta': ruta_absoluta,
            'datos': datos_extraidos,
            'codigos_lista': codigos_para_template,
            'empresas': empresas,
            'texto_crudo': texto_completo, # Enviamos el texto tal como lo lee PyMuPDF
        }
        return render(request, 'contabilidad/f29_revisar.html', context)

@login_required
def f29_guardar_view(request):
    """Recibe los datos confirmados, guarda la declaración y elimina el PDF."""
    if request.method == 'POST':
        empresa_id = request.POST.get('empresa_id')
        mes = request.POST.get('mes')
        ano = request.POST.get('ano')
        folio = request.POST.get('folio')
        ruta_absoluta = request.POST.get('ruta_absoluta')
        
        # VALIDACIÓN CRÍTICA: Evitar folios duplicados
        if folio:
            # Buscamos si existe el folio en otra declaración (excluyendo la que estamos editando si fuera el caso)
            if DeclaracionF29.objects.filter(folio=folio).exclude(empresa_id=empresa_id, mes=mes, ano=ano).exists():
                messages.error(request, f"Error de Seguridad: El folio {folio} ya se encuentra registrado en el sistema. No se permiten duplicados.")
                return redirect('contabilidad:f29_subir')

        datos_json = {}
        
        # 1. Procesar los códigos extraídos del PDF (respetando los checkboxes)
        for key, value in request.POST.items():
            if key.startswith('valor_'):
                cod = key.split('_')[1]
                
                # Solo si el usuario dejó marcado el ticket de inclusión
                if request.POST.get(f'incluir_{cod}'):
                    datos_json[cod] = int(value)
                    
                    # Guardar nombre si el código es nuevo
                    desc = request.POST.get(f'desc_{cod}')
                    if desc and desc.strip():
                        CodigoF29.objects.get_or_create(codigo=cod, defaults={'descripcion': desc.strip()})
                        
        # 2. Procesar las filas agregadas manualmente mediante el botón
        codigos_manuales = request.POST.getlist('codigo_manual')
        descs_manuales = request.POST.getlist('desc_manual')
        valores_manuales = request.POST.getlist('valor_manual')
        
        for cod, desc, val in zip(codigos_manuales, descs_manuales, valores_manuales):
            cod = cod.strip()
            if cod and val:
                datos_json[cod] = int(val)
                if desc.strip():
                    CodigoF29.objects.get_or_create(codigo=cod, defaults={'descripcion': desc.strip()})
        
        # Buscamos el código 91 (Total a Pagar)
        total_a_pagar = datos_json.get('91', datos_json.get('091', 0))
        empresa = Empresa.objects.get(id=empresa_id)
        
        # Guardar en la base de datos
        declaracion, created = DeclaracionF29.objects.update_or_create(
            empresa=empresa, mes=mes, ano=ano,
            defaults={
                'folio': folio, 'total_a_pagar': total_a_pagar,
                'datos_extraidos': datos_json, 'estado': 'pendiente'
            }
        )
        
        # EJECUTAR MOTOR DE REGLAS
        declaracion.verificar_cuadratura()
        declaracion.save()

        # 5. MAGIA: Eliminamos el PDF temporal para ahorrar espacio
        if ruta_absoluta and os.path.exists(ruta_absoluta):
            os.remove(ruta_absoluta)
            
        messages.success(request, '¡F29 procesado exitosamente! Los datos se guardaron y el PDF temporal se eliminó.')
        return redirect('contabilidad:f29_lista')
        
    return redirect('contabilidad:f29_subir')

@login_required
def f29_detalle_view(request, pk):
    """Muestra el detalle de un F29 procesado usando los códigos legibles."""
    if request.user.perfil.rol == 'admin':
        f29 = get_object_or_404(DeclaracionF29, pk=pk)
    else:
        f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=request.user.perfil.empresa_id)

    asientos_f29 = f29.asientos_generados.select_related('origen_plantilla').order_by('id')
    return render(request, 'contabilidad/f29_detalle.html', {
        'f29': f29,
        'asientos_f29': asientos_f29,
    })

@login_required
def f29_eliminar_view(request, pk):
    """Elimina un F29 de la base de datos."""
    if request.method == 'POST':
        if request.user.perfil.rol == 'admin':
            f29 = get_object_or_404(DeclaracionF29, pk=pk)
        else:
            f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=request.user.perfil.empresa_id)
        f29.delete()
        messages.success(request, 'La declaración F29 fue eliminada exitosamente.')
    return redirect('contabilidad:f29_lista')

@login_required
def f29_recalcular_view(request, pk):
    """Vuelve a pasar el motor de reglas a un F29 ya guardado."""
    if request.method == 'POST':
        if request.user.perfil.rol == 'admin':
            f29 = get_object_or_404(DeclaracionF29, pk=pk)
        else:
            f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=request.user.perfil.empresa_id)
        f29.verificar_cuadratura()
        f29.save()
        messages.success(request, f'Reglas de cuadratura reaplicadas para el folio {f29.folio}.')
    return redirect('contabilidad:f29_lista')

@login_required
def f29_editar_view(request, pk):
    """Permite editar los montos y códigos de un F29 ya guardado sin re-subir el PDF."""
    if request.user.perfil.rol == 'admin':
        f29 = get_object_or_404(DeclaracionF29, pk=pk)
    else:
        f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=request.user.perfil.empresa_id)

    if request.method == 'POST':
        f29.mes = request.POST.get('mes')
        f29.ano = request.POST.get('ano')
        folio = request.POST.get('folio')
        
        if folio and DeclaracionF29.objects.filter(folio=folio).exclude(pk=f29.pk).exists():
            messages.error(request, f"Error: El folio {folio} ya está siendo utilizado por otra declaración.")
            return redirect('contabilidad:f29_editar', pk=f29.pk)
            
        f29.folio = folio
        datos_json = {}
        
        for key, value in request.POST.items():
            if key.startswith('valor_'):
                cod = key.split('_')[1]
                if request.POST.get(f'incluir_{cod}'):
                    datos_json[cod] = int(value)
                    desc = request.POST.get(f'desc_{cod}')
                    if desc and desc.strip():
                        CodigoF29.objects.get_or_create(codigo=cod, defaults={'descripcion': desc.strip()})
                        
        codigos_manuales = request.POST.getlist('codigo_manual')
        descs_manuales = request.POST.getlist('desc_manual')
        valores_manuales = request.POST.getlist('valor_manual')
        
        for cod, desc, val in zip(codigos_manuales, descs_manuales, valores_manuales):
            cod = cod.strip()
            if cod and val:
                datos_json[cod] = int(val)
                if desc.strip():
                    CodigoF29.objects.get_or_create(codigo=cod, defaults={'descripcion': desc.strip()})
                    
        f29.datos_extraidos = datos_json
        f29.total_a_pagar = datos_json.get('91', datos_json.get('091', 0))
        f29.verificar_cuadratura()
        f29.save()
        
        messages.success(request, 'Formulario 29 actualizado exitosamente.')
        return redirect('contabilidad:f29_lista')

    codigos_encontrados = list(f29.datos_extraidos.keys())
    codigos_db = {
        c.codigo: c.descripcion
        for c in CodigoF29.objects.filter(codigo__in=codigos_encontrados)
    }
    codigos_lista = [
        {
            'codigo': codigo,
            'valor': valor,
            'descripcion': codigos_db.get(str(codigo), f'Código {codigo} (Sin nombre)'),
        }
        for codigo, valor in f29.datos_extraidos.items()
    ]
    return render(request, 'contabilidad/f29_editar.html', {'f29': f29, 'codigos_lista': codigos_lista})


def _plantillas_ya_aplicadas(f29):
    return set(
        AsientoContable.objects.filter(origen_f29=f29, origen_plantilla__isnull=False)
        .values_list('origen_plantilla_id', flat=True)
    )


def _guardar_asiento_f29(f29, plantilla, fecha, glosa, calculo):
    asiento = AsientoContable.objects.create(
        empresa=f29.empresa,
        fecha=fecha,
        glosa=glosa,
        origen_f29=f29,
        origen_plantilla=plantilla,
        tipo_asiento='f29',
    )
    for lc in calculo['lineas_calculadas']:
        cuenta = CuentaContable.objects.get(empresa=f29.empresa, codigo=lc['cuenta_codigo'])
        LineaAsiento.objects.create(
            asiento=asiento,
            cuenta=cuenta,
            debe=lc['debe'],
            haber=lc['haber'],
        )
    return asiento


@login_required
def f29_centralizar_view(request, pk):
    """Genera uno o más asientos desde plantillas seleccionadas (compras, ventas, pago, etc.)."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')

    f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=empresa_id)
    plantillas = PlantillaCentralizacion.objects.filter(empresa_id=empresa_id, tipo_origen='f29')
    plantillas_aplicadas = _plantillas_ya_aplicadas(f29)
    asientos_existentes = f29.asientos_generados.select_related('origen_plantilla').order_by('id')

    ultimo_dia = calendar.monthrange(f29.ano, f29.mes)[1]
    fecha_sugerida = f"{f29.ano}-{f29.mes:02d}-{ultimo_dia:02d}"
    glosa_sugerida = f"F29 período {f29.mes:02d}/{f29.ano}"

    context = {
        'f29': f29,
        'plantillas': plantillas,
        'plantillas_aplicadas': plantillas_aplicadas,
        'asientos_existentes': asientos_existentes,
        'fecha_sugerida': fecha_sugerida,
        'glosa_sugerida': glosa_sugerida,
    }

    if request.method == 'POST':
        plantilla_ids = [int(x) for x in request.POST.getlist('plantilla_ids') if x.isdigit()]
        fecha = request.POST.get('fecha')
        glosa_base = request.POST.get('glosa', glosa_sugerida)
        confirmado = request.POST.get('confirmado') == 'true'

        context['fecha_sel'] = fecha
        context['glosa_sel'] = glosa_base
        context['plantilla_ids_sel'] = plantilla_ids

        if not plantilla_ids:
            messages.error(request, 'Selecciona al menos una plantilla de centralización.')
            return render(request, 'contabilidad/f29_centralizar.html', context)

        try:
            asientos_preview = []
            omitidas_sin_monto = []

            for plantilla_id in plantilla_ids:
                plantilla = get_object_or_404(PlantillaCentralizacion, id=plantilla_id, empresa_id=empresa_id)
                if plantilla.id in plantillas_aplicadas:
                    raise ValueError(
                        f'La plantilla «{plantilla.nombre}» ya fue centralizada para este F29. '
                        'Desmarca las ya aplicadas o elige otras.'
                    )

                calculo = calcular_asiento_desde_plantilla(plantilla, f29.datos_extraidos)
                if calculo is None:
                    omitidas_sin_monto.append(plantilla.nombre)
                    continue

                glosa_asiento = f"{plantilla.nombre} — {glosa_base}"
                calculo['glosa'] = glosa_asiento
                asientos_preview.append(calculo)

            if not asientos_preview:
                if omitidas_sin_monto:
                    messages.warning(
                        request,
                        'Ninguna plantilla seleccionada generó montos: '
                        + ', '.join(omitidas_sin_monto)
                        + '. Revisa los códigos del F29 o las fórmulas.',
                    )
                return render(request, 'contabilidad/f29_centralizar.html', context)

            if confirmado:
                creados = []
                with transaction.atomic():
                    for preview in asientos_preview:
                        asiento = _guardar_asiento_f29(
                            f29,
                            preview['plantilla'],
                            fecha,
                            preview['glosa'],
                            preview,
                        )
                        creados.append(asiento)

                ids = ', '.join(f'#{a.id}' for a in creados)
                msg = f'Se generaron {len(creados)} asiento(s): {ids}.'
                if omitidas_sin_monto:
                    msg += f' Omitidas sin monto: {", ".join(omitidas_sin_monto)}.'
                messages.success(request, msg)
                return redirect('contabilidad:f29_detalle', pk=f29.pk)

            context['mostrar_modal'] = True
            context['asientos_preview'] = asientos_preview
            context['omitidas_sin_monto'] = omitidas_sin_monto

        except ZeroDivisionError:
            messages.error(request, 'Error matemático: división por cero en alguna fórmula. Revisa los códigos del F29.')
        except Exception as e:
            messages.error(request, f'Fallo en la centralización: {str(e)}')

    return render(request, 'contabilidad/f29_centralizar.html', context)


@login_required
def contabilidad_hub_view(request):
    """Centro de navegación del módulo Contabilidad."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        messages.warning(request, 'Selecciona una empresa para acceder a Contabilidad.')
        return redirect('core:home')

    f29_count = DeclaracionF29.objects.filter(empresa=empresa_actual).count()
    asientos_count = AsientoContable.objects.filter(empresa=empresa_actual).count()
    cuentas_count = CuentaContable.objects.filter(empresa=empresa_actual).count()
    plantillas_count = PlantillaCentralizacion.objects.filter(empresa=empresa_actual).count()

    from .models import ImportacionRCVCompra, DocumentoCompraRCV
    rcv_count = ImportacionRCVCompra.objects.filter(empresa=empresa_actual).count()
    rcv_pendientes = DocumentoCompraRCV.objects.filter(
        empresa=empresa_actual, estado='pendiente',
    ).count()

    return render(request, 'contabilidad/hub.html', {
        'empresa': empresa_actual,
        'f29_count': f29_count,
        'asientos_count': asientos_count,
        'cuentas_count': cuentas_count,
        'plantillas_count': plantillas_count,
        'rcv_count': rcv_count,
        'rcv_pendientes': rcv_pendientes,
    })


# =====================================================================
# VISTAS DE PLAN DE CUENTAS
# =====================================================================

def _get_empresa_plan(request):
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return None
    return get_object_or_404(Empresa, id=empresa_id)


@login_required
def plan_cuentas_lista_view(request):
    """Muestra el plan de cuentas de la empresa seleccionada."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        messages.warning(request, "Por favor, selecciona una empresa para ver su Plan de Cuentas.")
        return redirect('core:home')

    cuentas = CuentaContable.objects.filter(empresa=empresa_actual).prefetch_related(
        'asignaciones_acciones__accion',
    )
    tiene_movimientos = AsientoContable.objects.filter(empresa=empresa_actual).exists()
    puede_vaciar_plan = cuentas.exists() and not tiene_movimientos

    return render(request, 'contabilidad/plan_cuentas/lista.html', {
        'cuentas': cuentas,
        'tiene_movimientos': tiene_movimientos,
        'puede_vaciar_plan': puede_vaciar_plan,
    })


@login_required
def plan_cuentas_crear_view(request):
    """Crea una nueva cuenta contable para una empresa específica."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        messages.warning(request, "Por favor, selecciona una empresa para agregarle una cuenta.")
        return redirect('core:home')

    if request.method == 'POST':
        form = CuentaContableForm(request.POST)
        if form.is_valid():
            cuenta = form.save(commit=False)
            cuenta.empresa = empresa_actual
            cuenta.save()
            messages.success(request, f'Cuenta {cuenta.codigo} - {cuenta.nombre} creada con éxito.')
            return redirect('contabilidad:plan_cuentas_lista')
    else:
        form = CuentaContableForm()

    return render(request, 'contabilidad/plan_cuentas/form.html', {
        'form': form,
        'titulo': 'Crear Cuenta Contable',
        'cuenta': None,
    })


@login_required
def plan_cuentas_editar_view(request, pk):
    """Edita código, nombre y tipo de una cuenta contable."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        messages.warning(request, "Por favor, selecciona una empresa.")
        return redirect('core:home')

    cuenta = get_object_or_404(CuentaContable, pk=pk, empresa=empresa_actual)
    bloquear = cuenta.tiene_movimientos()

    if request.method == 'POST':
        form = CuentaContableForm(request.POST, instance=cuenta, bloquear_estructura=bloquear)
        if form.is_valid():
            cuenta_editada = form.save(commit=False)
            if bloquear:
                cuenta_editada.codigo = cuenta.codigo
                cuenta_editada.tipo = cuenta.tipo
            cuenta_editada.save()
            messages.success(request, f'Cuenta {cuenta_editada.codigo} actualizada correctamente.')
            return redirect('contabilidad:plan_cuentas_lista')
    else:
        form = CuentaContableForm(instance=cuenta, bloquear_estructura=bloquear)

    return render(request, 'contabilidad/plan_cuentas/form.html', {
        'form': form,
        'titulo': 'Editar Cuenta Contable',
        'cuenta': cuenta,
        'bloquear_estructura': bloquear,
    })


@login_required
def plan_cuentas_acciones_view(request, pk):
    """Asigna acciones rápidas ya creadas a una cuenta del plan."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    cuenta = get_object_or_404(CuentaContable, pk=pk, empresa=empresa_actual)
    acciones_empresa = AccionRapida.objects.filter(empresa=empresa_actual, activa=True).prefetch_related(
        'lineas_contrapartida__cuenta', 'asignaciones_cuentas',
    )

    if request.method == 'POST':
        seleccionadas = request.POST.getlist('accion_ids')
        CuentaAccionRapida.objects.filter(cuenta=cuenta).delete()
        for orden, accion_id in enumerate(seleccionadas):
            if accion_id:
                CuentaAccionRapida.objects.create(
                    cuenta=cuenta,
                    accion_id=accion_id,
                    orden=orden,
                )
        messages.success(request, f'Acciones asignadas a {cuenta.codigo}.')
        return redirect('contabilidad:plan_cuentas_lista')

    asignadas_ids = set(
        cuenta.asignaciones_acciones.values_list('accion_id', flat=True)
    )

    return render(request, 'contabilidad/plan_cuentas/acciones.html', {
        'cuenta': cuenta,
        'acciones_empresa': acciones_empresa,
        'asignadas_ids': asignadas_ids,
    })


@login_required
def acciones_rapidas_lista_view(request):
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    acciones = AccionRapida.objects.filter(empresa=empresa_actual).prefetch_related(
        'lineas_contrapartida__cuenta',
        'asignaciones_cuentas__cuenta',
    )
    return render(request, 'contabilidad/acciones_rapidas/lista.html', {
        'acciones': acciones,
    })


@login_required
def acciones_rapidas_form_view(request, pk=None):
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    accion = None
    if pk:
        accion = get_object_or_404(AccionRapida, pk=pk, empresa=empresa_actual)

    todas_cuentas = CuentaContable.objects.filter(empresa=empresa_actual)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        tipo = request.POST.get('tipo', 'pago')
        lado_pendiente = request.POST.get('lado_pendiente', 'haber')
        cuenta_ids = request.POST.getlist('cuenta_contrapartida[]')

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
        elif not cuenta_ids:
            messages.error(request, 'Agrega al menos una cuenta de contrapartida.')
        else:
            if accion:
                accion.nombre = nombre
                accion.tipo = tipo
                accion.lado_pendiente = lado_pendiente
                accion.save()
                accion.lineas_contrapartida.all().delete()
            else:
                accion = AccionRapida.objects.create(
                    empresa=empresa_actual,
                    nombre=nombre,
                    tipo=tipo,
                    lado_pendiente=lado_pendiente,
                )
            for orden, c_id in enumerate(cuenta_ids):
                if c_id:
                    LineaAccionRapida.objects.create(
                        accion=accion, cuenta_id=c_id, orden=orden,
                    )
            messages.success(request, f'Acción "{nombre}" guardada.')
            return redirect('contabilidad:acciones_rapidas_lista')

    contrapartidas = []
    if accion:
        contrapartidas = list(accion.lineas_contrapartida.values_list('cuenta_id', flat=True))

    return render(request, 'contabilidad/acciones_rapidas/form.html', {
        'accion': accion,
        'todas_cuentas': todas_cuentas,
        'contrapartidas': contrapartidas,
    })


@login_required
def acciones_rapidas_eliminar_view(request, pk):
    if request.method != 'POST':
        return redirect('contabilidad:acciones_rapidas_lista')

    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    accion = get_object_or_404(AccionRapida, pk=pk, empresa=empresa_actual)
    nombre = accion.nombre
    accion.delete()
    messages.success(request, f'Acción "{nombre}" eliminada.')
    return redirect('contabilidad:acciones_rapidas_lista')


@login_required
def plan_cuentas_eliminar_view(request, pk):
    """Elimina una cuenta si no tiene movimientos en el libro diario."""
    if request.method != 'POST':
        return redirect('contabilidad:plan_cuentas_lista')

    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    cuenta = get_object_or_404(CuentaContable, pk=pk, empresa=empresa_actual)
    if cuenta.tiene_movimientos():
        messages.error(
            request,
            f'No se puede eliminar {cuenta.codigo}: tiene movimientos en el libro diario.',
        )
        return redirect('contabilidad:plan_cuentas_lista')

    codigo = cuenta.codigo
    cuenta.delete()
    messages.success(request, f'Cuenta {codigo} eliminada correctamente.')
    return redirect('contabilidad:plan_cuentas_lista')


@login_required
def plan_cuentas_vaciar_view(request):
    """Elimina todo el plan de cuentas de la empresa si no hay asientos contables."""
    if request.method != 'POST':
        return redirect('contabilidad:plan_cuentas_lista')

    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    if AsientoContable.objects.filter(empresa=empresa_actual).exists():
        messages.error(
            request,
            'No se puede vaciar el plan: la empresa ya tiene asientos en el libro diario.',
        )
        return redirect('contabilidad:plan_cuentas_lista')

    total = CuentaContable.objects.filter(empresa=empresa_actual).count()
    CuentaContable.objects.filter(empresa=empresa_actual).delete()
    messages.success(request, f'Se eliminaron {total} cuentas del plan. Puedes cargar el plan base nuevamente.')
    return redirect('contabilidad:plan_cuentas_lista')


@login_required
def plan_cuentas_cargar_base_view(request):
    """Muestra una lista de cuentas predeterminadas y permite crearlas en bloque."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        messages.warning(request, "Por favor, selecciona una empresa para cargarle un plan de cuentas.")
        return redirect('core:home')

    codigos_existentes = set(
        CuentaContable.objects.filter(empresa=empresa_actual).values_list('codigo', flat=True)
    )

    if request.method == 'POST':
        codigos_seleccionados = set(request.POST.getlist('cuentas_seleccionadas'))
        cuentas_creadas = 0

        for cuenta_base in PLAN_CUENTAS_BASE:
            if cuenta_base['codigo'] in codigos_seleccionados and cuenta_base['codigo'] not in codigos_existentes:
                CuentaContable.objects.create(
                    empresa=empresa_actual,
                    codigo=cuenta_base['codigo'],
                    nombre=cuenta_base['nombre'],
                    tipo=cuenta_base['tipo'],
                    subtipo_operacion=cuenta_base.get('subtipo', 'general'),
                )
                cuentas_creadas += 1

        messages.success(request, f'Se han importado {cuentas_creadas} cuentas correctamente al plan de la empresa.')
        return redirect('contabilidad:plan_cuentas_lista')

    cuentas_agrupadas = {}
    for cuenta_base in PLAN_CUENTAS_BASE:
        tipo = cuenta_base['tipo']
        if tipo not in cuentas_agrupadas:
            cuentas_agrupadas[tipo] = []
        cuenta = cuenta_base.copy()
        cuenta['ya_existe'] = cuenta['codigo'] in codigos_existentes
        cuentas_agrupadas[tipo].append(cuenta)

    tipos_ordenados = [
        (tipo, TIPO_NOMBRES.get(tipo, tipo.title()), cuentas_agrupadas[tipo])
        for tipo in ORDEN_TIPOS
        if tipo in cuentas_agrupadas
    ]

    return render(request, 'contabilidad/plan_cuentas/cargar_base.html', {
        'empresa_actual': empresa_actual,
        'tipos_ordenados': tipos_ordenados,
    })


@login_required
def plan_cuentas_exportar_view(request):
    """Exporta plan de cuentas + acciones rápidas en JSON."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    payload = serializar_plan_empresa(empresa_actual)
    nombre = f"plan_cuentas_{empresa_actual.id}.json"
    response = JsonResponse(payload, json_dumps_params={'indent': 2, 'ensure_ascii': False})
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


@login_required
def plan_cuentas_importar_view(request):
    """Importa acciones rápidas desde JSON exportado (cuentas por código)."""
    empresa_actual = _get_empresa_plan(request)
    if not empresa_actual:
        return redirect('core:home')

    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        reemplazar = request.POST.get('reemplazar') == 'on'

        if not archivo:
            messages.error(request, 'Selecciona un archivo JSON exportado del plan.')
        else:
            try:
                data = json.load(archivo)
            except (json.JSONDecodeError, UnicodeDecodeError):
                messages.error(request, 'El archivo no es un JSON válido.')
            else:
                if reemplazar:
                    AccionRapida.objects.filter(empresa=empresa_actual).delete()
                importadas, omitidas = importar_acciones_plan(empresa_actual, data)
                messages.success(
                    request,
                    f'Importadas {importadas} acciones rápidas.'
                    + (f' Omitidas {omitidas} cuentas sin match por código.' if omitidas else ''),
                )
                return redirect('contabilidad:plan_cuentas_lista')

    return render(request, 'contabilidad/plan_cuentas/importar.html')

# =====================================================================
# VISTAS DE PLANTILLAS DE CENTRALIZACIÓN (FÓRMULAS)
# =====================================================================

@login_required
def plantilla_lista_view(request):
    """Lista todas las plantillas creadas para la empresa activa."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Selecciona una empresa para gestionar sus plantillas.")
        return redirect('core:home')

    plantillas = PlantillaCentralizacion.objects.filter(empresa_id=empresa_id)
    return render(request, 'contabilidad/plantillas/lista.html', {'plantillas': plantillas})

@login_required
def plantilla_crear_view(request):
    """Motor dinámico para crear plantillas y sus líneas matemáticas."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')
        
    empresa_actual = get_object_or_404(Empresa, id=empresa_id)
    cuentas = CuentaContable.objects.filter(empresa=empresa_actual)
    codigos_sii = CodigoF29.objects.all()

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        tipo_origen = request.POST.get('tipo_origen')
        
        plantilla = PlantillaCentralizacion.objects.create(
            empresa=empresa_actual, nombre=nombre, tipo_origen=tipo_origen
        )
        
        # Obtenemos los arrays enviados por el JS dinámico
        cuentas_id = request.POST.getlist('cuenta_id[]')
        movimientos = request.POST.getlist('movimiento[]')
        formulas = request.POST.getlist('formula[]')
        
        for c_id, mov, form in zip(cuentas_id, movimientos, formulas):
            if c_id and mov and form:
                LineaPlantilla.objects.create(plantilla=plantilla, cuenta_id=c_id, tipo_movimiento=mov, formula=form)
                
        messages.success(request, f'Plantilla "{nombre}" creada con éxito.')
        return redirect('contabilidad:plantilla_lista')

    return render(request, 'contabilidad/plantillas/form_js.html', {'cuentas': cuentas, 'codigos_sii': codigos_sii})

@login_required
def plantilla_copiar_view(request):
    """Permite a un Administrador copiar una plantilla de otra empresa a la actual."""
    # REGLA RBAC: Solo Administradores pueden clonar configuraciones
    if request.user.perfil.rol != 'admin':
        messages.error(request, "Acceso denegado: Solo los administradores pueden copiar plantillas entre empresas.")
        return redirect('contabilidad:plantilla_lista')
        
    empresa_dest_id = request.session.get('empresa_activa_id')
    if not empresa_dest_id:
        return redirect('core:home')
        
    empresa_dest = get_object_or_404(Empresa, id=empresa_dest_id)
    
    if request.method == 'POST':
        plantilla_origen_id = request.POST.get('plantilla_id')
        if plantilla_origen_id:
            plantilla_origen = get_object_or_404(PlantillaCentralizacion, id=plantilla_origen_id)
            
            # 1. Crear la cabecera de la nueva plantilla
            nueva_plantilla = PlantillaCentralizacion.objects.create(
                empresa=empresa_dest, nombre=f"{plantilla_origen.nombre} (Copia)", tipo_origen=plantilla_origen.tipo_origen
            )
            
            errores = []
            # 2. Copiar líneas mapeando la cuenta destino según el CÓDIGO de la cuenta origen
            for linea in plantilla_origen.lineas.all():
                cuenta_dest = CuentaContable.objects.filter(empresa=empresa_dest, codigo=linea.cuenta.codigo).first()
                if cuenta_dest:
                    LineaPlantilla.objects.create(
                        plantilla=nueva_plantilla, cuenta=cuenta_dest, tipo_movimiento=linea.tipo_movimiento, formula=linea.formula
                    )
                else:
                    errores.append(f"{linea.cuenta.codigo} ({linea.cuenta.nombre})")
            
            if errores:
                messages.warning(request, f"Copia parcial. Las siguientes cuentas no existen en esta empresa y sus líneas fueron omitidas: {', '.join(errores)}")
            else:
                messages.success(request, "¡Plantilla copiada y vinculada exitosamente!")
            return redirect('contabilidad:plantilla_lista')

    # Traemos todas las plantillas que NO pertenezcan a la empresa actual
    plantillas_otras = PlantillaCentralizacion.objects.exclude(empresa=empresa_dest).select_related('empresa').order_by('empresa__razon_social', 'nombre')
    return render(request, 'contabilidad/plantillas/copiar.html', {'plantillas_otras': plantillas_otras, 'empresa_dest': empresa_dest})

@login_required
def plantilla_editar_view(request, pk):
    """Permite editar una plantilla existente y sus fórmulas."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')
        
    plantilla = get_object_or_404(PlantillaCentralizacion, pk=pk, empresa_id=empresa_id)
    cuentas = CuentaContable.objects.filter(empresa_id=empresa_id)
    codigos_sii = CodigoF29.objects.all()

    if request.method == 'POST':
        plantilla.nombre = request.POST.get('nombre')
        plantilla.tipo_origen = request.POST.get('tipo_origen')
        plantilla.save()
        
        # Estrategia Erase & Replace: Borramos líneas viejas y creamos las nuevas
        plantilla.lineas.all().delete()
        
        cuentas_id = request.POST.getlist('cuenta_id[]')
        movimientos = request.POST.getlist('movimiento[]')
        formulas = request.POST.getlist('formula[]')
        
        for c_id, mov, form in zip(cuentas_id, movimientos, formulas):
            if c_id and mov and form:
                LineaPlantilla.objects.create(plantilla=plantilla, cuenta_id=c_id, tipo_movimiento=mov, formula=form)
                
        messages.success(request, f'Plantilla "{plantilla.nombre}" actualizada con éxito.')
        return redirect('contabilidad:plantilla_lista')

    return render(request, 'contabilidad/plantillas/form_js.html', {
        'plantilla': plantilla, 'cuentas': cuentas, 'codigos_sii': codigos_sii
    })

# =====================================================================
# VISTAS DEL LIBRO DIARIO Y ASIENTOS
# =====================================================================

@login_required
def libro_diario_view(request):
    """Muestra la lista de Asientos Contables generados para la empresa."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Selecciona una empresa para ver su Libro Diario.")
        return redirect('core:home')
        
    asientos = AsientoContable.objects.filter(empresa_id=empresa_id).select_related(
        'origen_f29', 'origen_plantilla'
    ).prefetch_related('lineas')
    return render(request, 'contabilidad/libro_diario/lista.html', {'asientos': asientos})

@login_required
def asiento_detalle_view(request, pk):
    """Muestra el detalle de un asiento específico (Comprobante de Partida Doble)."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')
        
    asiento = get_object_or_404(
        AsientoContable.objects.prefetch_related(
            'lineas__cuenta',
            'lineas__aplicaciones_salida__asiento_pago',
            'aplicaciones__linea_origen__asiento',
            'aplicaciones__linea_origen__cuenta',
        ),
        pk=pk,
        empresa_id=empresa_id,
    )
    total_debe = sum(linea.debe for linea in asiento.lineas.all())
    total_haber = sum(linea.haber for linea in asiento.lineas.all())
    aplicaciones = list(asiento.aplicaciones.all()) if asiento.tipo_asiento in ('pago', 'cobro') else []
    lineas_saldadas = [l for l in asiento.lineas.all() if l.monto_aplicado > 0]
    
    return render(request, 'contabilidad/libro_diario/detalle.html', {
        'asiento': asiento,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'aplicaciones': aplicaciones,
        'lineas_saldadas': lineas_saldadas,
    })
