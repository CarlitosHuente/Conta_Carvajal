# rrhh/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

# --- Modelos Base sin cambios ---
class Empresa(models.Model):
    # ... (sin cambios) ...
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    razon_social = models.CharField(max_length=255, verbose_name="Razón Social")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    correo_contacto = models.EmailField(verbose_name="Correo de Contacto")
    
    # SECCION: Gestión de Cliente y Claves
    tipo_contribuyente = models.CharField(max_length=1, choices=[('P', 'Persona'), ('E', 'Empresa')], default='E')
    giro = models.CharField(max_length=255, blank=True)
    direccion = models.CharField(max_length=255, blank=True)

    # Representante
    rep_legal_nombre = models.CharField(max_length=255, blank=True)
    rep_legal_rut = models.CharField(max_length=12, blank=True)

    # Credenciales
    clave_sii = models.CharField(max_length=100, blank=True)
    clave_previred = models.CharField(max_length=100, blank=True)
    clave_unica = models.CharField(max_length=100, blank=True)
    clave_certificado = models.CharField(max_length=100, blank=True)

    # Honorarios fijos
    honorario_mensual_uf = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_renta_anual = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.razon_social

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
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
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
    plan_salud_pactado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    moneda_plan_salud = models.CharField(max_length=3, choices=MONEDA_CHOICES, default='CLP')
    sueldo_base = models.PositiveIntegerField()
    colacion = models.PositiveIntegerField(default=0, help_text="Haber no imponible")
    movilizacion = models.PositiveIntegerField(default=0, help_text="Haber no imponible")
    tipo_gratificacion = models.CharField(max_length=5, choices=TIPO_GRATIFICACION_CHOICES, default='LEGAL')
    monto_gratificacion_fija = models.PositiveIntegerField(default=0, help_text="Llenar solo si el tipo de gratificación es Fija Mensual")
    tipo_jornada = models.CharField(max_length=4, choices=TIPO_JORNADA_CHOICES, default='FULL')
    horas_semanales = models.PositiveIntegerField(default=45)
    dias_semana = models.PositiveIntegerField(default=5)

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

class Liquidacion(models.Model):
    # ... (sin cambios) ...
    contrato = models.ForeignKey(Contrato, on_delete=models.PROTECT)
    mes = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()
    fecha_emision = models.DateField(default=timezone.now)
    sueldo_liquido = models.IntegerField(default=0)
    total_haberes = models.IntegerField(default=0)
    total_descuentos = models.IntegerField(default=0)

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
    

# --- SECCION PERFILES Y ROLES ---
class PerfilUsuario(models.Model):
    ROLES = (
        ('admin', 'Administrador/Contador'),
        ('cliente', 'Cliente'),
    )
    # Relación uno a uno con el usuario nativo de Django
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    
    # Define qué puede hacer en el ERP
    rol = models.CharField(max_length=20, choices=ROLES, default='cliente')
    
    # Vinculación obligatoria para Clientes
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, help_text="Asignar solo si el rol es Cliente")

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"
    
# SECCION: Control de Cobranza Mensual
class RegistroCobro(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='cobros')
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
        

# === SIGNALS / AUTOMATIZACIONES ===
@receiver(post_save, sender=Empresa)
def crear_usuario_cliente(sender, instance, created, **kwargs):
    if created:
        # Creamos usuario usando el RUT como username (sin puntos ni guión)
        username = instance.rut.replace(".", "").replace("-", "").lower()
        user, _ = User.objects.get_or_create(username=username, email=instance.correo_contacto)
        # Seteamos una clave inicial por defecto (el mismo rut o algo genérico)
        user.set_password(username) 
        user.save()
        
        # Le asignamos el PerfilUsuario con rol cliente
        from .models import PerfilUsuario
        PerfilUsuario.objects.get_or_create(user=user, rol='cliente', empresa=instance)