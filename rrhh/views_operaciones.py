# rrhh/views_operaciones.py — Hub, personal, finiquitos, export, centralización

import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from contabilidad.models import AsientoContable
from core.models import Empresa
from core.permissions import ensure_empresa_operativa, require_access
from core.vista import vista_es_admin_ui

from .calculos_rrhh import saldo_vacaciones_trabajador
from .centralizacion_rrhh import (
    generar_asiento_remuneraciones,
    obtener_o_crear_configuracion,
    resumen_liquidaciones_periodo,
    vista_previa_asiento,
)
from .export_previred import generar_csv_previred
from .forms import (
    CargaFamiliarForm,
    CentralizacionRRHHForm,
    ConfiguracionCentralizacionRRHHForm,
    MovimientoVacacionesForm,
    PrestamoForm,
    TrabajadorForm,
)
from .models import (
    CargaFamiliar,
    Contrato,
    Finiquito,
    Liquidacion,
    MovimientoVacaciones,
    Prestamo,
    Trabajador,
)
from .motor_finiquito import propuestas_finiquito
from .plantilla_finiquito import (
    BLOQUES,
    VARIABLES,
    contexto_finiquito,
    documento_desde_lineas,
    guardar_textos,
    obtener_textos,
)


@login_required
def rrhh_hub_view(request):
    """Centro de operaciones RR.HH. con accesos agrupados por flujo de trabajo."""
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response
    empresa = get_object_or_404(Empresa, id=empresa_id)
    today = datetime.now()
    return render(request, 'rrhh/hub.html', {
        'empresa': empresa,
        'mes_actual': today.month,
        'ano_actual': today.year,
    })


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def trabajador_edit_view(request, pk):
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden('No tienes permiso para editar trabajadores.')

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=pk, empresa_id=empresa_id)
    if request.method == 'POST':
        form = TrabajadorForm(request.POST, instance=trabajador, empresa_fija_id=empresa_id)
        if form.is_valid():
            t = form.save(commit=False)
            t.empresa_id = empresa_id
            t.save()
            messages.success(request, 'Ficha del trabajador actualizada.')
            return redirect('rrhh:trabajador_detail', pk=trabajador.pk)
    else:
        form = TrabajadorForm(instance=trabajador, empresa_fija_id=empresa_id)

    return render(request, 'rrhh/trabajador_form.html', {
        'form': form,
        'titulo': f'Editar — {trabajador.nombre_completo}',
        'empresa_asignada': trabajador.empresa,
        'trabajador': trabajador,
    })


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def trabajador_toggle_activo_view(request, pk):
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden('No tienes permiso.')

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=pk, empresa_id=empresa_id)
    if request.method == 'POST':
        trabajador.activo = not trabajador.activo
        trabajador.save(update_fields=['activo'])
        estado = 'activado' if trabajador.activo else 'desactivado'
        messages.success(request, f'Trabajador {estado} correctamente.')
    return redirect('rrhh:trabajador_detail', pk=pk)


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def gestionar_cargas_familiares_view(request, trabajador_pk):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=trabajador_pk, empresa_id=empresa_id)
    CargaFormSet = modelformset_factory(CargaFamiliar, form=CargaFamiliarForm, extra=1, can_delete=True)

    if request.method == 'POST':
        formset = CargaFormSet(request.POST, queryset=CargaFamiliar.objects.filter(trabajador=trabajador))
        if formset.is_valid():
            instances = formset.save(commit=False)
            for inst in instances:
                inst.trabajador = trabajador
                inst.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, 'Cargas familiares actualizadas.')
            return redirect('rrhh:trabajador_detail', pk=trabajador.pk)
    else:
        formset = CargaFormSet(queryset=CargaFamiliar.objects.filter(trabajador=trabajador))

    return render(request, 'rrhh/cargas_familiares_form.html', {
        'formset': formset,
        'trabajador': trabajador,
    })


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def gestionar_prestamos_view(request, contrato_id):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    contrato = get_object_or_404(Contrato, id=contrato_id, trabajador__empresa_id=empresa_id)
    prestamos = Prestamo.objects.filter(contrato=contrato).order_by('-fecha_solicitud')

    if request.method == 'POST':
        form = PrestamoForm(request.POST)
        if form.is_valid():
            prestamo = form.save(commit=False)
            prestamo.contrato = contrato
            prestamo.save()
            messages.success(request, 'Préstamo registrado. Se descontará en las próximas liquidaciones.')
            return redirect('rrhh:gestionar_prestamos', contrato_id=contrato.id)
    else:
        form = PrestamoForm()

    return render(request, 'rrhh/prestamos_list.html', {
        'contrato': contrato,
        'prestamos': prestamos,
        'form': form,
    })


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def gestionar_vacaciones_view(request, trabajador_pk):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=trabajador_pk, empresa_id=empresa_id)
    saldo = saldo_vacaciones_trabajador(trabajador)
    movimientos = MovimientoVacaciones.objects.filter(trabajador=trabajador)[:30]

    if request.method == 'POST':
        form = MovimientoVacacionesForm(request.POST)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.trabajador = trabajador
            mov.save()
            messages.success(request, 'Movimiento de vacaciones registrado.')
            return redirect('rrhh:gestionar_vacaciones', trabajador_pk=trabajador.pk)
    else:
        form = MovimientoVacacionesForm()

    return render(request, 'rrhh/vacaciones.html', {
        'trabajador': trabajador,
        'saldo': saldo,
        'movimientos': movimientos,
        'form': form,
    })


def _solo_admin_finiquito(request):
    if not vista_es_admin_ui(request):
        return HttpResponseForbidden('Solo administradores pueden finiquitar.')
    return None


def _decimal_dias(raw):
    texto = str(raw or '0').strip().replace(' ', '')
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    else:
        texto = texto.replace(',', '.')
    try:
        return Decimal(texto)
    except InvalidOperation:
        raise ValueError('Los días de vacaciones deben ser un número, por ejemplo 11.25.')


def _lineas_finiquito_post(request):
    nombres = request.POST.getlist('linea_nombre')
    montos = request.POST.getlist('linea_monto')
    lineas = []
    for nombre, monto in zip(nombres, montos):
        nombre = (nombre or '').strip()
        monto_txt = ''.join(ch for ch in str(monto or '') if ch.isdigit())
        if not nombre and not str(monto or '').strip():
            continue
        if not nombre:
            raise ValueError('Cada línea con monto necesita un concepto.')
        if not monto_txt:
            raise ValueError(f'El monto de «{nombre}» debe ser un entero, por ejemplo 150000.')
        lineas.append({'nombre': nombre[:200], 'monto': int(monto_txt)})
    if not lineas:
        raise ValueError('Agrega al menos un concepto.')
    return lineas


def _preview_base(contrato, fecha, motivo):
    if isinstance(fecha, str):
        try:
            fecha_d = datetime.strptime(fecha, '%Y-%m-%d').date()
        except ValueError:
            fecha_d = date.today()
    else:
        fecha_d = fecha or date.today()
    motivo_label = dict(Finiquito.MOTIVO_CHOICES).get(motivo, motivo)
    doc = documento_desde_lineas(contrato, fecha_d, motivo_label, [])
    return {
        'titulo': doc['textos']['titulo'],
        'intro': doc['textos']['intro'],
        'servicios': doc['textos']['servicios'],
        'cierre': doc['textos']['cierre'],
        'variables': doc['variables'],
    }


def _pdf_propuesta(request, contrato):
    try:
        fecha = datetime.strptime(request.POST.get('fecha_termino') or '', '%Y-%m-%d').date()
    except ValueError:
        fecha = date.today()
    motivo = request.POST.get('motivo') or 'RENUNCIA'
    motivo_label = dict(Finiquito.MOTIVO_CHOICES).get(motivo, motivo)
    try:
        lineas = _lineas_finiquito_post(request)
    except (ValueError, InvalidOperation) as exc:
        return HttpResponse(str(exc), status=400, content_type='text/plain; charset=utf-8')
    documento = documento_desde_lineas(contrato, fecha, motivo_label, lineas)
    borrador = type('Borrador', (), {})()
    borrador.conceptos = lineas
    borrador.total_bruto_finiquito = documento['total']
    html = render_to_string('rrhh/finiquito_pdf.html', {
        'finiquito': borrador,
        'documento': documento,
    })
    try:
        from xhtml2pdf import pisa
        output = io.BytesIO()
        pisa.CreatePDF(src=html, dest=output, encoding='utf-8')
        payload = output.getvalue()
        content_type = 'application/pdf'
    except Exception:
        payload = html.encode('utf-8')
        content_type = 'text/html; charset=utf-8'
    response = HttpResponse(payload, content_type=content_type)
    response['Content-Disposition'] = 'attachment; filename="propuesta_finiquito.pdf"'
    return response


def _totales_desde_lineas(lineas, dias_vacaciones):
    vacaciones = indemnizacion = otros = 0
    for linea in lineas:
        nombre = linea['nombre'].lower()
        if nombre.startswith('feriado') or nombre.startswith('vacacion'):
            vacaciones += linea['monto']
        elif 'años de servicio' in nombre or 'anos de servicio' in nombre:
            indemnizacion += linea['monto']
        else:
            otros += linea['monto']
    return {
        'dias_vacaciones_pendientes': dias_vacaciones,
        'monto_vacaciones': vacaciones,
        'monto_indemnizacion': indemnizacion,
        'monto_ultimo_sueldo': otros,
        'total_bruto_finiquito': vacaciones + indemnizacion + otros,
        'conceptos': lineas,
    }


def _lineas_guardadas(finiquito):
    if finiquito.conceptos:
        return finiquito.conceptos
    lineas = [{
        'nombre': f'Feriado proporcional ({finiquito.dias_vacaciones_pendientes} días)',
        'monto': finiquito.monto_vacaciones,
    }]
    if finiquito.monto_indemnizacion:
        lineas.append({
            'nombre': 'Indemnización por años de servicio',
            'monto': finiquito.monto_indemnizacion,
        })
    if finiquito.monto_ultimo_sueldo:
        lineas.append({
            'nombre': 'Otros haberes del finiquito',
            'monto': finiquito.monto_ultimo_sueldo,
        })
    return lineas


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def terminar_contrato_view(request, contrato_id):
    denegado = _solo_admin_finiquito(request)
    if denegado:
        return denegado
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    contrato = get_object_or_404(
        Contrato.objects.select_related('trabajador'),
        id=contrato_id,
        trabajador__empresa_id=empresa_id,
    )
    trabajador = contrato.trabajador
    existente = contrato.finiquitos.order_by('-fecha_emision', '-id').first()
    if existente and request.method != 'POST':
        return redirect('rrhh:finiquito_editar', pk=existente.pk)

    try:
        fecha = datetime.strptime(request.POST.get('fecha_termino') or request.GET.get('fecha') or '', '%Y-%m-%d').date()
    except ValueError:
        fecha = date.today()

    if request.method == 'POST' and request.POST.get('accion') == 'vista_pdf':
        return _pdf_propuesta(request, contrato)

    if request.method == 'POST' and request.POST.get('accion') == 'guardar':
        motivo = request.POST.get('motivo') or 'RENUNCIA'
        if motivo not in dict(Finiquito.MOTIVO_CHOICES):
            motivo = 'RENUNCIA'
        try:
            dias_vac = _decimal_dias(request.POST.get('dias_vacaciones'))
            lineas = _lineas_finiquito_post(request)
            datos = _totales_desde_lineas(lineas, dias_vac)
        except (ValueError, InvalidOperation) as exc:
            return render(request, 'rrhh/finiquitar.html', {
                'modo': 'lineas',
                'contrato': contrato,
                'trabajador': trabajador,
                'fecha': request.POST.get('fecha_termino'),
                'motivo': motivo,
                'motivo_label': dict(Finiquito.MOTIVO_CHOICES).get(motivo, motivo),
                'dias_vacaciones': request.POST.get('dias_vacaciones') or '0',
                'lineas': [
                    {'nombre': n, 'monto': m}
                    for n, m in zip(request.POST.getlist('linea_nombre'), request.POST.getlist('linea_monto'))
                ] or [{'nombre': '', 'monto': ''}],
                'preview_base': _preview_base(contrato, request.POST.get('fecha_termino'), motivo),
                'error': str(exc),
            })

        contrato.fecha_fin = fecha
        contrato.vigente = False
        contrato.save(update_fields=['fecha_fin', 'vigente'])
        if not trabajador.contratos.filter(vigente=True).exists():
            trabajador.activo = False
            trabajador.save(update_fields=['activo'])
        finiquito = Finiquito.objects.create(
            contrato=contrato,
            fecha_termino=fecha,
            motivo=motivo,
            **datos,
        )
        messages.success(request, 'Finiquito guardado y contrato terminado.')
        return redirect('rrhh:finiquito_detail', pk=finiquito.pk)

    if request.method == 'POST' and request.POST.get('accion') == 'elegir':
        motivo = request.POST.get('motivo') or 'RENUNCIA'
        propuesta = next((p for p in propuestas_finiquito(contrato, fecha) if p['motivo'] == motivo), None)
        if not propuesta:
            messages.error(request, 'Elige una causal.')
            return redirect('rrhh:terminar_contrato', contrato_id=contrato.id)
        return render(request, 'rrhh/finiquitar.html', {
            'modo': 'lineas',
            'contrato': contrato,
            'trabajador': trabajador,
            'fecha': fecha.isoformat(),
            'motivo': motivo,
            'motivo_label': propuesta['titulo'],
            'dias_vacaciones': propuesta['dias_vacaciones'],
            'lineas': propuesta['lineas'],
            'preview_base': _preview_base(contrato, fecha, motivo),
            'error': '',
        })

    return render(request, 'rrhh/finiquitar.html', {
        'modo': 'propuestas',
        'contrato': contrato,
        'trabajador': trabajador,
        'fecha': fecha.isoformat(),
        'propuestas': propuestas_finiquito(contrato, fecha),
        'saldo_vacaciones': saldo_vacaciones_trabajador(trabajador, fecha),
    })


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def finiquito_editar_view(request, pk):
    denegado = _solo_admin_finiquito(request)
    if denegado:
        return denegado
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    finiquito = get_object_or_404(
        Finiquito.objects.select_related('contrato__trabajador'),
        pk=pk,
        contrato__trabajador__empresa_id=empresa_id,
    )
    if request.method == 'POST' and request.POST.get('accion') == 'vista_pdf':
        return _pdf_propuesta(request, finiquito.contrato)

    if request.method == 'POST':
        try:
            fecha = datetime.strptime(request.POST.get('fecha_termino') or '', '%Y-%m-%d').date()
        except ValueError:
            fecha = finiquito.fecha_termino
        try:
            dias_vac = _decimal_dias(request.POST.get('dias_vacaciones') or finiquito.dias_vacaciones_pendientes)
            lineas = _lineas_finiquito_post(request)
            datos = _totales_desde_lineas(lineas, dias_vac)
        except (ValueError, InvalidOperation) as exc:
            return render(request, 'rrhh/finiquitar.html', {
                'modo': 'lineas',
                'finiquito': finiquito,
                'contrato': finiquito.contrato,
                'trabajador': finiquito.contrato.trabajador,
                'fecha': request.POST.get('fecha_termino') or finiquito.fecha_termino.isoformat(),
                'motivo': finiquito.motivo,
                'motivo_label': finiquito.get_motivo_display(),
                'dias_vacaciones': request.POST.get('dias_vacaciones') or finiquito.dias_vacaciones_pendientes,
                'lineas': [
                    {'nombre': n, 'monto': m}
                    for n, m in zip(request.POST.getlist('linea_nombre'), request.POST.getlist('linea_monto'))
                ],
                'preview_base': _preview_base(finiquito.contrato, request.POST.get('fecha_termino'), finiquito.motivo),
                'error': str(exc),
            })
        for campo, valor in datos.items():
            setattr(finiquito, campo, valor)
        finiquito.fecha_termino = fecha
        finiquito.save()
        contrato = finiquito.contrato
        contrato.fecha_fin = fecha
        contrato.save(update_fields=['fecha_fin'])
        messages.success(request, 'Finiquito actualizado.')
        return redirect('rrhh:finiquito_detail', pk=finiquito.pk)

    return render(request, 'rrhh/finiquitar.html', {
        'modo': 'lineas',
        'finiquito': finiquito,
        'contrato': finiquito.contrato,
        'trabajador': finiquito.contrato.trabajador,
        'fecha': finiquito.fecha_termino.isoformat(),
        'motivo': finiquito.motivo,
        'motivo_label': finiquito.get_motivo_display(),
        'dias_vacaciones': finiquito.dias_vacaciones_pendientes,
        'lineas': _lineas_guardadas(finiquito),
        'preview_base': _preview_base(finiquito.contrato, finiquito.fecha_termino, finiquito.motivo),
        'error': '',
    })


@login_required
@require_access('rrhh', 'trabajadores', 'ver')
def finiquito_list_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    finiquitos = Finiquito.objects.filter(
        contrato__trabajador__empresa_id=empresa_id,
    ).select_related('contrato__trabajador').order_by('-fecha_emision')[:100]

    return render(request, 'rrhh/finiquito_list.html', {'finiquitos': finiquitos})


@login_required
@require_access('rrhh', 'trabajadores', 'ver')
def finiquito_detail_view(request, pk):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    finiquito = get_object_or_404(
        Finiquito.objects.select_related('contrato__trabajador__empresa'),
        pk=pk,
        contrato__trabajador__empresa_id=empresa_id,
    )
    return render(request, 'rrhh/finiquito_detail.html', {
        'finiquito': finiquito,
        'documento': contexto_finiquito(finiquito),
    })


@login_required
@require_access('rrhh', 'trabajadores', 'ver')
def finiquito_pdf_view(request, pk):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response
    finiquito = get_object_or_404(
        Finiquito.objects.select_related('contrato__trabajador__empresa'),
        pk=pk,
        contrato__trabajador__empresa_id=empresa_id,
    )
    html = render_to_string('rrhh/finiquito_pdf.html', {
        'finiquito': finiquito,
        'documento': contexto_finiquito(finiquito),
    })
    try:
        from xhtml2pdf import pisa
        output = io.BytesIO()
        pisa.CreatePDF(src=html, dest=output, encoding='utf-8')
        payload = output.getvalue()
        content_type = 'application/pdf'
        filename = f'finiquito_{finiquito.contrato.trabajador.rut}.pdf'
    except Exception:
        payload = html.encode('utf-8')
        content_type = 'text/html; charset=utf-8'
        filename = 'finiquito.html'
    response = HttpResponse(payload, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def plantilla_finiquito_view(request):
    if not vista_es_admin_ui(request):
        return HttpResponseForbidden('Solo administradores pueden editar plantillas.')
    if request.method == 'POST':
        guardar_textos(request.POST)
        messages.success(request, 'Borrador de finiquito guardado.')
        return redirect('rrhh:plantilla_finiquito')
    textos = obtener_textos()
    return render(request, 'rrhh/plantilla_finiquito.html', {
        'bloques': [
            {'codigo': codigo, 'etiqueta': etiqueta, 'texto': textos[codigo]}
            for codigo, etiqueta, _defecto in BLOQUES
        ],
        'variables': VARIABLES,
    })


@login_required
@require_access('rrhh', 'liquidaciones', 'exportar')
def export_previred_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    empresa = get_object_or_404(Empresa, id=empresa_id)
    today = datetime.now()
    mes = int(request.GET.get('mes', today.month))
    ano = int(request.GET.get('ano', today.year))

    if request.GET.get('descargar') == '1':
        csv_content = generar_csv_previred(empresa, mes, ano)
        if len(csv_content.strip().splitlines()) <= 1:
            messages.warning(request, 'No hay liquidaciones para exportar en ese período.')
            return redirect(f"{reverse('rrhh:export_previred')}?mes={mes}&ano={ano}")
        response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="previred_{empresa.rut}_{mes:02d}_{ano}.csv"'
        return response

    count = Liquidacion.objects.filter(
        contrato__trabajador__empresa=empresa, mes=mes, ano=ano,
    ).count()

    return render(request, 'rrhh/export_previred.html', {
        'mes_seleccionado': mes,
        'ano_seleccionado': ano,
        'meses_opciones': range(1, 13),
        'anos_opciones': range(2024, today.year + 2),
        'cantidad_liquidaciones': count,
    })


@login_required
@require_access('rrhh', 'liquidaciones', 'exportar')
def configurar_centralizacion_rrhh_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    empresa = get_object_or_404(Empresa, id=empresa_id)
    config = obtener_o_crear_configuracion(empresa)

    if request.method == 'POST':
        form = ConfiguracionCentralizacionRRHHForm(request.POST, instance=config, empresa=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cuentas de centralización de remuneraciones guardadas.')
            next_url = request.POST.get('next') or reverse('rrhh:centralizar_remuneraciones')
            return redirect(next_url)
    else:
        form = ConfiguracionCentralizacionRRHHForm(instance=config, empresa=empresa)

    return render(request, 'rrhh/config_centralizacion_rrhh.html', {
        'form': form,
        'config': config,
    })


@login_required
@require_access('rrhh', 'liquidaciones', 'exportar')
def centralizar_remuneraciones_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    empresa = get_object_or_404(Empresa, id=empresa_id)
    today = datetime.now()
    mes = int(request.GET.get('mes', today.month))
    ano = int(request.GET.get('ano', today.year))

    config = obtener_o_crear_configuracion(empresa)
    resumen = resumen_liquidaciones_periodo(empresa, mes, ano)
    preview_lineas = vista_previa_asiento(resumen, config) if resumen['cantidad'] else []
    asiento_existente = AsientoContable.objects.filter(
        empresa=empresa, origen_rrhh_mes=mes, origen_rrhh_ano=ano,
    ).first()

    if request.method == 'POST':
        form = CentralizacionRRHHForm(request.POST)
        if form.is_valid():
            try:
                asiento, _ = generar_asiento_remuneraciones(
                    empresa,
                    form.cleaned_data['mes'],
                    form.cleaned_data['ano'],
                    config=config,
                )
                messages.success(request, f'Asiento contable #{asiento.id} generado correctamente.')
                return redirect('contabilidad:asiento_detalle', pk=asiento.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = CentralizacionRRHHForm(initial={'mes': mes, 'ano': ano})

    return render(request, 'rrhh/centralizar_remuneraciones.html', {
        'form': form,
        'config': config,
        'resumen': resumen,
        'preview_lineas': preview_lineas,
        'asiento_existente': asiento_existente,
        'mes_seleccionado': mes,
        'ano_seleccionado': ano,
        'meses_opciones': range(1, 13),
        'anos_opciones': range(2024, today.year + 2),
    })
