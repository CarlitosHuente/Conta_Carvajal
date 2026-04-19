from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Empresa(models.Model):
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    razon_social = models.CharField(max_length=255, verbose_name="Razón Social")
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    correo_contacto = models.EmailField(verbose_name="Correo de Contacto")
    
    # SECCION: Gestión de Cliente y Claves
    tipo_contribuyente = models.CharField(max_length=1, choices=[('P', 'Persona'), ('E', 'Empresa')], default='E')
    giro = models.CharField(max_length=255, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    rep_legal_nombre = models.CharField(max_length=255, blank=True)
    rep_legal_rut = models.CharField(max_length=12, blank=True)
    clave_sii = models.CharField(max_length=100, blank=True)
    clave_previred = models.CharField(max_length=100, blank=True)
    clave_unica = models.CharField(max_length=100, blank=True)
    clave_certificado = models.CharField(max_length=100, blank=True)
    honorario_mensual_uf = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_renta_anual = models.PositiveIntegerField(default=0)

    # ¡NUEVO! Interruptores de Módulos (Por defecto los activamos para no romper lo actual)
    tiene_rrhh = models.BooleanField(default=True, verbose_name="¿Módulo RRHH Activo?")
    tiene_contabilidad = models.BooleanField(default=False, verbose_name="¿Módulo Contabilidad Activo?")
    tiene_cobranza = models.BooleanField(default=True, verbose_name="¿Módulo Cobranza Activo?")

    def __str__(self):
        return self.razon_social

class PerfilUsuario(models.Model):
    ROLES = (('admin', 'Administrador/Contador'), ('cliente', 'Cliente'))
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=20, choices=ROLES, default='cliente')
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, help_text="Asignar solo si el rol es Cliente")

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"

@receiver(post_save, sender=Empresa)
def crear_usuario_cliente(sender, instance, created, **kwargs):
    if created:
        username = instance.rut.replace(".", "").replace("-", "").lower()
        user, _ = User.objects.get_or_create(username=username, email=instance.correo_contacto)
        user.set_password(username) 
        user.save()
        PerfilUsuario.objects.get_or_create(user=user, rol='cliente', empresa=instance)
