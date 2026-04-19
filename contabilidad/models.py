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
