"""Serialización del plan de cuentas con acciones rápidas."""

from .models import AccionRapida, LineaAccionRapida, CuentaAccionRapida


def serializar_plan_empresa(empresa):
    cuentas = empresa.cuentas_contables.order_by('codigo')
    acciones = AccionRapida.objects.filter(empresa=empresa).prefetch_related(
        'lineas_contrapartida__cuenta',
        'asignaciones_cuentas__cuenta',
    ).order_by('nombre')

    payload = {
        'version': 2,
        'empresa': empresa.razon_social,
        'acciones_rapidas': [],
        'cuentas': [],
    }

    for accion in acciones:
        payload['acciones_rapidas'].append({
            'nombre': accion.nombre,
            'tipo': accion.tipo,
            'lado_pendiente': accion.lado_pendiente,
            'activa': accion.activa,
            'contrapartidas': [
                linea.cuenta.codigo
                for linea in accion.lineas_contrapartida.all().order_by('orden', 'id')
            ],
            'cuentas_asignadas': [
                a.cuenta.codigo
                for a in accion.asignaciones_cuentas.all().order_by('orden', 'id')
            ],
        })

    for cuenta in cuentas:
        payload['cuentas'].append({
            'codigo': cuenta.codigo,
            'nombre': cuenta.nombre,
            'tipo': cuenta.tipo,
            'subtipo_operacion': cuenta.subtipo_operacion or 'general',
            'requiere_auxiliar': cuenta.requiere_auxiliar,
        })

    return payload


def importar_acciones_plan(empresa, data):
    codigo_a_cuenta = {c.codigo: c for c in empresa.cuentas_contables.all()}
    importadas = 0

    acciones_data = data.get('acciones_rapidas')
    if acciones_data is None:
        acciones_data = _acciones_desde_v1(data, codigo_a_cuenta)

    for accion_data in acciones_data:
        accion, _ = AccionRapida.objects.get_or_create(
            empresa=empresa,
            nombre=accion_data.get('nombre', 'Acción'),
            defaults={
                'tipo': accion_data.get('tipo', 'pago'),
                'lado_pendiente': accion_data.get('lado_pendiente', 'haber'),
                'activa': accion_data.get('activa', True),
            },
        )
        accion.lineas_contrapartida.all().delete()
        for orden, codigo_contra in enumerate(accion_data.get('contrapartidas', [])):
            cuenta_contra = codigo_a_cuenta.get(codigo_contra)
            if cuenta_contra:
                LineaAccionRapida.objects.create(
                    accion=accion, cuenta=cuenta_contra, orden=orden,
                )

        for orden, codigo_cuenta in enumerate(accion_data.get('cuentas_asignadas', [])):
            cuenta = codigo_a_cuenta.get(codigo_cuenta)
            if cuenta:
                CuentaAccionRapida.objects.get_or_create(
                    cuenta=cuenta, accion=accion, defaults={'orden': orden},
                )
        importadas += 1

    return importadas, 0


def _acciones_desde_v1(data, codigo_a_cuenta):
    """Compatibilidad export v1: acciones embebidas por cuenta."""
    agrupadas = {}
    for item in data.get('cuentas', []):
        codigo_cuenta = item.get('codigo')
        for accion_data in item.get('acciones_rapidas', []):
            key = (
                accion_data.get('nombre'),
                accion_data.get('tipo'),
                accion_data.get('lado_pendiente'),
                tuple(accion_data.get('contrapartidas', [])),
            )
            if key not in agrupadas:
                agrupadas[key] = {**accion_data, 'cuentas_asignadas': []}
            if codigo_cuenta:
                agrupadas[key]['cuentas_asignadas'].append(codigo_cuenta)
    return list(agrupadas.values())
