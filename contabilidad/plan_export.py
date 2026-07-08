"""Serialización del plan de cuentas con acciones rápidas."""

from .models import AccionRapidaCuenta, LineaAccionRapida


def serializar_plan_empresa(empresa):
    cuentas = empresa.cuentas_contables.prefetch_related(
        'acciones_rapidas__lineas_contrapartida__cuenta',
    ).order_by('codigo')

    payload = {
        'version': 1,
        'empresa': empresa.razon_social,
        'cuentas': [],
    }

    for cuenta in cuentas:
        acciones = []
        for accion in cuenta.acciones_rapidas.all().order_by('orden', 'id'):
            acciones.append({
                'nombre': accion.nombre,
                'tipo': accion.tipo,
                'lado_pendiente': accion.lado_pendiente,
                'orden': accion.orden,
                'activa': accion.activa,
                'contrapartidas': [
                    linea.cuenta.codigo
                    for linea in accion.lineas_contrapartida.all().order_by('orden', 'id')
                ],
            })
        payload['cuentas'].append({
            'codigo': cuenta.codigo,
            'nombre': cuenta.nombre,
            'tipo': cuenta.tipo,
            'subtipo_operacion': cuenta.subtipo_operacion or 'general',
            'acciones_rapidas': acciones,
        })

    return payload


def importar_acciones_plan(empresa, data):
    """
    Importa acciones rápidas desde JSON exportado.
    Las cuentas deben existir en la empresa destino (match por código).
    """
    cuentas_data = data.get('cuentas', [])
    importadas = 0
    omitidas = 0

    codigo_a_cuenta = {
        c.codigo: c
        for c in empresa.cuentas_contables.all()
    }

    for item in cuentas_data:
        cuenta = codigo_a_cuenta.get(item.get('codigo'))
        if not cuenta:
            omitidas += 1
            continue

        for accion_data in item.get('acciones_rapidas', []):
            accion = AccionRapidaCuenta.objects.create(
                cuenta=cuenta,
                nombre=accion_data.get('nombre', 'Acción'),
                tipo=accion_data.get('tipo', 'pago'),
                lado_pendiente=accion_data.get('lado_pendiente', 'haber'),
                orden=accion_data.get('orden', 0),
                activa=accion_data.get('activa', True),
            )
            for orden, codigo_contra in enumerate(accion_data.get('contrapartidas', [])):
                cuenta_contra = codigo_a_cuenta.get(codigo_contra)
                if cuenta_contra:
                    LineaAccionRapida.objects.create(
                        accion=accion,
                        cuenta=cuenta_contra,
                        orden=orden,
                    )
            importadas += 1

    return importadas, omitidas
