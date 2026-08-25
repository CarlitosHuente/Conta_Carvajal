from django import template

register = template.Library()


@register.filter
def dict_get(mapping, key):
    if not mapping:
        return 0
    try:
        return mapping.get(key, 0)
    except AttributeError:
        return 0


@register.filter
def formato_cajas(value):
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        numero = 0
    return f'{numero:,.0f}'.replace(',', '.')


@register.filter
def formato_usd(value):
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        numero = 0
    return f'{numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


@register.filter
def formato_entero(value):
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        numero = 0
    return f'{numero:,.0f}'.replace(',', '.')
