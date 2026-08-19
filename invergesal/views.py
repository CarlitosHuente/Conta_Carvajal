import base64
import io
import json
from datetime import datetime
from pathlib import Path

import pytz
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods, require_POST

from invergesal.permissions import invergesal_required
from invergesal.services import drive
from invergesal.services.data_processor import CONSOLIDATED_FILENAME, generar_reporte_consolidado
from invergesal.services.reports import (
    aplicar_filtros,
    cargar_datos_en_cache,
    clear_cache,
    construir_tabla,
    filtros_desde_request,
    get_calidad,
    get_cache_info,
    get_cached_df,
    get_folder_id,
    merge_calidad,
    obtener_detalle_cajas_por_puerto,
)


def _logo_data_uri():
    logo_path = Path(__file__).resolve().parent / 'static' / 'invergesal' / 'img' / 'logo.png'
    if not logo_path.exists():
        return ''
    b64 = base64.b64encode(logo_path.read_bytes()).decode('ascii')
    return f'data:image/png;base64,{b64}'


def _excel_response(buffer, filename):
    """HttpResponse en memoria: FileResponse+BytesIO revienta Passenger (Internal Error)."""
    if hasattr(buffer, 'seek'):
        buffer.seek(0)
    payload = buffer.getvalue() if hasattr(buffer, 'getvalue') else buffer
    response = HttpResponse(
        payload,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _render_pdf(html, base_url=None):
    try:
        from weasyprint import HTML
        return HTML(string=html, base_url=base_url).write_pdf(), 'application/pdf', 'attachment; filename=reporte_carga.pdf'
    except Exception:
        try:
            from xhtml2pdf import pisa
            output = io.BytesIO()
            pisa.CreatePDF(src=html, dest=output, encoding='utf-8')
            output.seek(0)
            return output.read(), 'application/pdf', 'attachment; filename=reporte_carga.pdf'
        except Exception:
            return html.encode('utf-8'), 'text/html; charset=utf-8', 'inline; filename=reporte_carga.html'


def _opciones_filtros(df):
    return {
        'all_semanas': sorted(df['SEMANA'].unique()),
        'all_puertos': sorted(df['PUERTO_DESCARGA'].dropna().unique()),
        'all_navieras': sorted(df['NAVIERA'].dropna().unique()),
        'all_consignatarios': sorted(df['CONSIGNATARIO'].dropna().unique()),
    }


@invergesal_required
@require_http_methods(['GET', 'POST'])
def estadisticas(request):
    success, message = cargar_datos_en_cache()
    if not success:
        messages.error(request, message)
        return render(request, 'invergesal/estadisticas_error.html', {
            'message': message,
            'calidad': get_calidad(),
        })

    df = get_cached_df()
    opciones = _opciones_filtros(df)
    defaults = {
        'semanas': opciones['all_semanas'][-10:],
        'puertos': ['SAN ANTONIO', 'VALPARAISO'],
        'naviera': 'TODAS',
        'consignatario': '',
    }
    filtros = filtros_desde_request(request, defaults)
    df_filtrado = aplicar_filtros(
        df, filtros['semanas'], filtros['puertos'], filtros['naviera'], filtros['consignatario']
    )
    tabla_final = construir_tabla(df_filtrado, filtros['semanas'])

    return render(request, 'invergesal/estadisticas.html', {
        'tabla_final': tabla_final,
        'semanas_columnas': filtros['semanas'],
        'all_semanas': opciones['all_semanas'],
        'all_puertos': opciones['all_puertos'],
        'all_navieras': opciones['all_navieras'],
        'all_consignatarios': opciones['all_consignatarios'],
        'semanas_seleccionadas': filtros['semanas'],
        'puertos_seleccionados': filtros['puertos'],
        'naviera_seleccionada': filtros['naviera'],
        'consignatario_busqueda': filtros['consignatario'],
        'cache_info': get_cache_info(),
        'calidad': get_calidad(),
    })


@invergesal_required
def generar_reporte(request):
    folder_id = get_folder_id()
    if not folder_id:
        messages.error(request, 'Error: El ID de la carpeta de Google Drive no está configurado.')
        return redirect('invergesal:estadisticas')

    messages.info(request, 'Iniciando el procesamiento. Esto puede tardar y refrescará el caché.')
    success, message, calidad = generar_reporte_consolidado(folder_id)
    if success:
        clear_cache()
        messages.success(request, message)
        cargar_datos_en_cache(force_refresh=True)
        merge_calidad(get_calidad(), calidad)
    else:
        messages.error(request, message)
        merge_calidad(get_calidad(), calidad)
    return redirect('invergesal:estadisticas')


@invergesal_required
@require_POST
def detalle_puerto(request):
    try:
        body = json.loads(request.body.decode() or '{}')
        puerto = (body.get('puerto') or '').strip()
    except Exception:
        return JsonResponse({'error': 'Solicitud inválida', 'filas': []}, status=400)
    if not puerto:
        return JsonResponse({'error': 'Indica un puerto', 'filas': []}, status=400)
    try:
        filas = obtener_detalle_cajas_por_puerto(puerto)
    except Exception as exc:
        return JsonResponse({'error': str(exc), 'filas': []}, status=500)
    return JsonResponse({'puerto': puerto, 'filas': filas})


@invergesal_required
def descargar_reporte(request):
    folder_id = get_folder_id()
    file_info = drive.find_file_by_name(CONSOLIDATED_FILENAME, folder_id)
    if not file_info:
        messages.warning(request, 'El reporte consolidado no existe. Por favor, genérelo primero.')
        return redirect('invergesal:estadisticas')

    file_bytes = drive.download_file(file_info['id'])
    if not file_bytes:
        messages.error(request, 'No se pudo descargar el archivo desde Google Drive.')
        return redirect('invergesal:estadisticas')

    return _excel_response(file_bytes, CONSOLIDATED_FILENAME)


@invergesal_required
@require_POST
def descargar_reporte_pdf(request):
    success, message = cargar_datos_en_cache()
    if not success:
        messages.error(request, message)
        return redirect('invergesal:estadisticas')

    df = get_cached_df()
    filtros = filtros_desde_request(request)
    df_filtrado = aplicar_filtros(
        df, filtros['semanas'], filtros['puertos'], filtros['naviera'], filtros['consignatario']
    )
    tabla_final = construir_tabla(df_filtrado, filtros['semanas'])
    html = render_to_string('invergesal/reporte_pdf.html', {
        'tabla_final': tabla_final,
        'semanas_columnas': filtros['semanas'],
        'cache_info': get_cache_info(),
        'logo_data_uri': _logo_data_uri(),
        'fecha_generacion': datetime.now(pytz.timezone('America/Santiago')).strftime('%d/%m/%Y %H:%M:%S'),
    })
    payload, content_type, disposition = _render_pdf(html)
    response = HttpResponse(payload, content_type=content_type)
    response['Content-Disposition'] = disposition
    return response


@invergesal_required
@require_POST
def descargar_filtrado(request):
    success, message = cargar_datos_en_cache()
    if not success:
        messages.error(request, message)
        return redirect('invergesal:estadisticas')

    df = get_cached_df()
    filtros = filtros_desde_request(request)
    df_filtrado = aplicar_filtros(
        df, filtros['semanas'], filtros['puertos'], filtros['naviera'], filtros['consignatario']
    )
    output_buffer = io.BytesIO()
    df_filtrado.to_excel(output_buffer, index=False, sheet_name='Datos Filtrados')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return _excel_response(output_buffer, f'Reporte_Filtrado_{timestamp}.xlsx')
