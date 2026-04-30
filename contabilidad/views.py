import os
import re
import calendar
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.conf import settings
from django.urls import reverse

from .extractor import extraer_datos_f29
from .models import CodigoF29, DeclaracionF29, CuentaContable, PlantillaCentralizacion, LineaPlantilla, AsientoContable, LineaAsiento
from .forms import CuentaContableForm
from core.models import Empresa
from core.permissions import require_access
from .plan_base import PLAN_CUENTAS_BASE

@login_required
@require_access('contabilidad', 'f29', 'ver')
def f29_lista_view(request):
    """Muestra el historial de F29 cargados según el rol del usuario."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para ver sus declaraciones.")
        return redirect('core:home')
    
    declaraciones = DeclaracionF29.objects.filter(empresa_id=empresa_id).order_by('-ano', '-mes').prefetch_related('asientos_generados')
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
        url_pdf = f"{settings.MEDIA_URL}tmp/{filename}"
        
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
        
    return render(request, 'contabilidad/f29_detalle.html', {'f29': f29})

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

    return render(request, 'contabilidad/f29_editar.html', {'f29': f29})

@login_required
def f29_centralizar_view(request, pk):
    """Motor Matemático: Transforma un F29 en un Asiento Contable usando una Plantilla."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')
        
    f29 = get_object_or_404(DeclaracionF29, pk=pk, empresa_id=empresa_id)
    plantillas = PlantillaCentralizacion.objects.filter(empresa_id=empresa_id, tipo_origen='f29')
    
    # Fecha por defecto: Último día del mes del F29
    ultimo_dia = calendar.monthrange(f29.ano, f29.mes)[1]
    fecha_sugerida = f"{f29.ano}-{f29.mes:02d}-{ultimo_dia:02d}"
    glosa_sugerida = f"Centralización Impuestos F29 - Período {f29.mes:02d}/{f29.ano}"
    
    context = {'f29': f29, 'plantillas': plantillas, 'fecha_sugerida': fecha_sugerida, 'glosa_sugerida': glosa_sugerida}

    if request.method == 'POST':
        plantilla_id = request.POST.get('plantilla_id')
        fecha = request.POST.get('fecha')
        glosa = request.POST.get('glosa')
        confirmado = request.POST.get('confirmado') == 'true'
        
        # Mantenemos los datos en el formulario para que no se borren al previsualizar
        context['plantilla_id_sel'] = int(plantilla_id) if plantilla_id else None
        context['fecha_sel'] = fecha
        context['glosa_sel'] = glosa
        
        plantilla = get_object_or_404(PlantillaCentralizacion, id=plantilla_id)
        f29_datos = f29.datos_extraidos
        resultados_cuentas = {} # Memoria temporal para variables locales [CTA:X]
        
        total_debe = 0
        total_haber = 0
        lineas_calculadas = []
        
        try:
            for linea in plantilla.lineas.all():
                formula = linea.formula
                
                # 1. Reemplazar Códigos F29 ([520])
                codigos_f29 = re.findall(r'\[(\d+)\]', formula)
                for cod in codigos_f29:
                    valor = f29_datos.get(cod, 0) or 0
                    formula = formula.replace(f'[{cod}]', str(valor))
                    
                # 2. Reemplazar Cuentas Locales calculadas previamente ([CTA:1.1.05])
                codigos_cta = re.findall(r'\[CTA:([0-9\.]+)\]', formula)
                for cod in codigos_cta:
                    valor = resultados_cuentas.get(cod, 0)
                    formula = formula.replace(f'[CTA:{cod}]', str(valor))
                    
                # 3. Evaluación Matemática Segura
                # eval() con __builtins__: None impide la inyección de código malicioso
                resultado_linea = round(eval(formula, {"__builtins__": None}, {}))
                resultados_cuentas[linea.cuenta.codigo] = resultado_linea
                
                debe = resultado_linea if linea.tipo_movimiento == 'debe' else 0
                haber = resultado_linea if linea.tipo_movimiento == 'haber' else 0
                
                total_debe += debe
                total_haber += haber
                
                lineas_calculadas.append({
                    'cuenta_codigo': linea.cuenta.codigo,
                    'cuenta_nombre': linea.cuenta.nombre,
                    'debe': debe,
                    'haber': haber
                })
                
            # REGLA DE ORO: Validar Cuadratura
            if total_debe != total_haber:
                raise ValueError(f"Descuadre detectado. Debe: ${total_debe:,} | Haber: ${total_haber:,}. Revisa las fórmulas de tu plantilla.")
                
            if confirmado:
                # Todo OK: Usuario vio el Pop-up y aceptó. Guardar Asiento.
                asiento = AsientoContable.objects.create(empresa=f29.empresa, fecha=fecha, glosa=glosa, origen_f29=f29)
                for lc in lineas_calculadas:
                    cuenta = CuentaContable.objects.get(empresa=f29.empresa, codigo=lc['cuenta_codigo'])
                    LineaAsiento.objects.create(asiento=asiento, cuenta=cuenta, debe=lc['debe'], haber=lc['haber'])
                    
                messages.success(request, f"¡Centralización Exitosa! Se ha generado el comprobante #{asiento.id} por ${total_debe:,}")
                return redirect('contabilidad:libro_diario') # Redirigimos al Libro Diario para ver la creación
            else:
                # Mostrar Pop-up de Vista Previa
                context['mostrar_modal'] = True
                context['lineas_calculadas'] = lineas_calculadas
                context['total_debe'] = total_debe
                context['total_haber'] = total_haber
                context['plantilla_nombre'] = plantilla.nombre
            
        except ZeroDivisionError:
            messages.error(request, "Error Matemático: Intento de división por cero. Revisa si algún código del F29 está vacío e intenta dividir.")
        except Exception as e:
            messages.error(request, f"Fallo en la Centralización: {str(e)}")
            
    return render(request, 'contabilidad/f29_centralizar.html', context)


# =====================================================================
# VISTAS DE PLAN DE CUENTAS
# =====================================================================

@login_required
def plan_cuentas_lista_view(request):
    """Muestra el plan de cuentas de la empresa seleccionada."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para ver su Plan de Cuentas.")
        return redirect('core:home')

    empresa_actual = get_object_or_404(Empresa, id=empresa_id)
    cuentas = CuentaContable.objects.filter(empresa=empresa_actual)

    return render(request, 'contabilidad/plan_cuentas/lista.html', {'cuentas': cuentas})

@login_required
def plan_cuentas_crear_view(request):
    """Crea una nueva cuenta contable para una empresa específica."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para agregarle una cuenta.")
        return redirect('core:home')
    
    empresa_actual = get_object_or_404(Empresa, id=empresa_id)

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

    return render(request, 'contabilidad/plan_cuentas/form.html', {'form': form})

@login_required
def plan_cuentas_cargar_base_view(request):
    """Muestra una lista de cuentas predeterminadas y permite crearlas en bloque."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        messages.warning(request, "Por favor, selecciona una empresa para cargarle un plan de cuentas.")
        return redirect('core:home')

    empresa_actual = get_object_or_404(Empresa, id=empresa_id)

    if not empresa_actual:
        messages.error(request, "Debe seleccionar una empresa primero.")
        return redirect('contabilidad:plan_cuentas_lista')

    # Cuentas que la empresa ya tiene registradas (para no sugerir duplicados)
    codigos_existentes = list(CuentaContable.objects.filter(empresa=empresa_actual).values_list('codigo', flat=True))

    if request.method == 'POST':
        codigos_seleccionados = request.POST.getlist('cuentas_seleccionadas')
        cuentas_creadas = 0
        
        for cuenta_base in PLAN_CUENTAS_BASE:
            if cuenta_base['codigo'] in codigos_seleccionados and cuenta_base['codigo'] not in codigos_existentes:
                CuentaContable.objects.create(
                    empresa=empresa_actual,
                    codigo=cuenta_base['codigo'],
                    nombre=cuenta_base['nombre'],
                    tipo=cuenta_base['tipo']
                )
                cuentas_creadas += 1
                
        messages.success(request, f'Se han importado {cuentas_creadas} cuentas correctamente al plan de la empresa.')
        return redirect('contabilidad:plan_cuentas_lista')

    # Preparamos las cuentas agrupadas para la vista HTML
    cuentas_agrupadas = {}
    for cuenta in PLAN_CUENTAS_BASE:
        tipo = cuenta['tipo']
        if tipo not in cuentas_agrupadas:
            cuentas_agrupadas[tipo] = []
        # Le añadimos un flag si ya existe
        cuenta['ya_existe'] = cuenta['codigo'] in codigos_existentes
        cuentas_agrupadas[tipo].append(cuenta)

    return render(request, 'contabilidad/plan_cuentas/cargar_base.html', {
        'cuentas_agrupadas': cuentas_agrupadas
    })

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
        
    asientos = AsientoContable.objects.filter(empresa_id=empresa_id).prefetch_related('lineas')
    return render(request, 'contabilidad/libro_diario/lista.html', {'asientos': asientos})

@login_required
def asiento_detalle_view(request, pk):
    """Muestra el detalle de un asiento específico (Comprobante de Partida Doble)."""
    empresa_id = request.session.get('empresa_activa_id')
    if not empresa_id:
        return redirect('core:home')
        
    asiento = get_object_or_404(AsientoContable, pk=pk, empresa_id=empresa_id)
    total_debe = sum(linea.debe for linea in asiento.lineas.all())
    total_haber = sum(linea.haber for linea in asiento.lineas.all())
    
    return render(request, 'contabilidad/libro_diario/detalle.html', {'asiento': asiento, 'total_debe': total_debe, 'total_haber': total_haber})
