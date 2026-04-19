import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.conf import settings

from .extractor import extraer_datos_f29
from .models import CodigoF29, DeclaracionF29
from core.models import Empresa

@login_required
def f29_lista_view(request):
    """Muestra el historial de F29 cargados según el rol del usuario."""
    if request.user.perfil.rol == 'admin':
        declaraciones = DeclaracionF29.objects.all().order_by('-ano', '-mes')
    else:
        declaraciones = DeclaracionF29.objects.filter(empresa_id=request.user.perfil.empresa_id).order_by('-ano', '-mes')
        
    return render(request, 'contabilidad/f29_lista.html', {'declaraciones': declaraciones})

@login_required
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
