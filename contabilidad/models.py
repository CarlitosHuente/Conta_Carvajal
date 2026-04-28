from django.db import models
from core.models import Empresa

class CodigoF29(models.Model):
    """
    Diccionario dinámico de códigos del SII. 
    Se alimentará automáticamente cuando el usuario asigne un nombre a un código nuevo.
    """
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código SII")
    descripcion = models.CharField(max_length=255, verbose_name="Descripción del Código")

    class Meta:
        verbose_name = "Código F29"
        verbose_name_plural = "Diccionario Códigos F29"
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"

class ReglaValidacion(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Regla", help_text="Ej: Cuadratura de IVA a Pagar")
    codigos_suma = models.CharField(max_length=255, blank=True, verbose_name="Códigos que Suman", help_text="Separados por coma. Ej: 538, 142")
    codigos_resta = models.CharField(max_length=255, blank=True, verbose_name="Códigos que Restan", help_text="Separados por coma. Ej: 539, 062")
    codigo_resultado = models.CharField(max_length=10, verbose_name="Código Resultado", help_text="El código que debe coincidir con la operación. Ej: 91")
    activa = models.BooleanField(default=True, verbose_name="Regla Activa")

    class Meta:
        verbose_name = "Regla de Validación"
        verbose_name_plural = "Reglas de Validación"

    def __str__(self):
        return self.nombre

class DeclaracionF29(models.Model):
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente de Revisión'),
        ('verificado', 'Cuadratura Verificada'),
        ('error', 'Error en Cuadratura'),
    )

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='declaraciones_f29')
    mes = models.IntegerField(verbose_name="Mes Tributario")
    ano = models.IntegerField(verbose_name="Año Tributario")
    folio = models.CharField(max_length=50, blank=True, null=True, verbose_name="Folio F29")
    
    total_a_pagar = models.IntegerField(default=0, verbose_name="Total a Pagar (o Favor)")
    
    # Almacenamiento crudo y eficiente de códigos (Ej: {"549": 10000})
    datos_extraidos = models.JSONField(default=dict, verbose_name="Códigos Extraídos")
    
    # Almacenaremos el reporte matemático de por qué falló o acertó la cuadratura
    detalles_cuadratura = models.JSONField(default=list, blank=True, null=True, verbose_name="Detalles de Cuadratura")
    
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_carga = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Declaración F29"
        verbose_name_plural = "Declaraciones F29"
        unique_together = ('empresa', 'mes', 'ano') 

    def __str__(self):
        return f"F29 {self.empresa.rut} - {self.mes}/{self.ano}"

    @property
    def detalles_legibles(self):
        """
        Transforma los códigos del JSON consultando la base de datos de Códigos.
        """
        # Traemos todos los códigos que este F29 contiene desde la BD para no hacer 100 consultas
        codigos_db = {c.codigo: c.descripcion for c in CodigoF29.objects.filter(codigo__in=self.datos_extraidos.keys())}
        
        resultado = {}
        for codigo, valor in self.datos_extraidos.items():
            nombre_legible = codigos_db.get(str(codigo), f"Código {codigo} (Sin nombre)")
            resultado[nombre_legible] = valor
        return resultado
        
    def verificar_cuadratura(self):
        reglas = ReglaValidacion.objects.filter(activa=True)
        if not reglas.exists():
            self.estado = 'pendiente'
            self.detalles_cuadratura = []
            return
            
        todas_cumplen = True
        detalles = []
        
        for regla in reglas:
            suma = 0
            resta = 0
            detalles_suma = {}
            detalles_resta = {}
            
            if regla.codigos_suma:
                for cod in regla.codigos_suma.replace(' ', '').split(','):
                    val = int(self.datos_extraidos.get(cod, 0) or 0)
                    suma += val
                    detalles_suma[cod] = val
                    
            if regla.codigos_resta:
                for cod in regla.codigos_resta.replace(' ', '').split(','):
                    val = int(self.datos_extraidos.get(cod, 0) or 0)
                    resta += val
                    detalles_resta[cod] = val
                    
            esperado = int(self.datos_extraidos.get(regla.codigo_resultado, 0) or 0)
            calculado = suma - resta
            cumple = (calculado == esperado)
            
            if not cumple:
                todas_cumplen = False
                
            detalles.append({
                'regla': regla.nombre,
                'calculado': calculado,
                'esperado': esperado,
                'diferencia': calculado - esperado,
                'cumple': cumple,
                'elementos_suma': detalles_suma,
                'elementos_resta': detalles_resta,
                'codigo_resultado': regla.codigo_resultado
            })
                
        self.detalles_cuadratura = detalles
        self.estado = 'verificado' if todas_cumplen else 'error'

# =====================================================================
# MÓDULO DE PLAN DE CUENTAS Y CENTRALIZACIÓN (CONTABILIDAD SIMPLIFICADA)
# =====================================================================

class CuentaContable(models.Model):
    TIPO_CHOICES = (
        ('activo', 'Activo'),
        ('pasivo', 'Pasivo'),
        ('patrimonio', 'Patrimonio'),
        ('perdida', 'Resultado Pérdida'),
        ('ganancia', 'Resultado Ganancia'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='cuentas_contables')
    codigo = models.CharField(max_length=20, verbose_name="Código de Cuenta", help_text="Ej: 1.1.01.01")
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Cuenta", help_text="Ej: IVA Crédito Fiscal")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)

    class Meta:
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Planes de Cuentas"
        unique_together = ('empresa', 'codigo')
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class PlantillaCentralizacion(models.Model):
    TIPO_ORIGEN_CHOICES = (
        ('f29', 'Formulario 29 (Simplificada)'),
        ('rcv', 'Registro de Compra y Ventas (Completa - Próximamente)'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='plantillas_centralizacion')
    nombre = models.CharField(max_length=100, verbose_name="Nombre de la Plantilla", help_text="Ej: Centralización Compras F29")
    tipo_origen = models.CharField(max_length=10, choices=TIPO_ORIGEN_CHOICES, default='f29')

    class Meta:
        verbose_name = "Plantilla de Centralización"
        verbose_name_plural = "Plantillas de Centralización"

    def __str__(self):
        return f"{self.nombre} ({self.empresa.razon_social})"

class LineaPlantilla(models.Model):
    MOVIMIENTO_CHOICES = (
        ('debe', 'Debe'),
        ('haber', 'Haber'),
    )
    plantilla = models.ForeignKey(PlantillaCentralizacion, on_delete=models.CASCADE, related_name='lineas')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.CASCADE)
    tipo_movimiento = models.CharField(max_length=10, choices=MOVIMIENTO_CHOICES)
    formula = models.CharField(max_length=255, verbose_name="Fórmula de Cálculo", help_text="Usa códigos entre corchetes. Ej: ([520] / 19) * 100")

    class Meta:
        verbose_name = "Línea de Plantilla"
        verbose_name_plural = "Líneas de Plantilla"

    def __str__(self):
        return f"{self.cuenta.nombre} - {self.tipo_movimiento} - {self.formula}"

class AsientoContable(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='asientos')
    fecha = models.DateField(verbose_name="Fecha del Asiento")
    glosa = models.CharField(max_length=255, verbose_name="Glosa o Descripción")
    
    # Relaciones de origen (Polimorfismo básico). 
    # Si el asiento viene de un F29, se llena este campo. Si viene de RCV (futuro), usaremos el otro.
    origen_f29 = models.ForeignKey('DeclaracionF29', on_delete=models.SET_NULL, null=True, blank=True, related_name='asientos_generados', verbose_name="Origen F29")
    # origen_rcv = models.ForeignKey('RegistroCompraVenta', on_delete=models.SET_NULL, null=True, blank=True) # <-- Se activará en el futuro

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Libro Diario (Asientos)"
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"Asiento {self.id} - {self.empresa.rut} - {self.fecha}"

class LineaAsiento(models.Model):
    asiento = models.ForeignKey(AsientoContable, on_delete=models.CASCADE, related_name='lineas')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.PROTECT) # PROTECT: Evita borrar la cuenta si ya tiene asientos
    debe = models.BigIntegerField(default=0, verbose_name="Debe")
    haber = models.BigIntegerField(default=0, verbose_name="Haber")

    class Meta:
        verbose_name = "Línea de Asiento"
        verbose_name_plural = "Líneas de Asiento"

    def __str__(self):
        return f"{self.cuenta.nombre}: D={self.debe} H={self.haber}"
