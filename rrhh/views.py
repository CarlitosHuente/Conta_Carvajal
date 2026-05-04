# rrhh/views.py

from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.forms import modelformset_factory, inlineformset_factory
from .models import Contrato, Trabajador, IndicadorEconomico, NovedadMensual, AFP, SistemaSalud, ItemContrato, Liquidacion, ConceptoVariable, TramoConcepto
from core.models import Empresa, PerfilUsuario
from .forms import EmpresaForm, TrabajadorForm, ContratoForm, IndicadorEconomicoForm, NovedadMensualForm, ItemContratoForm, ConceptoVariableForm, TramoConceptoForm
from django.contrib.auth.decorators import login_required
from datetime import datetime
import requests
from django.urls import reverse
from .motor_remuneraciones import procesar_liquidacion
from django.db.models import Prefetch
import calendar
from .models import RegistroCobro
from django.db import models
from core.permissions import require_access



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
        mes = int(request.POST.get('mes'))
        ano = int(request.POST.get('ano'))
        accion = request.POST.get('accion', 'procesar')

        contratos_activos = Contrato.objects.filter(trabajador__empresa=empresa, vigente=True)

        # Detectamos trabajadores sin novedad mensual para guiar el proceso en vez de fallar.
        for contrato in contratos_activos:
            novedad = NovedadMensual.objects.filter(
                trabajador=contrato.trabajador,
                mes=mes,
                ano=ano
            ).first()
            if not novedad:
                pendientes_novedades.append(contrato.trabajador)

        if pendientes_novedades and accion != 'autocompletar':
            messages.warning(
                request,
                "Faltan datos minimos de novedades para algunos trabajadores. "
                "Completa en el asistente rapido y vuelve a procesar."
            )
            context = {
                'mes_seleccionado': mes,
                'ano_seleccionado': ano,
                'anos_opciones': range(2024, datetime.now().year + 2),
                'meses_opciones': range(1, 13),
                'liquidaciones_generadas': Liquidacion.objects.filter(
                    contrato__trabajador__empresa=empresa, mes=mes, ano=ano
                ).select_related('contrato__trabajador').order_by('contrato__trabajador__apellido_paterno'),
                'pendientes_novedades': pendientes_novedades,
            }
            return render(request, 'rrhh/crear_liquidacion.html', context)

        if accion == 'autocompletar' and pendientes_novedades:
            for trabajador in pendientes_novedades:
                NovedadMensual.objects.get_or_create(
                    trabajador=trabajador,
                    mes=mes,
                    ano=ano,
                    defaults={
                        'dias_ausencia': 0,
                        'dias_licencia': 0,
                        'bono_esporadico': 0,
                        'descuento_esporadico': 0,
                        'datos_variables': {}
                    }
                )
            messages.info(
                request,
                f"Asistente rapido aplicado: {len(pendientes_novedades)} trabajador(es) con datos minimos creados."
            )
            # Recalcular lista de contratos (sin pendientes) antes de procesar
            contratos_activos = Contrato.objects.filter(trabajador__empresa=empresa, vigente=True)

        exitos = 0
        fallos = 0
        nombres_fallidos = []

        for contrato in contratos_activos:
            try:
                procesar_liquidacion(contrato, mes, ano)
                exitos += 1
            except Exception as e:
                fallos += 1
                nombres_fallidos.append(f"{contrato.trabajador.nombre_completo} (Error: {e})")
        
        if exitos > 0:
            messages.success(request, f"Proceso finalizado. Se generaron/actualizaron {exitos} liquidaciones exitosamente.")
        if fallos > 0:
            messages.error(request, f"Fallaron {fallos} liquidaciones: {', '.join(nombres_fallidos)}")

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
    Muestra la lista de todos los trabajadores.
    """
    # SECCION: Filtro por Rol
    if request.user.perfil.rol == 'admin':
        # El admin ve todos los trabajadores activos
        trabajadores = Trabajador.objects.filter(activo=True).order_by('apellido_paterno')
    else:
        # El cliente SOLO ve los trabajadores de su propia empresa
        empresa_id = request.user.perfil.empresa_id
        if not empresa_id:
            trabajadores = Trabajador.objects.none() # Devuelve una lista vacía si no tiene empresa
        else:
            trabajadores = Trabajador.objects.filter(empresa_id=empresa_id, activo=True).order_by('apellido_paterno')

    context = {
        'trabajadores': trabajadores
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

    empresa_activa_id = request.session.get('empresa_activa_id')

    if request.method == 'POST':
        form = TrabajadorForm(request.POST, empresa_fija_id=empresa_activa_id)
        if form.is_valid():
            trabajador = form.save(commit=False)
            if empresa_activa_id:
                trabajador.empresa_id = empresa_activa_id
            trabajador.save()
            return redirect('rrhh:trabajador_list')
    else:
        form = TrabajadorForm(empresa_fija_id=empresa_activa_id)
    
    context = {
        'form': form,
        'titulo': 'Añadir Nuevo Trabajador', # Un título para reutilizar la plantilla
        'empresa_asignada': Empresa.objects.filter(id=empresa_activa_id).first() if empresa_activa_id else None,
    }
    return render(request, 'rrhh/trabajador_form.html', context)
@login_required
def trabajador_detail_view(request, pk):
    """
    Muestra la información detallada de un trabajador y sus contratos.
    'pk' es la "Primary Key" o ID del trabajador.
    """
    trabajador = Trabajador.objects.get(id=pk)
    # SECCION: Filtro por Rol
    # Un cliente solo puede ver trabajadores de su propia empresa
    if request.user.perfil.rol == 'cliente' and trabajador.empresa != request.user.perfil.empresa:
        return HttpResponseForbidden("No tienes permiso para ver este trabajador.")

    # Obtenemos todos los contratos asociados a este trabajador
    contratos = Contrato.objects.filter(trabajador=trabajador).order_by('-fecha_inicio')

    context = {
        'trabajador': trabajador,
        'contratos': contratos
    }
    return render(request, 'rrhh/trabajador_detail.html', context)

@login_required
def contrato_create_view(request, trabajador_pk):
    # SECCION: Solo admin puede crear contratos
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    trabajador = Trabajador.objects.get(id=trabajador_pk)
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
    }
    return render(request, 'rrhh/contrato_form.html', context)

@login_required
def contrato_edit_view(request, pk):
    # SECCION: Solo admin puede editar contratos
    if request.user.perfil.rol != 'admin':
        return HttpResponseForbidden("No tienes permiso para realizar esta acción.")

    contrato = get_object_or_404(Contrato, pk=pk)
    trabajador = contrato.trabajador

    if request.method == 'POST':
        form = ContratoForm(request.POST, instance=contrato)
        if form.is_valid():
            form.save()
            messages.success(request, f"Contrato de {trabajador.nombre_completo} actualizado correctamente.")
            return redirect(f"{reverse('rrhh:trabajador_detail', kwargs={'pk': trabajador.id})}#lista-contratos")
    else:
        form = ContratoForm(instance=contrato)

    context = {'form': form, 'trabajador': trabajador, 'contrato': contrato}
    return render(request, 'rrhh/contrato_form.html', context)

@login_required
def gestionar_items_contrato_view(request, contrato_id):
    """
    Permite agregar bonos fijos, asignaciones o descuentos recurrentes a un contrato.
    """
    contrato = get_object_or_404(Contrato, id=contrato_id)
    
    # Verificación RBAC (El cliente solo ve contratos de su empresa)
    if request.user.perfil.rol == 'cliente' and contrato.trabajador.empresa != request.user.perfil.empresa:
        return HttpResponseForbidden("No tienes permiso para modificar este contrato.")

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
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Selecciona una empresa para gestionar sus conceptos de pago.")
        return redirect('core:home')
    
    conceptos = ConceptoVariable.objects.filter(empresa_id=empresa_id)
    return render(request, 'rrhh/conceptos/list.html', {'conceptos': conceptos})

# Formset dinámico para los tramos
TramoFormSet = inlineformset_factory(ConceptoVariable, TramoConcepto, form=TramoConceptoForm, extra=1, can_delete=True)

@login_required
def concepto_variable_create_view(request):
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id: return redirect('core:home')

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
    empresa_id = request.session.get('empresa_activa_id')
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
            form.save()
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
            form.save()
            messages.success(request, f"Indicadores de {indicador.mes}/{indicador.ano} actualizados correctamente.")
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
    descuentos = liquidacion.items.filter(tipo='DESCUENTO')

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
    descuentos = liquidacion.items.filter(tipo='DESCUENTO')

    context = {
        'liquidacion': liquidacion, 'haberes_imponibles': haberes_imponibles,
        'haberes_no_imponibles': haberes_no_imponibles, 'descuentos': descuentos,
    }
    return render(request, 'rrhh/liquidacion_pdf.html', context)

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

    liquidaciones = Liquidacion.objects.filter(
        contrato__trabajador__empresa=empresa, mes=mes, ano=ano
    ).select_related('contrato__trabajador').order_by('contrato__trabajador__apellido_paterno')

    context = {
        'mes_seleccionado': mes, 'ano_seleccionado': ano,
        'meses_opciones': range(1, 13), 'anos_opciones': range(2024, today.year + 2),
        'liquidaciones': liquidaciones,
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