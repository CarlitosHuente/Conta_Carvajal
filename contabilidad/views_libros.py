import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .cobros_pagos import crear_asiento_manual, registrar_pago_o_cobro, SaldarMovimientosError
from .libros import (
    balance_ocho_columnas,
    config_saldar_cuenta,
    cuentas_contrapartida_disponibles,
    cuentas_medio_pago,
    movimientos_cuenta,
    resumen_cuentas_empresa,
)
from .models import AccionRapidaCuenta, CuentaContable, LineaAsiento
from .views import _get_empresa_plan


def _fecha_corte_desde_request(request):
    hoy = date.today()
    raw = request.GET.get('fecha_corte') or request.POST.get('fecha_corte') or hoy.isoformat()
    try:
        partes = str(raw).split('-')
        fecha = date(int(partes[0]), int(partes[1]), int(partes[2]))
    except (ValueError, IndexError):
        fecha = hoy
    return {'fecha_corte': fecha}


def _acciones_json(cuenta):
    acciones = []
    for accion in cuenta.acciones_rapidas.filter(activa=True).prefetch_related('lineas_contrapartida__cuenta'):
        acciones.append({
            'id': accion.id,
            'nombre': accion.nombre,
            'tipo': accion.tipo,
            'cuentas': [
                {
                    'id': l.cuenta_id,
                    'label': f'{l.cuenta.codigo} — {l.cuenta.nombre}',
                }
                for l in accion.lineas_contrapartida.all()
            ],
        })
    return acciones


@login_required
def libro_mayor_view(request):
    empresa = _get_empresa_plan(request)
    if not empresa:
        messages.warning(request, 'Selecciona una empresa para ver el Libro Mayor.')
        return redirect('core:home')

    corte = _fecha_corte_desde_request(request)
    cuentas = resumen_cuentas_empresa(empresa, corte['fecha_corte'])

    return render(request, 'contabilidad/libro_mayor/lista.html', {
        'cuentas': cuentas,
        'corte': corte,
    })


@login_required
def libro_mayor_cuenta_view(request, pk):
    empresa = _get_empresa_plan(request)
    if not empresa:
        return redirect('core:home')

    cuenta = get_object_or_404(
        CuentaContable.objects.prefetch_related('acciones_rapidas__lineas_contrapartida__cuenta'),
        pk=pk,
        empresa=empresa,
    )
    corte = _fecha_corte_desde_request(request)
    movimientos, saldo_final = movimientos_cuenta(cuenta, corte['fecha_corte'])

    config = config_saldar_cuenta(cuenta)
    puede_saldar = bool(config)
    tipo_op = config['tipo'] if config else None
    cuentas_pago = cuentas_contrapartida_disponibles(empresa) if puede_saldar else []
    cuentas_sugeridas = cuentas_medio_pago(empresa) if puede_saldar else []

    if request.method == 'POST' and puede_saldar:
        linea_ids = request.POST.getlist('linea_ids')
        fecha_pago = request.POST.get('fecha_pago') or corte['fecha_corte']
        glosa = request.POST.get('glosa', '').strip()
        cuenta_medio_ids = request.POST.getlist('cuenta_medio_id[]')
        montos_medio = request.POST.getlist('monto_medio[]')

        medios = []
        for c_id, monto in zip(cuenta_medio_ids, montos_medio):
            if not c_id:
                continue
            medios.append({'cuenta_id': c_id, 'monto': monto})

        lineas = list(
            LineaAsiento.objects.filter(
                pk__in=linea_ids,
                cuenta=cuenta,
            ).prefetch_related('aplicaciones_salida')
        )

        try:
            asiento, monto, tipo = registrar_pago_o_cobro(
                empresa, cuenta, lineas, medios, fecha_pago, glosa or None,
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
        'corte': corte,
        'puede_saldar': puede_saldar,
        'tipo_op': tipo_op,
        'cuentas_pago': cuentas_pago,
        'cuentas_sugeridas': cuentas_sugeridas,
        'acciones_json': json.dumps(_acciones_json(cuenta)),
        'sugeridas_json': json.dumps([
            {'id': c.id, 'label': f'{c.codigo} — {c.nombre}'} for c in cuentas_sugeridas
        ]),
        'es_pago': tipo_op == 'pago',
        'es_cobro': tipo_op == 'cobro',
    })


@login_required
def balance_view(request):
    empresa = _get_empresa_plan(request)
    if not empresa:
        messages.warning(request, 'Selecciona una empresa para ver el Balance.')
        return redirect('core:home')

    corte = _fecha_corte_desde_request(request)
    filas, totales = balance_ocho_columnas(empresa, corte['fecha_corte'])

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
        'corte': corte,
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
