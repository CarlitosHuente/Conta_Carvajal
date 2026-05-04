# rrhh/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class AFP(models.Model):
    # ... (sin cambios) ...
    nombre = models.CharField(max_length=100)
    tasa_dependiente = models.DecimalField(max_digits=5, decimal_places=2, help_text="Ej: 11.44")

    def __str__(self):
        return self.nombre

class SistemaSalud(models.Model):
    # ... (sin cambios) ...
    nombre = models.CharField(max_length=100, verbose_name="Sistema de Salud")
    
    def __str__(self):
        return self.nombre

class Trabajador(models.Model):
    # ... (sin cambios) ...
    ESTADO_CIVIL_CHOICES = [('S', 'Soltero/a'), ('C', 'Casado/a'), ('D', 'Divorciado/a'), ('V', 'Viudo/a')]
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Usuario (Opcional)")
    rut = models.CharField(max_length=12, unique=True)
    nombres = models.CharField(max_length=150)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    nacionalidad = models.CharField(max_length=100, default="Chilena")
    estado_civil = models.CharField(max_length=1, choices=ESTADO_CIVIL_CHOICES, default='S')
    direccion = models.CharField(max_length=255)
    comuna = models.CharField(max_length=100)
    telefono = models.CharField(max_length=15)
    email_personal = models.EmailField(unique=True)
    banco = models.CharField(max_length=100)
    tipo_cuenta = models.CharField(max_length=100)
    numero_cuenta = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellido_paterno} {self.apellido_materno}"

    def __str__(self):
        return self.nombre_completo

# --- Modelos Relacionados ---

class Contrato(models.Model):
    # ... (sin cambios en los campos existentes) ...
    TIPO_JORNADA_CHOICES = [('FULL', 'Jornada Completa'), ('PART', 'Jornada Parcial')]
    TIPO_GRATIFICACION_CHOICES = [('SIN', 'Sin Gratificación'), ('FIJA', 'Gratificación Fija Mensual'), ('LEGAL', 'Art. 50 (Tope 25% Sueldo Base)')]
    MONEDA_CHOICES = [('CLP', '$'), ('UF', 'UF')]
    trabajador = models.ForeignKey(Trabajador, on_delete=models.CASCADE, related_name="contratos")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True, help_text="Dejar en blanco si es indefinido")
    vigente = models.BooleanField(default=True)
    afp = models.ForeignKey(AFP, on_delete=models.PROTECT)
    sistema_salud = models.ForeignKey(SistemaSalud, on_delete=models.PROTECT)
    plan_salud_pactado = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        help_text="Monto del plan (CLP o UF); hasta 3 decimales en UF (ej. 3,357)",
    )
    moneda_plan_salud = models.CharField(max_length=3, choices=MONEDA_CHOICES, default='CLP')
    sueldo_base = models.PositiveIntegerField()
    colacion = models.PositiveIntegerField(default=0, help_text="Haber no imponible")
    movilizacion = models.PositiveIntegerField(default=0, help_text="Haber no imponible")
    tipo_gratificacion = models.CharField(max_length=5, choices=TIPO_GRATIFICACION_CHOICES, default='LEGAL')
    monto_gratificacion_fija = models.PositiveIntegerField(default=0, help_text="Llenar solo si el tipo de gratificación es Fija Mensual")
    tipo_jornada = models.CharField(max_length=4, choices=TIPO_JORNADA_CHOICES, default='FULL')
    horas_semanales = models.PositiveIntegerField(default=45)
    dias_semana = models.PositiveIntegerField(default=5)
    conceptos_variables = models.ManyToManyField('ConceptoVariable', blank=True, verbose_name="Conceptos Variables Aplicables")

    def __str__(self):
        return f"Contrato de {self.trabajador.nombre_completo} (Inicio: {self.fecha_inicio})"

# --- ¡NUEVO MODELO PARA ITEMS RECURRENTES DEL CONTRATO! ---
class ItemContrato(models.Model):
    TIPO_ITEM_CHOICES = [('HABER', 'Haber'), ('DESCUENTO', 'Descuento')]
    
    contrato = models.ForeignKey(Contrato, related_name='items_recurrentes', on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100, help_text="Ej: Bono de Producción, Descuento Farmacia")
    monto = models.PositiveIntegerField()
    tipo = models.CharField(max_length=10, choices=TIPO_ITEM_CHOICES, default='HABER')
    es_imponible = models.BooleanField(default=True, verbose_name="¿Es imponible?")

    def __str__(self):
        return f"{self.nombre} (${self.monto}) para {self.contrato}"

class ConceptoVariable(models.Model):
    """
    Define un tipo de haber o descuento cuyo monto no es fijo, sino que se calcula
    en base a una regla (ej: comisiones por venta).
    """
    TIPO_CALCULO_CHOICES = [
        ('PORCENTAJE', 'Porcentaje Fijo sobre una base'),
        ('TRAMOS', 'Porcentaje Escalonado (Por Tramos de Venta/Base)')
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='conceptos_variables')
    nombre = models.CharField(max_length=100, help_text="Ej: Comisión por Ventas, Bono por Cumplimiento")
    tipo_calculo = models.CharField(max_length=20, choices=TIPO_CALCULO_CHOICES, default='PORCENTAJE')
    porcentaje_calculo = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, help_text="Usa solo si es Porcentaje Fijo. Ej: 2.5 para 2.5%")
    es_imponible = models.BooleanField(default=True, verbose_name="¿Es imponible?")

    def __str__(self):
        return f"{self.nombre} ({self.empresa.razon_social})"

class TramoConcepto(models.Model):
    concepto = models.ForeignKey(ConceptoVariable, on_delete=models.CASCADE, related_name='tramos')
    tramo_desde = models.PositiveIntegerField(default=0, verbose_name="Desde ($)")
    tramo_hasta = models.PositiveIntegerField(null=True, blank=True, verbose_name="Hasta ($)", help_text="Dejar en blanco si no tiene límite superior")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Tasa (%)")

    class Meta:
        ordering = ['tramo_desde']

    def __str__(self):
        return f"De {self.tramo_desde} a {self.tramo_hasta or 'Infinito'} -> {self.porcentaje}%"

class Liquidacion(models.Model):
    # ... (sin cambios) ...
    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT)
    mes = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()
    fecha_emision = models.DateField(default=timezone.now)
    
    # FOTOGRAFÍA INMUTABLE (Snapshot de los datos al momento del cálculo)
    dias_trabajados = models.PositiveIntegerField(default=30)
    uf_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    utm_valor = models.PositiveIntegerField(default=0)
    afp_nombre = models.CharField(max_length=50, default="")
    afp_tasa = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    salud_nombre = models.CharField(max_length=50, default="")
    
    # TOTALES AGRUPADOS
    total_haberes_imponibles = models.IntegerField(default=0)
    total_haberes_no_imponibles = models.IntegerField(default=0)
    total_descuentos_legales = models.IntegerField(default=0)
    total_descuentos_varios = models.IntegerField(default=0)
    
    sueldo_liquido = models.IntegerField(default=0)

    class Meta:
        unique_together = ('contrato', 'mes', 'ano')

    def __str__(self):
        return f"Liquidación de {self.contrato.trabajador.nombre_completo} para {self.mes}/{self.ano}"

class ItemLiquidacion(models.Model):
    # ... (sin cambios) ...
    TIPO_ITEM_CHOICES = [('HABER', 'Haber'), ('DESCUENTO', 'Descuento')]
    liquidacion = models.ForeignKey(Liquidacion, related_name='items', on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)
    monto = models.PositiveIntegerField()
    tipo = models.CharField(max_length=10, choices=TIPO_ITEM_CHOICES)
    es_imponible = models.BooleanField(default=True, verbose_name="¿Es imponible?")

    def __str__(self):
        return f"{self.nombre} (${self.monto})"

class Prestamo(models.Model):
    # ... (sin cambios) ...
    contrato = models.ForeignKey(Contrato, on_delete=models.CASCADE)
    monto_total = models.PositiveIntegerField()
    numero_cuotas = models.PositiveIntegerField()
    fecha_solicitud = models.DateField()
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Préstamo de ${self.monto_total} a {self.contrato.trabajador.nombre_completo}"
    
class ConceptoNoImponible(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre
    
class IndicadorEconomico(models.Model):
    # Período
    mes = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()

    # Valores base
    uf = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor UF ($)")
    utm = models.PositiveIntegerField(verbose_name="Valor UTM ($)")
    sueldo_minimo = models.PositiveIntegerField(verbose_name="Sueldo Mínimo ($)")

    # Topes Imponibles (editables en UF y calculados en $)
    tope_imponible_afp_uf = models.DecimalField(max_digits=5, decimal_places=1, default=81.6, verbose_name="Tope Imponible AFP (UF)")
    tope_imponible_afp_pesos = models.PositiveIntegerField(verbose_name="Tope Imponible AFP ($)")
    
    tope_imponible_cesantia_uf = models.DecimalField(max_digits=5, decimal_places=1, default=122.6, verbose_name="Tope Imponible Seguro Cesantía (UF)")
    tope_imponible_cesantia_pesos = models.PositiveIntegerField(verbose_name="Tope Imponible Seguro Cesantía ($)")

    # Tasas
    tasa_sis = models.DecimalField(max_digits=4, decimal_places=2, verbose_name="Tasa SIS (%)")

    # Tasas Históricas de AFP (para cálculo inmutable)
    tasa_afp_capital = models.DecimalField(max_digits=5, decimal_places=2, default=11.44)
    tasa_afp_cuprum = models.DecimalField(max_digits=5, decimal_places=2, default=11.44)
    tasa_afp_habitat = models.DecimalField(max_digits=5, decimal_places=2, default=11.27)
    tasa_afp_modelo = models.DecimalField(max_digits=5, decimal_places=2, default=10.58)
    tasa_afp_planvital = models.DecimalField(max_digits=5, decimal_places=2, default=11.16)
    tasa_afp_provida = models.DecimalField(max_digits=5, decimal_places=2, default=11.45)
    tasa_afp_uno = models.DecimalField(max_digits=5, decimal_places=2, default=10.69)
    # Asignación Familiar
    asig_familiar_tramo_a_monto = models.PositiveIntegerField(verbose_name="Monto Tramo A")
    asig_familiar_tramo_a_limite = models.PositiveIntegerField(verbose_name="Límite Ingreso Tramo A ($)")
    asig_familiar_tramo_b_monto = models.PositiveIntegerField(verbose_name="Monto Tramo B")
    asig_familiar_tramo_b_limite = models.PositiveIntegerField(verbose_name="Límite Ingreso Tramo B ($)")
    asig_familiar_tramo_c_monto = models.PositiveIntegerField(verbose_name="Monto Tramo C")
    asig_familiar_tramo_c_limite = models.PositiveIntegerField(verbose_name="Límite Ingreso Tramo C ($)")

    class Meta:
        # Evita que se dupliquen períodos y ordena por fecha descendente
        unique_together = ('mes', 'ano')
        ordering = ['-ano', '-mes']

    def __str__(self):
        return f"Indicadores para {self.mes}/{self.ano}"
    
# SECCION: Control de Cobranza Mensual
class RegistroCobro(models.Model):
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='cobros')
    mes = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()
    
    monto_uf = models.DecimalField(max_digits=10, decimal_places=2)
    valor_uf_aplicado = models.DecimalField(max_digits=10, decimal_places=2)
    total_pesos = models.PositiveIntegerField(editable=False)

    pagado = models.BooleanField(default=False)
    nro_bh_emitida = models.CharField(max_length=50, blank=True, verbose_name="N° Boleta")
    fecha_pago = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('empresa', 'mes', 'ano')

    def save(self, *args, **kwargs):
        self.total_pesos = round(self.monto_uf * self.valor_uf_aplicado)
        super().save(*args, **kwargs)

class NovedadMensual(models.Model):
    """
    Registra la asistencia, licencias y horas extras de un trabajador en un mes específico.
    Es el paso previo y obligatorio antes de calcular su liquidación.
    """
    trabajador = models.ForeignKey(Trabajador, on_delete=models.CASCADE, related_name='novedades')
    mes = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    ano = models.IntegerField()
    
    # Asistencia (En Chile el mes comercial siempre es de 30 días para cálculo base)
    dias_trabajados = models.IntegerField(default=30) 
    dias_licencia = models.IntegerField(default=0)
    dias_ausencia = models.IntegerField(default=0)
    
    # Horas Extras
    horas_extras_50 = models.IntegerField(default=0, help_text="Horas extras normales (50%)")
    horas_extras_100 = models.IntegerField(default=0, help_text="Horas extras domingos/festivos (100%)")
    
    # Bonos o Descuentos excepcionales (que NO están en el contrato regular)
    bono_esporadico = models.IntegerField(default=0, help_text="Bonos por única vez en este mes ($)")
    descuento_esporadico = models.IntegerField(default=0, help_text="Descuentos por única vez en este mes ($)")
    
    # Campo flexible para guardar las bases de cálculo de los Conceptos Variables
    datos_variables = models.JSONField(default=dict, blank=True, help_text="Almacena bases de cálculo, ej: {'1': 1000000}")

    class Meta:
        # Un trabajador solo puede tener un registro de novedades por mes y año
        unique_together = ('trabajador', 'mes', 'ano')
        verbose_name = "Novedad Mensual"
        verbose_name_plural = "Novedades Mensuales"

    def __str__(self):
        return f"Novedades {self.trabajador.nombres} {self.trabajador.apellido_paterno} - {self.mes}/{self.ano}"
    
    def save(self, *args, **kwargs):
        # Auto-cálculo: Los días trabajados siempre son 30 menos las ausencias y licencias.
        self.dias_trabajados = 30 - self.dias_ausencia - self.dias_licencia
        if self.dias_trabajados < 0:
            self.dias_trabajados = 0
        super().save(*args, **kwargs)