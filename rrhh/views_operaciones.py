# rrhh/views_operaciones.py — Hub, personal, finiquitos, export, centralización

from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from contabilidad.models import AsientoContable
from core.models import Empresa
from core.permissions import ensure_empresa_operativa, require_access

from .calculos_rrhh import saldo_vacaciones_trabajador
from .centralizacion_rrhh import generar_asiento_remuneraciones, resumen_liquidaciones_periodo
from .export_previred import generar_csv_previred
from .forms import (
    CargaFamiliarForm,
    CentralizacionRRHHForm,
    MovimientoVacacionesForm,
    PrestamoForm,
    TerminarContratoForm,
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
from .motor_finiquito import calcular_finiquito


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


@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def terminar_contrato_view(request, contrato_id):
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden('No tienes permiso.')

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    contrato = get_object_or_404(Contrato, id=contrato_id, trabajador__empresa_id=empresa_id)
    trabajador = contrato.trabajador
    preview = None

    if request.method == 'POST':
        form = TerminarContratoForm(request.POST)
        if form.is_valid():
            fecha_termino = form.cleaned_data['fecha_termino']
            motivo = form.cleaned_data['motivo']
            contrato.fecha_fin = fecha_termino
            contrato.vigente = False
            contrato.save(update_fields=['fecha_fin', 'vigente'])

            finiquito = None
            if form.cleaned_data['generar_finiquito']:
                mes_u = fecha_termino.month if form.cleaned_data['incluir_ultimo_mes'] else None
                ano_u = fecha_termino.year if form.cleaned_data['incluir_ultimo_mes'] else None
                datos = calcular_finiquito(
                    contrato, fecha_termino, motivo,
                    incluir_ultimo_mes=form.cleaned_data['incluir_ultimo_mes'],
                    mes_ultimo=mes_u, ano_ultimo=ano_u,
                )
                finiquito = Finiquito.objects.create(
                    contrato=contrato,
                    fecha_termino=fecha_termino,
                    motivo=motivo,
                    **datos,
                )

            otros_vigentes = trabajador.contratos.filter(vigente=True).exists()
            if not otros_vigentes:
                trabajador.activo = False
                trabajador.save(update_fields=['activo'])

            messages.success(request, 'Contrato terminado correctamente.')
            if finiquito:
                return redirect('rrhh:finiquito_detail', pk=finiquito.pk)
            return redirect('rrhh:trabajador_detail', pk=trabajador.pk)
    else:
        form = TerminarContratoForm()
        if contrato.fecha_fin:
            form.fields['fecha_termino'].initial = contrato.fecha_fin

    preview = calcular_finiquito(contrato, date.today(), 'RENUNCIA')

    return render(request, 'rrhh/terminar_contrato.html', {
        'form': form,
        'contrato': contrato,
        'trabajador': trabajador,
        'preview': preview,
        'saldo_vacaciones': saldo_vacaciones_trabajador(trabajador),
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
        Finiquito, pk=pk, contrato__trabajador__empresa_id=empresa_id,
    )
    return render(request, 'rrhh/finiquito_detail.html', {'finiquito': finiquito})


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
def centralizar_remuneraciones_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    empresa = get_object_or_404(Empresa, id=empresa_id)
    today = datetime.now()
    mes = int(request.GET.get('mes', today.month))
    ano = int(request.GET.get('ano', today.year))

    resumen = resumen_liquidaciones_periodo(empresa, mes, ano)
    asiento_existente = AsientoContable.objects.filter(
        empresa=empresa, origen_rrhh_mes=mes, origen_rrhh_ano=ano,
    ).first()

    if request.method == 'POST':
        form = CentralizacionRRHHForm(request.POST)
        if form.is_valid():
            cuentas_map = {
                'gasto_remuneraciones': form.cleaned_data['cuenta_gasto'],
                'sueldos_por_pagar': form.cleaned_data['cuenta_sueldos'],
                'cotizaciones_por_pagar': form.cleaned_data['cuenta_cotizaciones'],
                'sis_por_pagar': form.cleaned_data['cuenta_sis'],
                'afc_empleador_por_pagar': form.cleaned_data['cuenta_afc'],
            }
            try:
                asiento, _ = generar_asiento_remuneraciones(
                    empresa, form.cleaned_data['mes'], form.cleaned_data['ano'], cuentas_map,
                )
                messages.success(request, f'Asiento contable #{asiento.id} generado correctamente.')
                return redirect('contabilidad:asiento_detalle', pk=asiento.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = CentralizacionRRHHForm(initial={'mes': mes, 'ano': ano})

    return render(request, 'rrhh/centralizar_remuneraciones.html', {
        'form': form,
        'resumen': resumen,
        'asiento_existente': asiento_existente,
        'mes_seleccionado': mes,
        'ano_seleccionado': ano,
    })
