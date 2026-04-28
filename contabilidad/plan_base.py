# contabilidad/plan_base.py

"""
Diccionario estándar del Plan de Cuentas Chileno.
Clasificación básica:
1: Activos
2: Pasivos
3: Patrimonio
4: Pérdidas (Egresos)
5: Ganancias (Ingresos)
"""

PLAN_CUENTAS_BASE = [
    # --- ACTIVOS ---
    {'codigo': '1.1.01', 'nombre': 'Caja', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.02', 'nombre': 'Banco', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.03', 'nombre': 'Clientes', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.04', 'nombre': 'Mercaderías', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.05', 'nombre': 'IVA Crédito Fiscal', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.06', 'nombre': 'PPM', 'tipo': 'activo', 'obligatoria': True},
    {'codigo': '1.1.07', 'nombre': 'Anticipo de Remuneraciones', 'tipo': 'activo', 'obligatoria': False},
    {'codigo': '1.2.01', 'nombre': 'Activo Fijo (Maquinarias/Vehículos)', 'tipo': 'activo', 'obligatoria': False},
    
    # --- PASIVOS ---
    {'codigo': '2.1.01', 'nombre': 'Proveedores', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.1.02', 'nombre': 'Acreedores Varios', 'tipo': 'pasivo', 'obligatoria': False},
    {'codigo': '2.1.03', 'nombre': 'IVA Débito Fiscal', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.1.04', 'nombre': 'Impuestos por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.1.05', 'nombre': 'Remuneraciones por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.1.06', 'nombre': 'Leyes Sociales por Pagar', 'tipo': 'pasivo', 'obligatoria': True},
    {'codigo': '2.2.01', 'nombre': 'Préstamos Bancarios', 'tipo': 'pasivo', 'obligatoria': False},
    
    # --- PATRIMONIO ---
    {'codigo': '3.1.01', 'nombre': 'Capital', 'tipo': 'patrimonio', 'obligatoria': True},
    {'codigo': '3.1.02', 'nombre': 'Utilidades Acumuladas', 'tipo': 'patrimonio', 'obligatoria': True},
    {'codigo': '3.1.03', 'nombre': 'Pérdidas Acumuladas', 'tipo': 'patrimonio', 'obligatoria': False},
    {'codigo': '3.1.04', 'nombre': 'Utilidad (Pérdida) del Ejercicio', 'tipo': 'patrimonio', 'obligatoria': True},
    
    # --- PÉRDIDAS (RESULTADO) ---
    {'codigo': '4.1.01', 'nombre': 'Costo de Ventas', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.1.02', 'nombre': 'Remuneraciones', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.1.03', 'nombre': 'Honorarios', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.1.04', 'nombre': 'Arriendos', 'tipo': 'perdida', 'obligatoria': False},
    {'codigo': '4.1.05', 'nombre': 'Gastos Generales (Luz, Agua, Internet)', 'tipo': 'perdida', 'obligatoria': True},
    {'codigo': '4.1.06', 'nombre': 'Depreciación', 'tipo': 'perdida', 'obligatoria': False},
    
    # --- GANANCIAS (RESULTADO) ---
    {'codigo': '5.1.01', 'nombre': 'Ingresos por Ventas', 'tipo': 'ganancia', 'obligatoria': True},
    {'codigo': '5.1.02', 'nombre': 'Ingresos por Servicios', 'tipo': 'ganancia', 'obligatoria': False},
    {'codigo': '5.1.03', 'nombre': 'Otros Ingresos', 'tipo': 'ganancia', 'obligatoria': False},
]