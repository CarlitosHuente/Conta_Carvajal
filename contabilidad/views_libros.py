import calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Empresa
from .cobros_pagos import crear_asiento_manual, registrar_pago_o_cobro, SaldarMovimientosError
from .libros import balance_ocho_columnas, cuentas_medio_pago, movimientos_cuenta, resumen_cuentas_empresa
from .models import AsientoContable, CuentaContable, LineaAsiento
from .views import _get_empresa_plan


def _periodo_desde_request(request):
    hoy = date.today()
    mes = request.GET.get('mes') or request.POST.get('mes') or hoy.month
    ano = request.GET.get('ano') or request.POST.get('ano') or hoy.year
    try:
        mes, ano = int(mes), int(ano)
    except (TypeError, ValueError):
        mes, ano = hoy.month, hoy.year
    ultimo = calendar.monthrange(ano, mes)[1]
    return {
        'mes': mes,
        'ano': ano,
        'fecha_desde': date(ano, mes, 1),
        'fecha_hasta': date(ano, mes, ultimo),
    }


@login_required
def libro_mayor_view(request):
    empresa = _get_empresa_plan(request)
    if not empresa:
        messages.warning(request, 'Selecciona una empresa para ver el Libro Mayor.')
        return redirect('core:home')

    periodo = _periodo_desde_request(request)
    cuentas = resumen_cuentas_empresa(empresa, periodo['fecha_desde'], periodo['fecha_hasta'])

    return render(request, 'contabilidad/libro_mayor/lista.html', {
        'cuentas': cuentas,
        'periodo': periodo,
    })


@login_required
def libro_mayor_cuenta_view(request, pk):
    empresa = _get_empresa_plan(request)
    if not empresa:
        return redirect('core:home')

    cuenta = get_object_or_404(CuentaContable, pk=pk, empresa=empresa)
    periodo = _periodo_desde_request(request)
    movimientos, saldo_final = movimientos_cuenta(cuenta, periodo['fecha_desde'], periodo['fecha_hasta'])

    subtipo = cuenta.subtipo_detectado()
    puede_saldar = cuenta.permite_saldar_operaciones()
    cuentas_pago = cuentas_medio_pago(empresa) if puede_saldar else []

    if request.method == 'POST' and puede_saldar:
        linea_ids = request.POST.getlist('linea_ids')
        cuenta_medio_id = request.POST.get('cuenta_medio_id')
        fecha_pago = request.POST.get('fecha_pago') or periodo['fecha_hasta']
        glosa = request.POST.get('glosa', '').strip()

        lineas = list(
            LineaAsiento.objects.filter(
                pk__in=linea_ids,
                cuenta=cuenta,
            ).prefetch_related('aplicaciones_salida')
        )

        try:
            asiento, monto, tipo = registrar_pago_o_cobro(
                empresa, cuenta, lineas, cuenta_medio_id, fecha_pago, glosa or None,
            )
            accion = 'Pago' if tipo == 'pago' else 'Cobro'
            messages.success(request, f'{accion} registrado: asiento #{asiento.id} por ${monto:,}.')
            return redirect('contabilidad:asiento_detalle', pk=asiento.pk)
        except SaldarMovimientosError as e:
            messages.error(request, str(e))

    return render(request, 'contabilidad/libro_mayor/cuenta.html', {
        'cuenta': cuenta,
        'movimientos': movimientos,
        'saldo_final': saldo_final,
        'periodo': periodo,
        'puede_saldar': puede_saldar,
        'subtipo': subtipo,
        'cuentas_pago': cuentas_pago,
        'es_proveedor': subtipo == 'proveedores',
        'es_cliente': subtipo == 'clientes',
    })


@login_required
def balance_view(request):
    empresa = _get_empresa_plan(request)
    if not empresa:
        messages.warning(request, 'Selecciona una empresa para ver el Balance.')
        return redirect('core:home')

    periodo = _periodo_desde_request(request)
    filas, totales = balance_ocho_columnas(empresa, periodo['fecha_desde'], periodo['fecha_hasta'])

    grupos = {}
    orden = ['activo', 'pasivo', 'patrimonio', 'ganancia', 'perdida']
    labels = dict(CuentaContable.TIPO_CHOICES)
    for fila in filas:
        t = fila['cuenta'].tipo
        grupos.setdefault(t, []).append(fila)

    balance_grupos = [(labels.get(t, t), grupos[t]) for t in orden if t in grupos]

    return render(request, 'contabilidad/balance/lista.html', {
        'balance_grupos': balance_grupos,
        'totales': totales,
        'periodo': periodo,
        'cuadra': totales['saldo_deudor'] == totales['saldo_acreedor'],
    })


@login_required
def asiento_crear_view(request):
    empresa = _get_empresa_plan(request)
    if not empresa:
        messages.warning(request, 'Selecciona una empresa para crear comprobantes.')
        return redirect('core:home')

    cuentas = CuentaContable.objects.filter(empresa=empresa)
    hoy = date.today().isoformat()

    if request.method == 'POST':
        fecha = request.POST.get('fecha')
        glosa = request.POST.get('glosa', '').strip()
        cuenta_ids = request.POST.getlist('cuenta_id[]')
        debes = request.POST.getlist('debe[]')
        haberes = request.POST.getlist('haber[]')

        lineas_data = []
        for c_id, d, h in zip(cuenta_ids, debes, haberes):
            if not c_id:
                continue
            lineas_data.append({
                'cuenta_id': c_id,
                'debe': d or 0,
                'haber': h or 0,
            })

        try:
            asiento = crear_asiento_manual(empresa, fecha, glosa, lineas_data)
            messages.success(request, f'Comprobante #{asiento.id} creado correctamente.')
            return redirect('contabilidad:asiento_detalle', pk=asiento.pk)
        except SaldarMovimientosError as e:
            messages.error(request, str(e))

    return render(request, 'contabilidad/libro_diario/crear.html', {
        'cuentas': cuentas,
        'fecha_hoy': hoy,
    })
