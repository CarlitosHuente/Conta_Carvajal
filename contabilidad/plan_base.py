# contabilidad/plan_base.py

"""
Plan de cuentas base — formato estándar X.XX.XX
  Clase (1 dígito) . Grupo (2 dígitos) . Cuenta (2 dígitos)

Clasificación:
  1 Activos | 2 Pasivos | 3 Patrimonio | 4 Pérdidas | 5 Ganancias
"""

TIPO_NOMBRES = {
    'activo': 'Activos',
    'pasivo': 'Pasivos',
    'patrimonio': 'Patrimonio',
    'perdida': 'Pérdidas (Estado de Resultados)',
    'ganancia': 'Ganancias (Estado de Resultados)',
}

ORDEN_TIPOS = ['activo', 'pasivo', 'patrimonio', 'ganancia', 'perdida']

PLAN_CUENTAS_BASE = [
    # --- ACTIVOS (1.01 Circulante / 1.02 No circulante) ---
    {'codigo': '1.01.01', 'nombre': 'Caja', 'tipo': 'activo', 'subtipo': 'caja', 'obligatoria': True},
    {'codigo': '1.01.02', 'nombre': 'Banco', 'tipo': 'activo', 'subtipo': 'banco', 'obligatoria': True},
    {'codigo': '1.01.03', 'nombre': 'Clientes', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.01.04', 'nombre': 'Mercaderías', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.01.05', 'nombre': 'IVA Crédito Fiscal', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.01.06', 'nombre': 'PPM', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.01.07', 'nombre': 'Anticipo de Remuneraciones', 'tipo': 'activo', 'obligatoria': False},
    {'codigo': '1.02.01', 'nombre': 'Activo Fijo (Maquinarias/Vehículos)', 'tipo': 'activo', 'obligatoria': False},

    # --- PASIVOS (2.01 Comerciales / 2.02 Remuneraciones / 2.03 Financieros) ---
    {'codigo': '2.01.01', 'nombre': 'Proveedores', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.01.02', 'nombre': 'Acreedores Varios', 'tipo': 'pasivo', 'obligatoria': False},
    {'codigo': '2.01.03', 'nombre': 'IVA Débito Fiscal', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.01.04', 'nombre': 'Impuestos por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.01', 'nombre': 'Remuneraciones por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.02', 'nombre': 'Cotizaciones Previred por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.03', 'nombre': 'SIS por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.04', 'nombre': 'AFC Empleador por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.05', 'nombre': 'Impuesto Único por Pagar (SII)', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.02.06', 'nombre': 'Otros Descuentos al Personal', 'tipo': 'pasivo', 'obligatoria': False},
    {'codigo': '2.03.01', 'nombre': 'Préstamos Bancarios', 'tipo': 'pasivo', 'obligatoria': False},

    # --- PATRIMONIO ---
    {'codigo': '3.01.01', 'nombre': 'Capital', 'tipo': 'patrimonio', 'obligatoria': True},
    {'codigo': '3.01.02', 'nombre': 'Utilidades Acumuladas', 'tipo': 'patrimonio', 'obligatoria': True},
    {'codigo': '3.01.03', 'nombre': 'Pérdidas Acumuladas', 'tipo': 'patrimonio', 'obligatoria': False},
    {'codigo': '3.01.04', 'nombre': 'Utilidad (Pérdida) del Ejercicio', 'tipo': 'patrimonio', 'obligatoria': True},

    # --- GANANCIAS (Estado de Resultados) ---
    {'codigo': '5.01.01', 'nombre': 'Ingresos por Ventas', 'tipo': 'ganancia', 'obligatoria': True},
    {'codigo': '5.01.02', 'nombre': 'Ingresos por Servicios', 'tipo': 'ganancia', 'obligatoria': False},
    {'codigo': '5.02.01', 'nombre': 'Otros Ingresos', 'tipo': 'ganancia', 'obligatoria': False},

    # --- PÉRDIDAS (Estado de Resultados) ---
    {'codigo': '4.01.01', 'nombre': 'Costo de Ventas', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.02.01', 'nombre': 'Remuneraciones', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.02.02', 'nombre': 'Gratificaciones', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.02.03', 'nombre': 'Leyes Sociales Empleador', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.03.01', 'nombre': 'Honorarios', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.03.02', 'nombre': 'Arriendos', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.03.03', 'nombre': 'Gastos Generales (Luz, Agua, Internet)', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.04.01', 'nombre': 'Depreciación', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.05.01', 'nombre': 'Gastos Financieros', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.06.01', 'nombre': 'Otros Gastos', 'tipo': 'perdida', 'obligatoria': False},
]
