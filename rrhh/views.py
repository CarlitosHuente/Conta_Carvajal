# rrhh/views.py

from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.forms import modelformset_factory, inlineformset_factory
from .models import Contrato, Trabajador, IndicadorEconomico, NovedadMensual, AFP, SistemaSalud, ItemContrato, Liquidacion, ItemLiquidacion, CuotaPrestamoLiquidacion, ConceptoVariable, TramoConcepto
from core.models import Empresa, PerfilUsuario
from .forms import EmpresaForm, TrabajadorForm, ContratoForm, IndicadorEconomicoForm, NovedadMensualForm, ItemContratoForm, ConceptoVariableForm, TramoConceptoForm
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from datetime import datetime, date
import requests
from django.urls import reverse
from .motor_remuneraciones import procesar_liquidacion
from django.db.models import Prefetch
import calendar
from .models import RegistroCobro
from django.db import models, transaction
from core.permissions import require_access, ensure_empresa_operativa
from core.vista import vista_es_admin_ui
from .liquidacion_items import descuentos_para_presentacion
from .libro_remuneraciones import COLUMNAS, MESES, excel_libro, libro_del_periodo
from .calculos_rrhh import iter_periodos, periodo_a_entero


def _sueldo_minimo_actual():
    ind = IndicadorEconomico.objects.order_by('-ano', '-mes').first()
    return ind.sueldo_minimo if ind else None


def _sincronizar_contratos_sueldo_minimo(sueldo_minimo=None):
    """Actualiza sueldo_base de contratos vigentes que usan sueldo mínimo (último indicador)."""
    ind = IndicadorEconomico.objects.order_by('-ano', '-mes').first()
    if not ind:
        return 0
    return Contrato.objects.filter(usa_sueldo_minimo=True, vigente=True).update(
        sueldo_base=ind.sueldo_minimo
    )


def _procesar_liquidaciones_mes(empresa, mes, ano, autocompletar_novedades=False):
    """Procesa liquidaciones de un mes. Devuelve dict con resultado."""
    contratos_activos = Contrato.objects.filter(trabajador__empresa=empresa, vigente=True)
    pendientes = []
    for contrato in contratos_activos:
        if not NovedadMensual.objects.filter(
            trabajador=contrato.trabajador, mes=mes, ano=ano
        ).exists():
            pendientes.append(contrato.trabajador)

    if pendientes and not autocompletar_novedades:
        return {
            'ok': False,
            'pendientes': pendientes,
            'exitos': 0,
            'fallos': 0,
            'errores': [],
        }

    if pendientes and autocompletar_novedades:
        for trabajador in pendientes:
            NovedadMensual.objects.get_or_create(
                trabajador=trabajador,
                mes=mes,
                ano=ano,
                defaults={
                    'dias_ausencia': 0,
                    'dias_licencia': 0,
                    'bono_esporadico': 0,
                    'descuento_esporadico': 0,
                    'datos_variables': {},
                },
            )

    exitos = 0
    fallos = 0
    omitidas_manuales = 0
    errores = []
    for contrato in contratos_activos:
        try:
            liq = procesar_liquidacion(contrato, mes, ano)
            if liq is None:
                continue
            if liq.manual:
                omitidas_manuales += 1
            else:
                exitos += 1
        except Exception as e:
            fallos += 1
            errores.append(f"{contrato.trabajador.nombre_completo}: {e}")

    return {
        'ok': True,
        'pendientes': [],
        'exitos': exitos,
        'fallos': fallos,
        'omitidas_manuales': omitidas_manuales,
        'errores': errores,
    }


# ... (las otras vistas de liquidación pueden quedar abajo)
@login_required
def empresa_list_view(request):
    # SECCION: Filtro por Rol
    if request.user.perfil.rol == 'admin':
        # El contador ve todas las empresas
        empresas = Empresa.objects.all()
    else:
        # El cliente SOLO ve su propia empresa
        # Si no tiene empresa asignada, devolvemos lista vacía o error
        empresas = Empresa.objects.filter(id=request.user.perfil.empresa_id)
    
    context = {'empresas': empresas}
    return render(request, 'rrhh/empresa_list.html', context)

@login_required
def empresa_create_view(request):
    """
    Esta vista maneja el formulario para crear una nueva empresa.
    """
    # SECCION: Solo admin puede crear empresas
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    if request.method == 'POST':
        # Si el usuario envió el formulario...
        form = EmpresaForm(request.POST, request.FILES) # request.FILES es para la imagen del logo
        if form.is_valid():
            form.save() # Guarda la nueva empresa en la BD
            return redirect('rrhh:empresa_list') # Redirige a la lista de empresas
    else:
        # Si el usuario acaba de llegar a la página, muestra un formulario vacío
        form = EmpresaForm()
    
    context = {
        'form': form,
    }
    return render(request, 'rrhh/empresa_form.html', context)

@login_required
@require_access('rrhh', 'liquidaciones', 'crear')
def crear_liquidacion_view(request):
    """
    VISTA DE PROCESAMIENTO MASIVO
    Genera las liquidaciones para todos los trabajadores activos de la empresa
    para un período seleccionado.
    """
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para continuar.")
        return redirect('core:home')

    empresa = get_object_or_404(Empresa, id=empresa_id)
    pendientes_novedades = []

    # --- Lógica de Procesamiento (POST) ---
    if request.method == 'POST':
        accion = request.POST.get('accion', 'procesar')

        if accion == 'procesar_rango':
            mes_desde = int(request.POST.get('mes_desde'))
            ano_desde = int(request.POST.get('ano_desde'))
            mes_hasta = int(request.POST.get('mes_hasta'))
            ano_hasta = int(request.POST.get('ano_hasta'))
            autocompletar = request.POST.get('autocompletar_rango') == 'on'

            if periodo_a_entero(ano_desde, mes_desde) > periodo_a_entero(ano_hasta, mes_hasta):
                messages.error(request, 'El período inicial no puede ser posterior al final.')
                return redirect('rrhh:crear_liquidacion')

            periodos = list(iter_periodos(mes_desde, ano_desde, mes_hasta, ano_hasta))
            if len(periodos) > 24:
                messages.error(request, 'El rango máximo es de 24 meses por operación.')
                return redirect('rrhh:crear_liquidacion')

            total_exitos = 0
            total_fallos = 0
            total_omitidas = 0
            meses_sin_novedad = []
            todos_errores = []

            for mes_p, ano_p in periodos:
                resultado = _procesar_liquidaciones_mes(
                    empresa, mes_p, ano_p, autocompletar_novedades=autocompletar,
                )
                if not resultado['ok']:
                    meses_sin_novedad.append(f'{mes_p}/{ano_p}')
                    continue
                total_exitos += resultado['exitos']
                total_fallos += resultado['fallos']
                total_omitidas += resultado.get('omitidas_manuales', 0)
                todos_errores.extend(resultado['errores'])

            if meses_sin_novedad:
                messages.warning(
                    request,
                    f"Sin novedades (no procesados): {', '.join(meses_sin_novedad)}. "
                    "Marca autocompletar o carga novedades en esos meses.",
                )
            if total_exitos:
                messages.success(
                    request,
                    f"Rango procesado: {len(periodos)} mes(es), {total_exitos} liquidación(es) generada(s).",
                )
            if total_omitidas:
                messages.info(
                    request,
                    f"Se dejaron sin cambiar {total_omitidas} liquidación(es) ingresadas o editadas a mano.",
                )
            if total_fallos:
                messages.error(request, f"Fallos en el rango: {'; '.join(todos_errores[:5])}")

            return redirect(
                f"{reverse('rrhh:crear_liquidacion')}?mes={mes_hasta}&ano={ano_hasta}&tab=regularizacion"
            )

        mes = int(request.POST.get('mes'))
        ano = int(request.POST.get('ano'))

        if accion == 'autocompletar':
            resultado = _procesar_liquidaciones_mes(empresa, mes, ano, autocompletar_novedades=True)
            if resultado['exitos']:
                messages.success(
                    request,
                    f"Proceso finalizado. Se generaron/actualizaron {resultado['exitos']} liquidaciones.",
                )
            if resultado.get('omitidas_manuales'):
                messages.info(
                    request,
                    f"Se dejaron sin cambiar {resultado['omitidas_manuales']} liquidación(es) ingresadas o editadas a mano.",
                )
            if resultado['fallos']:
                messages.error(
                    request,
                    f"Fallaron {resultado['fallos']} liquidaciones: {', '.join(resultado['errores'])}",
                )
            return redirect(f"{reverse('rrhh:crear_liquidacion')}?mes={mes}&ano={ano}")

        resultado = _procesar_liquidaciones_mes(empresa, mes, ano, autocompletar_novedades=False)
        if not resultado['ok']:
            messages.warning(
                request,
                "Faltan datos minimos de novedades para algunos trabajadores. "
                "Completa en el asistente rapido y vuelve a procesar.",
            )
            context = {
                'mes_seleccionado': mes,
                'ano_seleccionado': ano,
                'anos_opciones': range(2024, datetime.now().year + 2),
                'meses_opciones': range(1, 13),
                'liquidaciones_generadas': Liquidacion.objects.filter(
                    contrato__trabajador__empresa=empresa, mes=mes, ano=ano
                ).select_related('contrato__trabajador').order_by('contrato__trabajador__apellido_paterno'),
                'pendientes_novedades': resultado['pendientes'],
            }
            return render(request, 'rrhh/crear_liquidacion.html', context)

        if resultado['exitos']:
            messages.success(
                request,
                f"Proceso finalizado. Se generaron/actualizaron {resultado['exitos']} liquidaciones exitosamente.",
            )
        if resultado.get('omitidas_manuales'):
            messages.info(
                request,
                f"Se dejaron sin cambiar {resultado['omitidas_manuales']} liquidación(es) ingresadas o editadas a mano.",
            )
        if resultado['fallos']:
            messages.error(
                request,
                f"Fallaron {resultado['fallos']} liquidaciones: {', '.join(resultado['errores'])}",
            )

        return redirect(f"{reverse('rrhh:crear_liquidacion')}?mes={mes}&ano={ano}")

    # --- Lógica de Visualización (GET) ---
    today = datetime.now()
    mes_seleccionado = int(request.GET.get('mes', today.month))
    ano_seleccionado = int(request.GET.get('ano', today.year))

    liquidaciones_generadas = Liquidacion.objects.filter(
        contrato__trabajador__empresa=empresa, mes=mes_seleccionado, ano=ano_seleccionado
    ).select_related('contrato__trabajador').order_by('contrato__trabajador__apellido_paterno')

    context = {
        'mes_seleccionado': mes_seleccionado,
        'ano_seleccionado': ano_seleccionado,
        'anos_opciones': range(2024, today.year + 2),
        'meses_opciones': range(1, 13),
        'liquidaciones_generadas': liquidaciones_generadas,
        'pendientes_novedades': pendientes_novedades,
    }
    return render(request, 'rrhh/crear_liquidacion.html', context)
    
# rrhh/views.py



@login_required
@require_access('rrhh', 'trabajadores', 'ver')
def trabajador_list_view(request):
    """
    Lista trabajadores de la empresa operativa (sesión admin o perfil cliente).
    """
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajadores = Trabajador.objects.filter(
        empresa_id=empresa_id, activo=True
    ).order_by('apellido_paterno')

    context = {
        'trabajadores': trabajadores,
    }
    return render(request, 'rrhh/trabajador_list.html', context)
@login_required
def trabajador_create_view(request):
    """
    Maneja el formulario para crear un nuevo trabajador.
    """
    # SECCION: Solo admin puede crear trabajadores
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        form = TrabajadorForm(request.POST, empresa_fija_id=empresa_id)
        if form.is_valid():
            trabajador = form.save(commit=False)
            trabajador.empresa_id = empresa_id
            trabajador.save()
            return redirect('rrhh:trabajador_list')
    else:
        form = TrabajadorForm(empresa_fija_id=empresa_id)
    
    context = {
        'form': form,
        'titulo': 'Añadir Nuevo Trabajador',
        'empresa_asignada': Empresa.objects.filter(id=empresa_id).first(),
    }
    return render(request, 'rrhh/trabajador_form.html', context)
@login_required
@require_access('rrhh', 'trabajadores', 'ver')
def trabajador_detail_view(request, pk):
    """
    Muestra la información detallada de un trabajador y sus contratos.
    """
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=pk, empresa_id=empresa_id)
    contratos = Contrato.objects.filter(trabajador=trabajador).order_by('-fecha_inicio')

    liquidaciones_qs = (
        Liquidacion.objects.filter(contrato__trabajador=trabajador)
        .select_related('contrato')
        .order_by('-ano', '-mes')
    )
    total_liquidaciones = liquidaciones_qs.count()
    ver_todas = request.GET.get('ver_todas') == '1'
    liquidaciones = liquidaciones_qs if ver_todas else liquidaciones_qs[:3]

    context = {
        'trabajador': trabajador,
        'contratos': contratos,
        'liquidaciones': liquidaciones,
        'total_liquidaciones': total_liquidaciones,
        'ver_todas_liquidaciones': ver_todas,
    }
    return render(request, 'rrhh/trabajador_detail.html', context)

@login_required
def contrato_create_view(request, trabajador_pk):
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=trabajador_pk, empresa_id=empresa_id)
    if request.method == 'POST':
        form = ContratoForm(request.POST)
        if form.is_valid():
            contrato = form.save(commit=False) # No lo guardes en la BD todavía
            contrato.trabajador = trabajador   # Asigna el trabajador
            contrato.save()                    # Ahora sí, guárdalo
            form.save_m2m()                    # conceptos_variables (M2M) requiere instancia con pk
            messages.success(request, 'Contrato guardado correctamente.')
            return redirect(f"{reverse('rrhh:trabajador_detail', kwargs={'pk': trabajador.id})}#lista-contratos")
    else:
        form = ContratoForm()

    context = {
        'form': form,
        'trabajador': trabajador,
        'sueldo_minimo_actual': _sueldo_minimo_actual(),
    }
    return render(request, 'rrhh/contrato_form.html', context)

@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def contrato_edit_view(request, pk):
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    contrato = get_object_or_404(Contrato, pk=pk, trabajador__empresa_id=empresa_id)
    trabajador = contrato.trabajador

    if request.method == 'POST':
        form = ContratoForm(request.POST, instance=contrato)
        if form.is_valid():
            form.save()
            messages.success(request, f"Contrato de {trabajador.nombre_completo} actualizado correctamente.")
            return redirect(f"{reverse('rrhh:trabajador_detail', kwargs={'pk': trabajador.id})}#lista-contratos")
    else:
        form = ContratoForm(instance=contrato)

    context = {
        'form': form,
        'trabajador': trabajador,
        'contrato': contrato,
        'sueldo_minimo_actual': _sueldo_minimo_actual(),
    }
    return render(request, 'rrhh/contrato_form.html', context)

@login_required
@require_access('rrhh', 'trabajadores', 'editar')
def gestionar_items_contrato_view(request, contrato_id):
    """
    Permite agregar bonos fijos, asignaciones o descuentos recurrentes a un contrato.
    """
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    contrato = get_object_or_404(Contrato, id=contrato_id, trabajador__empresa_id=empresa_id)

    ItemFormSet = modelformset_factory(
        ItemContrato, form=ItemContratoForm, extra=1, can_delete=True
    )

    if request.method == 'POST':
        formset = ItemFormSet(request.POST, queryset=ItemContrato.objects.filter(contrato=contrato))
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.contrato = contrato
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, 'Ítems fijos del contrato actualizados correctamente.')
            return redirect('rrhh:trabajador_detail', pk=contrato.trabajador.id)
    else:
        formset = ItemFormSet(queryset=ItemContrato.objects.filter(contrato=contrato))

    context = {
        'formset': formset,
        'contrato': contrato,
    }
    return render(request, 'rrhh/items_contrato_form.html', context)


# --- CRUD PARA CONCEPTOS VARIABLES ---

@login_required
def concepto_variable_list_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response
    
    conceptos = ConceptoVariable.objects.filter(empresa_id=empresa_id)
    return render(request, 'rrhh/conceptos/list.html', {'conceptos': conceptos})

# Formset dinámico para los tramos
TramoFormSet = inlineformset_factory(ConceptoVariable, TramoConcepto, form=TramoConceptoForm, extra=1, can_delete=True)

@login_required
def concepto_variable_create_view(request):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        form = ConceptoVariableForm(request.POST)
        formset = TramoFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            concepto = form.save(commit=False)
            concepto.empresa_id = empresa_id
            concepto.save()
            
            # Vinculamos y guardamos los tramos
            formset.instance = concepto
            formset.save()
            
            messages.success(request, f"Concepto '{concepto.nombre}' creado exitosamente.")
            return redirect('rrhh:concepto_variable_list')
    else:
        form = ConceptoVariableForm()
        formset = TramoFormSet()
    return render(request, 'rrhh/conceptos/form.html', {'form': form, 'formset': formset})

@login_required
def concepto_variable_edit_view(request, pk):
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response
    concepto = get_object_or_404(ConceptoVariable, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        form = ConceptoVariableForm(request.POST, instance=concepto)
        formset = TramoFormSet(request.POST, instance=concepto)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Concepto '{concepto.nombre}' actualizado.")
            return redirect('rrhh:concepto_variable_list')
    else:
        form = ConceptoVariableForm(instance=concepto)
        formset = TramoFormSet(instance=concepto)
    return render(request, 'rrhh/conceptos/form.html', {'form': form, 'formset': formset, 'concepto': concepto})

@login_required
def indicador_list_view(request):
    """ Muestra el historial de indicadores económicos. """
    # SECCION: Solo admin puede ver esta lista
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para ver esta página.")

    indicadores = IndicadorEconomico.objects.all()
    context = {
        'indicadores': indicadores,
    }
    return render(request, 'rrhh/indicador_list.html', context)

@login_required
def indicador_create_view(request):
    """ Maneja la creación de indicadores para un nuevo período. """
    # SECCION: Solo admin puede crear indicadores
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    initial_data = {}
    # Lógica de precarga: busca el último período guardado
    ultimo_periodo = IndicadorEconomico.objects.order_by('-ano', '-mes').first()
    if ultimo_periodo:
        # Si existe, copia sus datos para el formulario inicial
        initial_data = ultimo_periodo.__dict__
        # Limpiamos datos que no deben copiarse
        del initial_data['_state']
        del initial_data['id']
        # Proponemos el siguiente mes/año
        if initial_data['mes'] == 12:
            initial_data['mes'] = 1
            initial_data['ano'] += 1
        else:
            initial_data['mes'] += 1

    if request.method == 'POST':
        form = IndicadorEconomicoForm(request.POST)
        if form.is_valid():
            indicador = form.save()
            actualizados = _sincronizar_contratos_sueldo_minimo()
            if actualizados:
                messages.success(
                    request,
                    f"Indicadores guardados. {actualizados} contrato(s) con sueldo mínimo actualizado(s)."
                )
            return redirect('rrhh:indicador_list')
    else:
        # Muestra el formulario, precargado con datos si existen
        form = IndicadorEconomicoForm(initial=initial_data)

    context = {
        'form': form,
    }
    return render(request, 'rrhh/indicador_form.html', context)

@login_required
def indicador_edit_view(request, pk):
    """ Permite editar un indicador económico de un mes específico. """
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    indicador = get_object_or_404(IndicadorEconomico, pk=pk)
    
    if request.method == 'POST':
        form = IndicadorEconomicoForm(request.POST, instance=indicador)
        if form.is_valid():
            indicador = form.save()
            actualizados = _sincronizar_contratos_sueldo_minimo()
            msg = f"Indicadores de {indicador.mes}/{indicador.ano} actualizados correctamente."
            if actualizados:
                msg += f" {actualizados} contrato(s) con sueldo mínimo actualizado(s)."
            messages.success(request, msg)
            return redirect('rrhh:indicador_list')
    else:
        form = IndicadorEconomicoForm(instance=indicador)

    return render(request, 'rrhh/indicador_form.html', {'form': form})

@login_required
def indicador_delete_view(request, pk):
    """ Permite eliminar un período de indicadores económicos. """
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")
        
    indicador = get_object_or_404(IndicadorEconomico, pk=pk)
    if request.method == 'POST':
        indicador.delete()
        messages.success(request, f"Indicadores de {indicador.mes}/{indicador.ano} eliminados.")
        return redirect('rrhh:indicador_list')
        
    return render(request, 'rrhh/indicador_confirm_delete.html', {'indicador': indicador})

@login_required
def afp_list_view(request):
    """ Muestra la lista de AFPs y sus tasas actuales. """
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("Solo administradores pueden ver esta página.")
    afps = AFP.objects.all().order_by('nombre')
    return render(request, 'rrhh/afp_list.html', {'afps': afps})
@login_required
@require_access('rrhh', 'liquidaciones', 'ver')
def liquidacion_detail_view(request, pk):
    """
    Muestra el detalle completo de una liquidación generada, en formato de payslip.
    """
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')

    liquidacion = get_object_or_404(Liquidacion, pk=pk, contrato__trabajador__empresa_id=empresa_id)
    
    # Agrupamos los ítems para la plantilla
    haberes_imponibles = liquidacion.items.filter(tipo='HABER', es_imponible=True)
    haberes_no_imponibles = liquidacion.items.filter(tipo='HABER', es_imponible=False)
    descuentos = descuentos_para_presentacion(liquidacion)

    context = {
        'liquidacion': liquidacion,
        'haberes_imponibles': haberes_imponibles,
        'haberes_no_imponibles': haberes_no_imponibles,
        'descuentos': descuentos,
    }
    return render(request, 'rrhh/liquidacion_detail.html', context)

@login_required
def liquidacion_pdf_view(request, pk):
    """
    Renderiza una versión optimizada para impresión (PDF) de la liquidación.
    """
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id: return redirect('core:home')

    liquidacion = get_object_or_404(Liquidacion, pk=pk, contrato__trabajador__empresa_id=empresa_id)
    haberes_imponibles = liquidacion.items.filter(tipo='HABER', es_imponible=True)
    haberes_no_imponibles = liquidacion.items.filter(tipo='HABER', es_imponible=False)
    descuentos = descuentos_para_presentacion(liquidacion)

    context = {
        'liquidacion': liquidacion, 'haberes_imponibles': haberes_imponibles,
        'haberes_no_imponibles': haberes_no_imponibles, 'descuentos': descuentos,
    }
    return render(request, 'rrhh/liquidacion_pdf.html', context)


_CATEGORIAS_LINEA = {
    'haber_imponible',
    'haber_no_imponible',
    'descuento_legal',
    'descuento_otro',
}


def _respuesta_si_no_admin(request):
    if not vista_es_admin_ui(request):
        return HttpResponseForbidden('Solo administradores pueden realizar esta acción.')
    return None


def _categoria_de_item(item):
    if item.tipo == 'HABER':
        return 'haber_imponible' if item.es_imponible else 'haber_no_imponible'
    return 'descuento_legal' if item.es_legal else 'descuento_otro'


def _lineas_post(request):
    nombres = request.POST.getlist('linea_nombre')
    montos = request.POST.getlist('linea_monto')
    categorias = request.POST.getlist('linea_categoria')
    lineas = []
    for nombre, monto, categoria in zip(nombres, montos, categorias):
        nombre = (nombre or '').strip()
        monto_txt = (monto or '').strip().replace('.', '').replace(' ', '')
        if not nombre and not monto_txt:
            continue
        if not nombre:
            raise ValueError('Cada línea con monto necesita un nombre.')
        if categoria not in _CATEGORIAS_LINEA:
            raise ValueError(f'Tipo inválido en «{nombre}».')
        if ',' in monto_txt or not monto_txt.isdigit():
            raise ValueError(f'Monto inválido en «{nombre}». Usa un entero, por ejemplo 150000.')
        lineas.append({
            'nombre': nombre[:100],
            'monto': int(monto_txt),
            'categoria': categoria,
        })
    if not lineas:
        raise ValueError('Agrega al menos una línea con nombre y monto.')
    return lineas


def _aplicar_lineas_manuales(liquidacion, lineas, dias):
    cuota = CuotaPrestamoLiquidacion.objects.filter(liquidacion=liquidacion).select_related('prestamo').first()
    etiqueta_prestamo = ''
    if cuota and cuota.prestamo.descripcion:
        etiqueta_prestamo = cuota.prestamo.descripcion.strip()

    liquidacion.items.all().delete()
    haberes_imp = haberes_no = legales = varios = asig = 0
    monto_cuota = None
    for linea in lineas:
        es_haber = linea['categoria'].startswith('haber')
        es_imponible = linea['categoria'] == 'haber_imponible'
        es_legal = linea['categoria'] == 'descuento_legal'
        ItemLiquidacion.objects.create(
            liquidacion=liquidacion,
            nombre=linea['nombre'],
            monto=linea['monto'],
            tipo='HABER' if es_haber else 'DESCUENTO',
            es_imponible=es_imponible if es_haber else False,
            es_legal=es_legal,
        )
        if es_imponible:
            haberes_imp += linea['monto']
        elif es_haber:
            haberes_no += linea['monto']
            if linea['nombre'].lower().startswith('asignación familiar') or linea['nombre'].lower().startswith('asignacion familiar'):
                asig += linea['monto']
        elif es_legal:
            legales += linea['monto']
        else:
            varios += linea['monto']
            nombre = linea['nombre']
            if cuota and (
                (etiqueta_prestamo and nombre == etiqueta_prestamo)
                or nombre.lower().startswith('cuota préstamo')
                or nombre.lower().startswith('cuota prestamo')
            ):
                monto_cuota = linea['monto']

    if cuota:
        if monto_cuota is None:
            cuota.delete()
        else:
            cuota.monto = monto_cuota
            cuota.save(update_fields=['monto'])

    liquidacion.dias_trabajados = dias
    liquidacion.total_haberes_imponibles = haberes_imp
    liquidacion.total_haberes_no_imponibles = haberes_no
    liquidacion.total_descuentos_legales = legales
    liquidacion.total_descuentos_varios = varios
    liquidacion.total_asignacion_familiar = asig
    liquidacion.sueldo_liquido = (haberes_imp + haberes_no) - (legales + varios)
    liquidacion.manual = True
    liquidacion.save()


def _contexto_lineas(liquidacion, lineas, error=''):
    return {
        'modo': 'lineas',
        'liquidacion': liquidacion,
        'trabajador': liquidacion.contrato.trabajador,
        'lineas': lineas,
        'error': error,
        'dias_trabajados': liquidacion.dias_trabajados,
    }


@login_required
@require_POST
def liquidacion_eliminar_view(request, pk):
    denegado = _respuesta_si_no_admin(request)
    if denegado:
        return denegado
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    liquidacion = get_object_or_404(
        Liquidacion, pk=pk, contrato__trabajador__empresa_id=empresa_id,
    )
    trabajador = liquidacion.contrato.trabajador
    periodo = f'{liquidacion.mes}/{liquidacion.ano}'
    liquidacion.delete()
    messages.success(request, f'Liquidación {periodo} de {trabajador.nombre_completo} eliminada.')
    return redirect(f"{reverse('rrhh:trabajador_detail', args=[trabajador.pk])}#historial-liquidaciones")


@login_required
def liquidacion_editar_view(request, pk):
    denegado = _respuesta_si_no_admin(request)
    if denegado:
        return denegado
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    liquidacion = get_object_or_404(
        Liquidacion.objects.select_related('contrato__trabajador'),
        pk=pk,
        contrato__trabajador__empresa_id=empresa_id,
    )

    if request.method == 'POST' and request.POST.get('accion') == 'recalcular':
        try:
            nueva = procesar_liquidacion(
                liquidacion.contrato, liquidacion.mes, liquidacion.ano, reemplazar_manual=True,
            )
        except Exception as exc:
            messages.error(request, f'No se pudo recalcular: {exc}')
            return redirect('rrhh:liquidacion_editar', pk=liquidacion.pk)
        if nueva is None:
            messages.error(request, 'No se pudo recalcular: el trabajador no tiene días trabajados en ese mes.')
            return redirect('rrhh:liquidacion_editar', pk=liquidacion.pk)
        messages.success(request, f'Liquidación {nueva.mes}/{nueva.ano} recalculada con el motor.')
        return redirect('rrhh:liquidacion_detail', pk=nueva.pk)

    if request.method == 'POST':
        try:
            dias = int(request.POST.get('dias_trabajados') or 0)
            if dias < 0 or dias > 31:
                raise ValueError('Los días trabajados deben estar entre 0 y 31.')
            lineas = _lineas_post(request)
            with transaction.atomic():
                _aplicar_lineas_manuales(liquidacion, lineas, dias)
        except ValueError as exc:
            lineas_error = []
            for nombre, monto, categoria in zip(
                request.POST.getlist('linea_nombre'),
                request.POST.getlist('linea_monto'),
                request.POST.getlist('linea_categoria'),
            ):
                lineas_error.append({'nombre': nombre, 'monto': monto, 'categoria': categoria})
            context = _contexto_lineas(liquidacion, lineas_error or [{'nombre': '', 'monto': '', 'categoria': 'haber_imponible'}], str(exc))
            context['dias_trabajados'] = request.POST.get('dias_trabajados') or liquidacion.dias_trabajados
            return render(request, 'rrhh/liquidacion_manual.html', context)
        messages.success(request, f'Liquidación {liquidacion.mes}/{liquidacion.ano} guardada como manual.')
        return redirect('rrhh:liquidacion_detail', pk=liquidacion.pk)

    lineas = [
        {'nombre': item.nombre, 'monto': item.monto, 'categoria': _categoria_de_item(item)}
        for item in liquidacion.items.order_by('id')
    ]
    if not lineas:
        lineas = [{'nombre': '', 'monto': '', 'categoria': 'haber_imponible'}]
    return render(request, 'rrhh/liquidacion_manual.html', _contexto_lineas(liquidacion, lineas))


@login_required
def liquidacion_forzar_view(request, trabajador_pk):
    denegado = _respuesta_si_no_admin(request)
    if denegado:
        return denegado
    empresa_id, redirect_response = ensure_empresa_operativa(request)
    if redirect_response:
        return redirect_response

    trabajador = get_object_or_404(Trabajador, pk=trabajador_pk, empresa_id=empresa_id)
    contratos = Contrato.objects.filter(trabajador=trabajador).order_by('-fecha_inicio')
    today = datetime.now()

    if request.method == 'POST' and request.POST.get('accion') == 'guardar':
        contrato = get_object_or_404(contratos, pk=request.POST.get('contrato_id'))
        try:
            mes = int(request.POST.get('mes'))
            ano = int(request.POST.get('ano'))
            dias = int(request.POST.get('dias_trabajados') or 30)
            if mes < 1 or mes > 12:
                raise ValueError('El mes no es válido.')
            if ano < 2000 or ano > today.year + 1:
                raise ValueError('El año no es válido.')
            if dias < 0 or dias > 31:
                raise ValueError('Los días trabajados deben estar entre 0 y 31.')
            if Liquidacion.objects.filter(contrato=contrato, mes=mes, ano=ano).exists():
                raise ValueError('Ya existe una liquidación de ese período. Ábrela para editarla.')
            lineas = _lineas_post(request)
        except ValueError as exc:
            lineas_error = []
            for nombre, monto, categoria in zip(
                request.POST.getlist('linea_nombre'),
                request.POST.getlist('linea_monto'),
                request.POST.getlist('linea_categoria'),
            ):
                lineas_error.append({'nombre': nombre, 'monto': monto, 'categoria': categoria})
            return render(request, 'rrhh/liquidacion_manual.html', {
                'modo': 'lineas',
                'trabajador': trabajador,
                'contrato': contrato,
                'mes': request.POST.get('mes'),
                'ano': request.POST.get('ano'),
                'dias_trabajados': request.POST.get('dias_trabajados') or 30,
                'lineas': lineas_error or [{'nombre': '', 'monto': '', 'categoria': 'haber_imponible'}],
                'error': str(exc),
            })

        indicador = IndicadorEconomico.objects.filter(mes=mes, ano=ano).first()
        ultimo = calendar.monthrange(ano, mes)[1]
        with transaction.atomic():
            liquidacion = Liquidacion.objects.create(
                contrato=contrato,
                mes=mes,
                ano=ano,
                fecha_emision=date(ano, mes, ultimo),
                dias_trabajados=dias,
                fecha_ingreso_contrato=contrato.fecha_inicio,
                cargo_contrato=(contrato.cargo or '')[:120],
                uf_valor=indicador.uf if indicador else 0,
                utm_valor=indicador.utm if indicador else 0,
                sueldo_minimo_valor=indicador.sueldo_minimo if indicador else 0,
                afp_nombre=contrato.afp.nombre,
                afp_tasa=contrato.afp.tasa_dependiente,
                salud_nombre=contrato.sistema_salud.nombre,
                manual=True,
            )
            _aplicar_lineas_manuales(liquidacion, lineas, dias)
        messages.success(request, f'Liquidación {mes}/{ano} ingresada a mano.')
        return redirect('rrhh:liquidacion_detail', pk=liquidacion.pk)

    if request.method == 'POST':
        contrato = get_object_or_404(contratos, pk=request.POST.get('contrato_id'))
        try:
            mes = int(request.POST.get('mes'))
            ano = int(request.POST.get('ano'))
        except (TypeError, ValueError):
            messages.error(request, 'Indica mes y año válidos.')
            return redirect('rrhh:liquidacion_forzar', trabajador_pk=trabajador.pk)
        existente = Liquidacion.objects.filter(contrato=contrato, mes=mes, ano=ano).first()
        if existente:
            return render(request, 'rrhh/liquidacion_manual.html', {
                'modo': 'existe',
                'trabajador': trabajador,
                'contrato': contrato,
                'mes': mes,
                'ano': ano,
                'liquidacion': existente,
            })
        return render(request, 'rrhh/liquidacion_manual.html', {
            'modo': 'lineas',
            'trabajador': trabajador,
            'contrato': contrato,
            'mes': mes,
            'ano': ano,
            'dias_trabajados': 30,
            'lineas': [{'nombre': '', 'monto': '', 'categoria': 'haber_imponible'}],
            'error': '',
        })

    return render(request, 'rrhh/liquidacion_manual.html', {
        'modo': 'elegir',
        'trabajador': trabajador,
        'contratos': contratos,
        'mes': today.month,
        'ano': today.year,
    })


@login_required
@require_access('rrhh', 'liquidaciones', 'ver')
def libro_remuneraciones_view(request):
    """
    Muestra el reporte consolidado de todos los trabajadores de la empresa en un mes.
    """
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id: return redirect('core:home')
    empresa = get_object_or_404(Empresa, id=empresa_id)

    today = datetime.now()
    mes = int(request.GET.get('mes', today.month))
    ano = int(request.GET.get('ano', today.year))
    filas, totales = libro_del_periodo(empresa, mes, ano)

    if request.GET.get('formato') == 'excel':
        contenido = excel_libro(empresa, mes, ano, filas, totales)
        nombre = f'libro_remuneraciones_{empresa.rut}_{mes:02d}_{ano}.xlsx'
        response = HttpResponse(
            contenido,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    context = {
        'mes_seleccionado': mes,
        'ano_seleccionado': ano,
        'mes_nombre': MESES[mes],
        'meses_opciones': range(1, 13),
        'anos_opciones': range(2024, today.year + 2),
        'filas': filas,
        'totales': totales,
        'columnas': COLUMNAS,
        'empresa': empresa,
    }
    return render(request, 'rrhh/libro_remuneraciones.html', context)

@login_required
def api_get_indicadores_economicos(request, ano, mes):
    """
    API interna que consulta mindicador.cl para obtener UF y UTM de un período.
    """
    if request.user.perfil.rol != 'admin':
        return JsonResponse({'success': False, 'error': 'Acceso no autorizado'}, status=403)

    # Para la UF, usamos el último día del mes. Para la UTM, el valor es mensual.
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fecha_str = f"{ultimo_dia:02d}-{mes:02d}-{ano}"
    
    data = {'uf': None, 'utm': None}
    
    try:
        # 1. UF
        res_uf = requests.get(f'https://mindicador.cl/api/uf/{fecha_str}', timeout=3)
        if res_uf.status_code == 200:
            api_data = res_uf.json()
            if api_data.get('serie') and api_data['serie']:
                data['uf'] = api_data['serie'][0]['valor']

        # 2. UTM
        res_utm = requests.get(f'https://mindicador.cl/api/utm/{fecha_str}', timeout=3)
        if res_utm.status_code == 200:
            api_data = res_utm.json()
            if api_data.get('serie') and api_data['serie']:
                data['utm'] = api_data['serie'][0]['valor']
        
        return JsonResponse({'success': True, 'uf': data['uf'], 'utm': data['utm']})

    except requests.exceptions.RequestException as e:
        return JsonResponse({'success': False, 'error': f'Error al conectar con la API externa: {e}'})
@login_required
def planilla_cobranza_view(request):
    if request.user.perfil.rol != 'admin':
        return redirect('core:home')

    # Si no hay año en la URL, usamos el actual
    anio_sel = int(request.GET.get('anio', datetime.now().year))
    
    # Filtramos empresas y sus cobros de ese año específico
    empresas = Empresa.objects.prefetch_related(
        models.Prefetch('cobros', queryset=RegistroCobro.objects.filter(ano=anio_sel))
    ).all()

    context = {
        'empresas': empresas,
        'anio_sel': anio_sel,
        'anios_opciones': range(2024, datetime.now().year + 2),
        'meses': range(1, 13),
    }
    return render(request, 'rrhh/planilla_cobranza.html', context)

@login_required
@require_access('rrhh', 'novedades', 'editar')
def ingresar_novedades_view(request):
    """
    Permite ingresar las novedades (ausencias, horas extras, etc.) para todos
    los trabajadores de una empresa en un mes específico.
    """
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para continuar.")
        return redirect('core:home')

    # Buscamos los trabajadores activos de la empresa que tienen un contrato vigente
    trabajadores_empresa = Trabajador.objects.filter(
        empresa_id=empresa_id, 
        activo=True,
        contratos__vigente=True
    ).distinct()

    # --- NUEVA LÓGICA: OBTENER LA UNIÓN DE CONCEPTOS ---
    contratos_activos = Contrato.objects.filter(trabajador__in=trabajadores_empresa, vigente=True)
    union_conceptos_ids = set(ConceptoVariable.objects.filter(contrato__in=contratos_activos).values_list('id', flat=True))
    conceptos_para_tabla = ConceptoVariable.objects.filter(id__in=union_conceptos_ids)

    # Creamos el factory para el formset
    NovedadFormSet = modelformset_factory(
        NovedadMensual,
        form=NovedadMensualForm,
        extra=0 # No mostrar formularios extra vacíos
    )

    # Obtenemos el mes y año de la URL o usamos el mes actual
    today = datetime.now()
    mes_seleccionado = int(request.GET.get('mes', today.month))
    ano_seleccionado = int(request.GET.get('ano', today.year))

    # Para cada trabajador, nos aseguramos de que exista un registro de NovedadMensual para el período.
    for trabajador in trabajadores_empresa:
        NovedadMensual.objects.get_or_create(
            trabajador=trabajador,
            mes=mes_seleccionado,
            ano=ano_seleccionado
        )

    # Filtramos el queryset del formset para que solo muestre las novedades de este período y empresa
    queryset = NovedadMensual.objects.filter(
        trabajador__in=trabajadores_empresa,
        mes=mes_seleccionado,
        ano=ano_seleccionado
    ).select_related('trabajador')

    if request.method == 'POST':
        formset = NovedadFormSet(request.POST, queryset=queryset, form_kwargs={'conceptos': conceptos_para_tabla})
        if formset.is_valid():
            formset.save()
            messages.success(request, f"Novedades para {mes_seleccionado}/{ano_seleccionado} guardadas correctamente.")
            return redirect(f"{request.path}?mes={mes_seleccionado}&ano={ano_seleccionado}")
        else:
            messages.error(request, "Hubo un error al guardar. Por favor, revisa los datos ingresados.")
    else:
        formset = NovedadFormSet(queryset=queryset, form_kwargs={'conceptos': conceptos_para_tabla})

    # --- NUEVA LÓGICA: ADJUNTAR CONCEPTOS APLICABLES A CADA FORMULARIO ---
    for form in formset:
        active_contract = form.instance.trabajador.contratos.filter(vigente=True).first()
        if active_contract:
            form.applicable_concept_ids = set(active_contract.conceptos_variables.values_list('id', flat=True))
        else:
            form.applicable_concept_ids = set()

    context = {
        'formset': formset,
        'mes_seleccionado': mes_seleccionado,
        'ano_seleccionado': ano_seleccionado,
        'anos_opciones': range(2024, today.year + 2),
        'meses_opciones': range(1, 13),
        'conceptos': conceptos_para_tabla,
    }
    return render(request, 'rrhh/novedades/ingresar_novedades.html', context)

@login_required
def cargar_datos_base_rrhh_view(request):
    """
    Carga automáticamente las AFPs y Sistemas de Salud (Isapres/Fonasa) 
    para poder crear contratos sin tener que escribirlas a mano.
    """
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("Solo administradores pueden cargar datos base.")
        
    # AFPs con tasas base referenciales
    afps = [
        ("Capital", 11.44), ("Cuprum", 11.44), ("Habitat", 11.27),
        ("Modelo", 10.58), ("PlanVital", 11.16), ("Provida", 11.45), ("Uno", 10.69)
    ]
    for nombre, tasa in afps:
        AFP.objects.get_or_create(nombre=nombre, defaults={'tasa_dependiente': tasa})
        
    # Sistemas de Salud
    salud = ["FONASA", "Banmédica", "Colmena", "Consalud", "CruzBlanca", "Nueva Masvida", "Vida Tres"]
    for nombre in salud:
        SistemaSalud.objects.get_or_create(nombre=nombre)
        
    messages.success(request, "Datos base de AFPs e Isapres cargados exitosamente. Ya puedes crear contratos.")
    return redirect('core:empresa_dashboard')

@login_required
def cargar_indicadores_base_view(request):
    """
    Carga los indicadores económicos históricos (UF, UTM, Sueldo Mínimo, Topes Previred)
    solo para los meses donde hubo cambios importantes. El motor heredará estos valores
    hacia los meses vacíos.
    """
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("Solo administradores pueden cargar datos históricos.")

    # 1. Encontrar la fecha del contrato más antiguo para saber desde dónde empezar
    contrato_mas_antiguo = Contrato.objects.order_by('fecha_inicio').first()
    if contrato_mas_antiguo:
        ano_iter = contrato_mas_antiguo.fecha_inicio.year
        mes_iter = contrato_mas_antiguo.fecha_inicio.month
    else:
        # Si no hay contratos en todo el sistema, partimos por defecto en Enero 2024
        ano_iter = 2024
        mes_iter = 1

    # 2. Diccionario de "Puntos de Inflexión" (meses donde la ley cambió los topes)
    datos_inflexion = {
        (2024, 1): {
            'uf': 36800.00, 'utm': 64666, 'sueldo_minimo': 460000, 'tasa_sis': 1.49,
            'tope_imponible_afp_uf': 84.3, 'tope_imponible_afp_pesos': 3102240,
            'tope_imponible_cesantia_uf': 122.6, 'tope_imponible_cesantia_pesos': 4511680,
            'asig_familiar_tramo_a_monto': 20328, 'asig_familiar_tramo_a_limite': 539328,
            'asig_familiar_tramo_b_monto': 12475, 'asig_familiar_tramo_b_limite': 787746,
            'asig_familiar_tramo_c_monto': 3942, 'asig_familiar_tramo_c_limite': 1228614,
            'tasa_afp_capital': 11.44, 'tasa_afp_cuprum': 11.44, 'tasa_afp_habitat': 11.27,
            'tasa_afp_modelo': 10.58, 'tasa_afp_planvital': 11.16, 'tasa_afp_provida': 11.45,
            'tasa_afp_uno': 10.69
        },
        (2024, 7): {
            'uf': 37500.00, 'utm': 65901, 'sueldo_minimo': 500000, 'tasa_sis': 1.49,
            'tope_imponible_afp_uf': 84.3, 'tope_imponible_afp_pesos': 3161250,
            'tope_imponible_cesantia_uf': 122.6, 'tope_imponible_cesantia_pesos': 4597500,
            'asig_familiar_tramo_a_monto': 21243, 'asig_familiar_tramo_a_limite': 586227,
            'asig_familiar_tramo_b_monto': 13036, 'asig_familiar_tramo_b_limite': 856410,
            'asig_familiar_tramo_c_monto': 4119, 'asig_familiar_tramo_c_limite': 1335450,
            'tasa_afp_capital': 11.44, 'tasa_afp_cuprum': 11.44, 'tasa_afp_habitat': 11.27,
            'tasa_afp_modelo': 10.58, 'tasa_afp_planvital': 11.16, 'tasa_afp_provida': 11.45,
            'tasa_afp_uno': 10.69
        }
    }

    hoy = datetime.now()
    # Buscamos el punto de inflexión más cercano hacia atrás para usarlo como base
    claves_ordenadas = sorted(datos_inflexion.keys(), reverse=True)
    ultimo_dato_conocido = datos_inflexion[claves_ordenadas[0]] # Por defecto, el más reciente
    for clave in claves_ordenadas:
        if clave <= (ano_iter, mes_iter):
            ultimo_dato_conocido = datos_inflexion[clave]
            break

    meses_creados = 0

    # 3. Bucle: Desde el contrato más antiguo hasta el mes actual
    while (ano_iter < hoy.year) or (ano_iter == hoy.year and mes_iter <= hoy.month):
        
        # Si este mes específico tuvo un cambio de ley, actualizamos nuestra base temporal
        if (ano_iter, mes_iter) in datos_inflexion:
            ultimo_dato_conocido = datos_inflexion[(ano_iter, mes_iter)]
            
        # get_or_create NO sobreescribe si el mes ya existe (por si lo editaste a mano)
        _, creado = IndicadorEconomico.objects.get_or_create(ano=ano_iter, mes=mes_iter, defaults=ultimo_dato_conocido)
        if creado:
            meses_creados += 1
            
        mes_iter += 1
        if mes_iter > 12:
            mes_iter = 1
            ano_iter += 1
            
    messages.success(request, f"¡Éxito! Se revisaron los periodos y se generaron {meses_creados} meses nuevos heredando los valores correspondientes.")
    return redirect('rrhh:indicador_list')