# rrhh/views.py

from django.http import JsonResponse
from django.shortcuts import render, redirect # Asegúrate de que redirect esté importado
from .models import Contrato, Empresa, Trabajador, IndicadorEconomico # Añade Empresa a los modelos importados
from .forms import EmpresaForm, TrabajadorForm, ContratoForm, IndicadorEconomicoForm # ¡Importa el nuevo formulario!


# ... (las otras vistas de liquidación pueden quedar abajo)

def empresa_list_view(request):
    """
    Esta vista muestra la lista de todas las empresas.
    """
    empresas = Empresa.objects.all() # Obtenemos todas las empresas de la BD
    context = {
        'empresas': empresas,
    }
    return render(request, 'rrhh/empresa_list.html', context)

def empresa_create_view(request):
    """
    Esta vista maneja el formulario para crear una nueva empresa.
    """
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

def crear_liquidacion_view(request):
    """
    Esta vista muestra la página/formulario para crear una nueva liquidación.
    """
    # Obtenemos todos los contratos vigentes para mostrarlos en el menú desplegable
    contratos = Contrato.objects.filter(vigente=True)
    
    context = {
        'contratos': contratos,
    }
    return render(request, 'rrhh/crear_liquidacion.html', context)


def cargar_datos_contrato_api(request, contrato_id):
    """
    Esta es una 'mini-API' interna. JavaScript la llamará cuando el usuario
    seleccione un contrato. Devuelve los datos del contrato en formato JSON.
    """
    try:
        contrato = Contrato.objects.get(id=contrato_id)
        
        # Preparamos la lista de haberes fijos
        haberes = []
        
        # 1. Haberes fijos del Contrato
        haberes.append({'nombre': 'Sueldo Base', 'monto': contrato.sueldo_base, 'tipo': 'HABER', 'es_imponible': True})
        if contrato.colacion > 0:
            haberes.append({'nombre': 'Colación', 'monto': contrato.colacion, 'tipo': 'HABER', 'es_imponible': False})
        if contrato.movilizacion > 0:
            haberes.append({'nombre': 'Movilización', 'monto': contrato.movilizacion, 'tipo': 'HABER', 'es_imponible': False})
        
        # 2. Copiamos todos los Items Recurrentes del Contrato
        for item in contrato.items_recurrentes.all():
            if item.tipo == 'HABER':
                haberes.append({
                    'nombre': item.nombre, 'monto': item.monto,
                    'tipo': item.tipo, 'es_imponible': item.es_imponible
                })

        return JsonResponse({'success': True, 'haberes': haberes})

    except Contrato.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Contrato no encontrado'})
    
# rrhh/views.py




def trabajador_list_view(request):
    """
    Muestra la lista de todos los trabajadores.
    """
    trabajadores = Trabajador.objects.filter(activo=True).order_by('apellido_paterno')
    context = {
        'trabajadores': trabajadores
    }
    return render(request, 'rrhh/trabajador_list.html', context)

def trabajador_create_view(request):
    """
    Maneja el formulario para crear un nuevo trabajador.
    """
    if request.method == 'POST':
        form = TrabajadorForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('rrhh:trabajador_list')
    else:
        form = TrabajadorForm()
    
    context = {
        'form': form,
        'titulo': 'Añadir Nuevo Trabajador' # Un título para reutilizar la plantilla
    }
    return render(request, 'rrhh/trabajador_form.html', context)

def trabajador_detail_view(request, pk):
    """
    Muestra la información detallada de un trabajador y sus contratos.
    'pk' es la "Primary Key" o ID del trabajador.
    """
    trabajador = Trabajador.objects.get(id=pk)
    # Obtenemos todos los contratos asociados a este trabajador
    contratos = Contrato.objects.filter(trabajador=trabajador).order_by('-fecha_inicio')

    context = {
        'trabajador': trabajador,
        'contratos': contratos
    }
    return render(request, 'rrhh/trabajador_detail.html', context)

def contrato_create_view(request, trabajador_pk):
    trabajador = Trabajador.objects.get(id=trabajador_pk)
    if request.method == 'POST':
        form = ContratoForm(request.POST)
        if form.is_valid():
            contrato = form.save(commit=False) # No lo guardes en la BD todavía
            contrato.trabajador = trabajador   # Asigna el trabajador
            contrato.save()                    # Ahora sí, guárdalo
            return redirect('rrhh:trabajador_detail', pk=trabajador.id)
    else:
        form = ContratoForm()

    context = {
        'form': form,
        'trabajador': trabajador,
    }
    return render(request, 'rrhh/contrato_form.html', context)

def indicador_list_view(request):
    """ Muestra el historial de indicadores económicos. """
    indicadores = IndicadorEconomico.objects.all()
    context = {
        'indicadores': indicadores,
    }
    return render(request, 'rrhh/indicador_list.html', context)

def indicador_create_view(request):
    """ Maneja la creación de indicadores para un nuevo período. """
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