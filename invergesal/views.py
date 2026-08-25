import base64
import io
import json
from datetime import datetime
from pathlib import Path

import pytz
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
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
from invergesal.services.parametros_viaje import guardar_parametros_viaje
from invergesal.services.simulacion_escalas import construir_simulacion
from invergesal.services.conexiones_saldos import (
    guardar_urls,
    serializar_conexiones,
)
from invergesal.services.parametros_gastos import (
    crear_parametro,
    eliminar_parametro,
    parse_anio,
    parse_semana,
    parse_valor,
    serializar_parametros,
    tarifas_para_semana,
)
from invergesal.services.saldos_ecuador import (
    agrupar_por_di,
    anios_disponibles,
    cargar_saldos_ecuador,
    cargar_todas_las_marcas,
    construir_liquidacion,
    codigo_liquidacion,
    clear_saldos_cache,
    get_saldos_cache_info,
    normalizar_pestana,
    pestanas_saldos,
    semanas_disponibles,
    _tramos_extra_limpios,
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


def _anio_saldos(request, anios, anio_default):
    raw = (request.GET.get('anio') or '').strip()
    if not raw:
        return anio_default
    try:
        anio = int(raw)
    except (TypeError, ValueError):
        return anio_default
    if anios and anio not in anios:
        return anio_default
    return anio


def _fuente_saldos(request):
    return normalizar_pestana(request.GET.get('fuente'))


def _contexto_saldos_vacio(fuente, message, extra=None):
    ctx = {
        'grupos': [],
        'anios': [],
        'anio_seleccionado': None,
        'semana_seleccionada': None,
        'semanas': [],
        'fuente': fuente,
        'fuentes': pestanas_saldos(),
        'cache_info': {},
        'totales': {'dis': 0, 'contenedores': 0, 'cajas': 0, 'total': 0},
        'liquidacion': None,
        'parametros_gastos': None,
        'conexiones_saldos': serializar_conexiones(),
        'error_carga': message,
    }
    if extra:
        ctx.update(extra)
    return ctx


@invergesal_required
@require_http_methods(['GET'])
def saldos_ecuador(request):
    fuente = _fuente_saldos(request)
    if fuente == 'liquidacion':
        return _saldos_liquidacion(request)

    success, message, filas = cargar_saldos_ecuador(fuente)
    if not success:
        return render(
            request,
            'invergesal/saldos_ecuador.html',
            _contexto_saldos_vacio(fuente, message, {'cache_info': get_saldos_cache_info(fuente)}),
        )
    if message:
        messages.warning(request, message)

    anios = anios_disponibles(filas)
    anio_default = anios[0] if anios else datetime.now().year
    anio = _anio_saldos(request, anios, anio_default)
    grupos = agrupar_por_di(filas, anio)
    totales = {
        'dis': len(grupos),
        'contenedores': sum(g['num_contenedores'] for g in grupos),
        'cajas': sum(g['cajas'] for g in grupos),
        'total': round(sum(g['total'] for g in grupos), 2),
    }
    return render(request, 'invergesal/saldos_ecuador.html', {
        'grupos': grupos,
        'anios': anios,
        'anio_seleccionado': anio,
        'semana_seleccionada': None,
        'semanas': [],
        'fuente': fuente,
        'fuentes': pestanas_saldos(),
        'cache_info': get_saldos_cache_info(fuente),
        'totales': totales,
        'liquidacion': None,
        'parametros_gastos': None,
        'conexiones_saldos': serializar_conexiones(),
        'error_carga': '',
    })


def _saldos_liquidacion(request):
    success, message, datos = cargar_todas_las_marcas()
    anios = sorted({
        anio
        for filas in datos.values()
        for anio in anios_disponibles(filas)
    }, reverse=True)
    anio_default = anios[0] if anios else datetime.now().year
    anio = _anio_saldos(request, anios, anio_default)
    semanas_nros = sorted({
        sem
        for filas in datos.values()
        for sem in semanas_disponibles(filas, anio)
    }, reverse=True)
    semana_default = semanas_nros[0] if semanas_nros else 1
    raw_sem = (request.GET.get('semana') or '').strip()
    try:
        semana = int(raw_sem) if raw_sem else semana_default
    except (TypeError, ValueError):
        semana = semana_default
    if semanas_nros and semana not in semanas_nros:
        semana = semana_default
    semanas = [{'numero': s, 'codigo': codigo_liquidacion(anio, s)} for s in semanas_nros]

    if not success and not any(datos.values()):
        return render(
            request,
            'invergesal/saldos_ecuador.html',
            _contexto_saldos_vacio('liquidacion', message, {
                'anios': anios,
                'anio_seleccionado': anio,
                'semanas': semanas,
                'semana_seleccionada': semana,
                'parametros_gastos': serializar_parametros(anio, semana),
                'conexiones_saldos': serializar_conexiones(),
            }),
        )
    if message:
        messages.warning(request, message)

    extras = _extras_tc_sesion(request, codigo_liquidacion(anio, semana))
    tarifas = tarifas_para_semana(anio, semana)
    liquidacion = construir_liquidacion(datos, anio, semana, extras, tarifas)
    infos = [get_saldos_cache_info(clave) for clave in ('banagreen', 'corproban')]
    cache_info = next((info for info in infos if info.get('modifiedTimeLocal')), {})
    return render(request, 'invergesal/saldos_ecuador.html', {
        'grupos': [],
        'anios': anios,
        'anio_seleccionado': anio,
        'semana_seleccionada': semana,
        'semanas': semanas,
        'fuente': 'liquidacion',
        'fuentes': pestanas_saldos(),
        'cache_info': cache_info,
        'totales': {'dis': 0, 'contenedores': 0, 'cajas': 0, 'total': 0},
        'liquidacion': liquidacion,
        'parametros_gastos': serializar_parametros(anio, semana),
        'conexiones_saldos': serializar_conexiones(),
        'error_carga': '',
    })


SESSION_TC_EXTRA = 'saldos_ecuador_tc_extra'


def _extras_tc_sesion(request, codigo):
    return list((request.session.get(SESSION_TC_EXTRA) or {}).get(str(codigo), []))


def _set_extras_tc_sesion(request, codigo, extras):
    data = dict(request.session.get(SESSION_TC_EXTRA) or {})
    codigo = str(codigo)
    if extras:
        data[codigo] = extras
    else:
        data.pop(codigo, None)
    request.session[SESSION_TC_EXTRA] = data
    request.session.modified = True


def _limpiar_extras_tc_sesion(request):
    request.session.pop(SESSION_TC_EXTRA, None)


@invergesal_required
@require_POST
def guardar_tc_extra_liquidacion(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos'}, status=400)
    try:
        anio = int(payload.get('anio'))
        semana = int(payload.get('semana'))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Semana inválida'}, status=400)
    extras = payload.get('extras') or []
    if not isinstance(extras, list):
        return JsonResponse({'ok': False, 'error': 'Ajustes inválidos'}, status=400)
    limpios = _tramos_extra_limpios(extras[:40])
    _set_extras_tc_sesion(request, codigo_liquidacion(anio, semana), limpios)
    return JsonResponse({'ok': True, 'extras': limpios})


@invergesal_required
@require_POST
def guardar_parametro_gasto(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos'}, status=400)
    accion = (payload.get('accion') or 'crear').strip().lower()
    if accion == 'eliminar':
        ok, mensaje = eliminar_parametro(payload.get('id'))
        return JsonResponse({'ok': ok, 'error': None if ok else mensaje, 'mensaje': mensaje})
    ok, mensaje, _obj = crear_parametro(
        (payload.get('concepto') or '').strip(),
        parse_anio(payload.get('anio_desde')),
        parse_semana(payload.get('semana_desde')),
        parse_anio(payload.get('anio_hasta')),
        parse_semana(payload.get('semana_hasta')),
        parse_valor(payload.get('valor')),
    )
    status = 200 if ok else 400
    return JsonResponse({'ok': ok, 'error': None if ok else mensaje, 'mensaje': mensaje}, status=status)


@invergesal_required
@require_POST
def guardar_conexiones_saldos(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos'}, status=400)
    ok, mensaje = guardar_urls(payload.get('banagreen'), payload.get('corproban'))
    if not ok:
        return JsonResponse({'ok': False, 'error': mensaje}, status=400)
    clear_saldos_cache()
    success, carga_msg, _datos = cargar_todas_las_marcas(force_refresh=True)
    if success:
        messages.success(request, mensaje + ' ' + (carga_msg or 'Se actualizaron BANAGREEN y CORPROBAN.'))
    else:
        messages.warning(request, f'{mensaje} No se pudo leer el CSV nuevo: {carga_msg}')
    return JsonResponse({'ok': True, 'mensaje': mensaje, 'carga_ok': success})


@invergesal_required
def actualizar_saldos_ecuador(request):
    _limpiar_extras_tc_sesion(request)
    fuente = _fuente_saldos(request)
    anio = (request.GET.get('anio') or '').strip()
    semana = (request.GET.get('semana') or '').strip()
    if fuente == 'liquidacion':
        success, message, _datos = cargar_todas_las_marcas(force_refresh=True)
    else:
        success, message, _filas = cargar_saldos_ecuador(fuente, force_refresh=True)
    if success:
        messages.success(request, message or 'Saldos Ecuador actualizado.')
    else:
        messages.error(request, message)
    redirect_url = reverse('invergesal:saldos_ecuador')
    params = [f'fuente={fuente}']
    if anio.isdigit():
        params.append(f'anio={anio}')
    if fuente == 'liquidacion' and semana.isdigit():
        params.append(f'semana={semana}')
    return redirect(f'{redirect_url}?{"&".join(params)}')


@invergesal_required
def calendario_escalas(request):
    success, message = cargar_datos_en_cache()
    if not success:
        messages.error(request, message)
    df = get_cached_df() if success else None
    mes_txt = (request.GET.get('mes') or '').strip()
    return render(request, 'invergesal/calendario_escalas.html', {
        'simulacion': construir_simulacion(df, mes_txt=mes_txt),
        'cache_info': get_cache_info() if success else {},
    })


def _url_escalas(**extra):
    params = {k: v for k, v in extra.items() if v}
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    url = reverse('invergesal:calendario_escalas')
    return f'{url}?{query}' if query else url


@invergesal_required
@require_POST
def guardar_dias_viaje_view(request):
    ok, mensaje = guardar_parametros_viaje(
        request.POST.get('dias_san_antonio'),
        request.POST.get('dias_valparaiso'),
        request.POST.getlist('buque_nombre'),
        request.POST.getlist('buque_dias'),
        request.POST.getlist('color_hasta'),
        request.POST.getlist('color_hex'),
    )
    if ok:
        messages.success(request, mensaje)
    else:
        messages.error(request, mensaje)
    return redirect(_url_escalas(mes=(request.POST.get('mes') or '').strip()))
