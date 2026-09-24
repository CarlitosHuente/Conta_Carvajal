"""Borrador del finiquito: la estructura es fija; el texto y las variables se editan."""

from django.utils.html import escape

from .models import PlantillaDocumento

CODIGO = 'finiquito'

VARIABLES = (
    ('{nombre}', 'Nombre del trabajador'),
    ('{rut_trabajador}', 'RUT del trabajador'),
    ('{cargo}', 'Cargo'),
    ('{fecha_inicio}', 'Fecha de inicio'),
    ('{fecha_termino}', 'Fecha de término'),
    ('{causal}', 'Causal'),
    ('{empresa}', 'Razón social'),
    ('{rut_empresa}', 'RUT del empleador'),
    ('{total}', 'Total del finiquito'),
    ('{lugar}', 'Lugar'),
    ('{fecha_documento}', 'Fecha del documento'),
)

BLOQUES = (
    ('titulo', 'Título', 'FINIQUITO DE CONTRATO DE TRABAJO'),
    ('intro', 'Comparecencia', (
        'En {lugar}, a {fecha_documento}, entre {empresa}, RUT {rut_empresa}, '
        'en adelante el Empleador, y {nombre}, RUT {rut_trabajador}, '
        'en adelante el Trabajador, se acuerda el término de la relación laboral.'
    )),
    ('servicios', 'Servicios prestados', (
        'El Trabajador se desempeñó en el cargo de {cargo}, desde el {fecha_inicio} '
        'hasta el {fecha_termino}, por la causal {causal}.'
    )),
    ('cierre', 'Cierre y pago', (
        'El Empleador paga la suma de {total}, según el detalle que sigue, '
        'y el Trabajador declara recibirlo a su entera satisfacción, '
        'sin cargos ni cobros posteriores que formular.'
    )),
    ('lugar', 'Lugar de suscripción', 'Santiago'),
)


def textos_por_defecto():
    return {codigo: texto for codigo, _etiqueta, texto in BLOQUES}


def obtener_textos():
    textos = textos_por_defecto()
    plantilla = PlantillaDocumento.objects.filter(codigo=CODIGO).first()
    if plantilla and isinstance(plantilla.bloques, dict):
        for codigo, _etiqueta, _texto in BLOQUES:
            valor = plantilla.bloques.get(codigo)
            if isinstance(valor, str) and valor.strip():
                textos[codigo] = valor
    return textos


def guardar_textos(datos):
    textos = textos_por_defecto()
    for codigo, _etiqueta, _texto in BLOQUES:
        valor = (datos.get(codigo) or '').strip()
        if valor:
            textos[codigo] = valor
    PlantillaDocumento.objects.update_or_create(
        codigo=CODIGO,
        defaults={'nombre': 'Finiquito', 'bloques': textos},
    )
    return textos


def aplicar(texto, variables):
    resultado = texto or ''
    for clave, valor in variables.items():
        resultado = resultado.replace('{' + clave + '}', str(valor or '—'))
    return resultado


def documento_desde_lineas(contrato, fecha_termino, motivo_label, lineas, fecha_documento=None):
    """Arma el texto del borrador sin guardar el finiquito."""
    from datetime import date as date_cls

    trabajador = contrato.trabajador
    empresa = trabajador.empresa
    textos = obtener_textos()
    if hasattr(fecha_termino, 'strftime'):
        fecha_fin = fecha_termino
    else:
        fecha_fin = date_cls.today()
    total = 0
    for linea in lineas:
        texto_monto = ''.join(ch for ch in str(linea.get('monto') or '') if ch.isdigit())
        total += int(texto_monto) if texto_monto else 0
    total_txt = f'${total:,}'.replace(',', '.')
    variables = {
        'nombre': trabajador.nombre_completo,
        'rut_trabajador': trabajador.rut,
        'cargo': contrato.cargo or '—',
        'fecha_inicio': contrato.fecha_inicio.strftime('%d/%m/%Y'),
        'fecha_termino': fecha_fin.strftime('%d/%m/%Y'),
        'causal': motivo_label,
        'empresa': empresa.razon_social,
        'rut_empresa': empresa.rut,
        'total': total_txt,
        'lugar': textos['lugar'],
        'fecha_documento': (fecha_documento or date_cls.today()).strftime('%d/%m/%Y'),
    }
    return {
        'titulo': aplicar(textos['titulo'], variables),
        'intro': aplicar(textos['intro'], variables),
        'servicios': aplicar(textos['servicios'], variables),
        'cierre': aplicar(textos['cierre'], variables),
        'empresa': empresa,
        'trabajador': trabajador,
        'textos': textos,
        'variables': variables,
        'total': total,
        'total_txt': total_txt,
    }


def contexto_finiquito(finiquito):
    trabajador = finiquito.contrato.trabajador
    empresa = trabajador.empresa
    textos = obtener_textos()
    variables = {
        'nombre': trabajador.nombre_completo,
        'rut_trabajador': trabajador.rut,
        'cargo': finiquito.contrato.cargo or '—',
        'fecha_inicio': finiquito.contrato.fecha_inicio.strftime('%d/%m/%Y'),
        'fecha_termino': finiquito.fecha_termino.strftime('%d/%m/%Y'),
        'causal': finiquito.get_motivo_display(),
        'empresa': empresa.razon_social,
        'rut_empresa': empresa.rut,
        'total': f'${finiquito.total_bruto_finiquito:,}'.replace(',', '.'),
        'lugar': textos['lugar'],
        'fecha_documento': finiquito.fecha_emision.strftime('%d/%m/%Y'),
    }
    return {
        'titulo': aplicar(textos['titulo'], variables),
        'intro': aplicar(textos['intro'], variables),
        'servicios': aplicar(textos['servicios'], variables),
        'cierre': aplicar(textos['cierre'], variables),
        'finiquito': finiquito,
        'empresa': empresa,
        'trabajador': trabajador,
    }


def html_seguro(texto):
    return escape(texto or '').replace('\n', '<br>')
