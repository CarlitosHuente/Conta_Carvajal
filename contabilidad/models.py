from django.conf import settings
from django.db import models
from django.db.models import Q
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
    SUBTIPO_CHOICES = (
        ('general', 'General'),
        ('caja', 'Caja / Efectivo'),
        ('banco', 'Banco'),
        ('clientes', 'Clientes'),
        ('proveedores', 'Proveedores'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='cuentas_contables')
    codigo = models.CharField(max_length=20, verbose_name="Código de Cuenta", help_text="Ej: 1.01.05")
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Cuenta", help_text="Ej: IVA Crédito Fiscal")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    subtipo_operacion = models.CharField(
        max_length=20, choices=SUBTIPO_CHOICES, default='general', blank=True,
        verbose_name='Subtipo operativo',
    )

    class Meta:
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Planes de Cuentas"
        unique_together = ('empresa', 'codigo')
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def tiene_movimientos(self):
        return self.lineaasiento_set.exists()

    def subtipo_detectado(self):
        if self.subtipo_operacion and self.subtipo_operacion != 'general':
            return self.subtipo_operacion
        mapa_prefijos = (
            ('1.01.01', 'caja'),
            ('1.01.02', 'banco'),
            ('1.01.03', 'clientes'),
            ('2.01.01', 'proveedores'),
        )
        for prefijo, subtipo in mapa_prefijos:
            if self.codigo.startswith(prefijo):
                return subtipo
        return 'general'

    def permite_saldar_operaciones(self):
        return self.asignaciones_acciones.filter(accion__activa=True).exists()


class AccionRapida(models.Model):
    """Plantilla reutilizable de pago/cobro — se asigna a una o más cuentas."""
    TIPO_CHOICES = (
        ('pago', 'Pago'),
        ('cobro', 'Cobro'),
    )
    LADO_CHOICES = (
        ('debe', 'Debe'),
        ('haber', 'Haber'),
    )
    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name='acciones_rapidas',
    )
    nombre = models.CharField(max_length=80, verbose_name='Nombre', help_text='Ej: Pago estándar, Cobro clientes')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='pago')
    lado_pendiente = models.CharField(
        max_length=10, choices=LADO_CHOICES, default='haber',
        verbose_name='Movimientos pendientes en',
        help_text='Lado del mayor que queda por saldar.',
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Acción rápida'
        verbose_name_plural = 'Acciones rápidas'
        ordering = ['nombre', 'id']

    def __str__(self):
        return f'{self.nombre} ({self.get_tipo_display()})'


class CuentaAccionRapida(models.Model):
    """Vincula una acción rápida a una cuenta del plan."""
    cuenta = models.ForeignKey(
        CuentaContable, on_delete=models.CASCADE, related_name='asignaciones_acciones',
    )
    accion = models.ForeignKey(
        AccionRapida, on_delete=models.CASCADE, related_name='asignaciones_cuentas',
    )
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Asignación acción rápida'
        verbose_name_plural = 'Asignaciones acciones rápidas'
        unique_together = ('cuenta', 'accion')
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.cuenta.codigo} ← {self.accion.nombre}'


class LineaAccionRapida(models.Model):
    accion = models.ForeignKey(
        AccionRapida, on_delete=models.CASCADE, related_name='lineas_contrapartida',
    )
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.CASCADE)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Contrapartida de acción rápida'
        verbose_name_plural = 'Contrapartidas de acción rápida'
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.cuenta.codigo} ({self.accion.nombre})'

class PlantillaCentralizacion(models.Model):
    TIPO_ORIGEN_CHOICES = (
        ('f29', 'Formulario 29 (Simplificada)'),
        ('rcv', 'Registro de Compra y Ventas'),
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
    TIPO_ASIENTO_CHOICES = (
        ('manual', 'Comprobante manual'),
        ('f29', 'Centralización F29'),
        ('rcv', 'Compra RCV'),
        ('rrhh', 'Remuneraciones'),
        ('pago', 'Pago a proveedores'),
        ('cobro', 'Cobro a clientes'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='asientos')
    fecha = models.DateField(verbose_name="Fecha del Asiento")
    glosa = models.CharField(max_length=255, verbose_name="Glosa o Descripción")
    tipo_asiento = models.CharField(max_length=20, choices=TIPO_ASIENTO_CHOICES, default='manual')
    
    # Relaciones de origen (Polimorfismo básico). 
    # Si el asiento viene de un F29, se llena este campo. Si viene de RCV (futuro), usaremos el otro.
    origen_f29 = models.ForeignKey('DeclaracionF29', on_delete=models.SET_NULL, null=True, blank=True, related_name='asientos_generados', verbose_name="Origen F29")
    origen_plantilla = models.ForeignKey(
        'PlantillaCentralizacion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asientos_generados',
        verbose_name='Plantilla de centralización',
    )
    origen_rrhh_mes = models.PositiveIntegerField(null=True, blank=True, verbose_name='Mes origen RR.HH.')
    origen_rrhh_ano = models.PositiveIntegerField(null=True, blank=True, verbose_name='Año origen RR.HH.')
    origen_importacion_rcv = models.ForeignKey(
        'ImportacionRCVCompra', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='asientos_generados',
        verbose_name='Importación RCV origen',
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Asiento Contable"
        verbose_name_plural = "Libro Diario (Asientos)"
        ordering = ['-fecha', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'origen_rrhh_mes', 'origen_rrhh_ano'],
                condition=models.Q(origen_rrhh_mes__isnull=False, origen_rrhh_ano__isnull=False),
                name='unique_asiento_rrhh_periodo',
            ),
            models.UniqueConstraint(
                fields=['origen_f29', 'origen_plantilla'],
                condition=models.Q(origen_f29__isnull=False, origen_plantilla__isnull=False),
                name='unique_asiento_f29_plantilla',
            ),
        ]

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

    @property
    def importe(self):
        return self.debe if self.debe else self.haber

    @property
    def monto_aplicado(self):
        return sum(a.monto for a in self.aplicaciones_salida.all())

    @property
    def monto_pendiente(self):
        return max(0, self.importe - self.monto_aplicado)

    @property
    def esta_saldada(self):
        return self.monto_pendiente == 0


class AplicacionCobroPago(models.Model):
    TIPO_CHOICES = (
        ('pago', 'Pago'),
        ('cobro', 'Cobro'),
    )
    asiento_pago = models.ForeignKey(AsientoContable, on_delete=models.CASCADE, related_name='aplicaciones')
    linea_origen = models.ForeignKey(LineaAsiento, on_delete=models.PROTECT, related_name='aplicaciones_salida')
    monto = models.BigIntegerField(verbose_name='Monto aplicado')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)

    class Meta:
        verbose_name = 'Aplicación cobro/pago'
        verbose_name_plural = 'Aplicaciones cobro/pago'

    def __str__(self):
        return f'{self.get_tipo_display()} ${self.monto:,} → línea #{self.linea_origen_id}'


# =====================================================================
# PROVEEDORES GLOBALES Y RCV COMPRAS
# =====================================================================

class ProveedorGlobal(models.Model):
    RUBRO_CHOICES = (
        ('', 'Sin clasificar'),
        ('farmacia', 'Farmacia / droguería'),
        ('insumos_medicos', 'Insumos médicos'),
        ('servicios', 'Servicios'),
        ('tecnologia', 'Tecnología'),
        ('otro', 'Otro'),
    )
    rut = models.CharField(max_length=12, unique=True, verbose_name='RUT')
    razon_social = models.CharField(max_length=255)
    razon_social_sii = models.CharField(max_length=255, blank=True, default='')
    rubro = models.CharField(max_length=30, choices=RUBRO_CHOICES, blank=True, default='')
    notas = models.TextField(blank=True, default='')
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Proveedor global'
        verbose_name_plural = 'Proveedores globales'
        ordering = ['razon_social']

    def __str__(self):
        return f'{self.rut} — {self.razon_social}'


class EmpresaProveedor(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='proveedores_vinculados')
    proveedor = models.ForeignKey(ProveedorGlobal, on_delete=models.CASCADE, related_name='vinculos_empresa')
    cuenta_gasto_habitual = models.ForeignKey(
        CuentaContable, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    veces_contabilizado = models.PositiveIntegerField(default=0)
    primera_compra = models.DateField(null=True, blank=True)
    ultima_compra = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Proveedor por empresa'
        verbose_name_plural = 'Proveedores por empresa'
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'proveedor'], name='unique_empresa_proveedor'),
        ]

    def __str__(self):
        return f'{self.empresa.razon_social} ↔ {self.proveedor.rut}'


class ProveedorCuentaStats(models.Model):
    proveedor = models.ForeignKey(ProveedorGlobal, on_delete=models.CASCADE, related_name='stats_cuentas')
    cuenta = models.ForeignKey(CuentaContable, on_delete=models.CASCADE, related_name='+')
    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name='+',
        help_text='Vacío = estadística global del estudio (todas las empresas).',
    )
    contador = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Estadística cuenta proveedor'
        verbose_name_plural = 'Estadísticas cuenta proveedor'
        constraints = [
            models.UniqueConstraint(
                fields=['proveedor', 'cuenta', 'empresa'],
                name='unique_proveedor_cuenta_stats',
            ),
        ]

    def __str__(self):
        scope = self.empresa.razon_social if self.empresa_id else 'Global'
        return f'{self.proveedor.rut} → {self.cuenta.codigo} ({scope}: {self.contador})'


class ImportacionRCVCompra(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='importaciones_rcv_compra')
    mes = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    nombre_archivo = models.CharField(max_length=255, blank=True, default='')
    total_filas = models.PositiveIntegerField(default=0)
    filas_nuevas = models.PositiveIntegerField(default=0)
    filas_duplicadas = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Importación RCV compras'
        verbose_name_plural = 'Importaciones RCV compras'
        ordering = ['-ano', '-mes', '-id']

    def __str__(self):
        return f'RCV {self.mes:02d}/{self.ano} — {self.empresa.razon_social}'

    @property
    def pendientes(self):
        return self.documentos.filter(
            Q(estado='pendiente') | Q(estado='contabilizada', asiento__isnull=True)
        ).count()

    @property
    def contabilizados(self):
        return self.documentos.filter(estado='contabilizada', asiento__isnull=False).count()


class DocumentoCompraRCV(models.Model):
    ESTADO_CHOICES = (
        ('pendiente', 'Pendiente'),
        ('contabilizada', 'Contabilizada'),
        ('omitida', 'Omitida'),
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='documentos_rcv_compra')
    importacion = models.ForeignKey(ImportacionRCVCompra, on_delete=models.CASCADE, related_name='documentos')
    proveedor = models.ForeignKey(ProveedorGlobal, on_delete=models.PROTECT, related_name='documentos_compra')
    tipo_doc = models.PositiveSmallIntegerField(verbose_name='Tipo documento')
    tipo_compra = models.CharField(max_length=50, blank=True, default='')
    folio = models.BigIntegerField()
    fecha_docto = models.DateField()
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    monto_exento = models.BigIntegerField(default=0)
    monto_neto = models.BigIntegerField(default=0)
    monto_iva_recuperable = models.BigIntegerField(default=0)
    monto_otro_impuesto = models.BigIntegerField(default=0)
    monto_total = models.BigIntegerField(default=0)
    razon_social_csv = models.CharField(max_length=255, blank=True, default='')
    cuenta_gasto = models.ForeignKey(
        CuentaContable, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='pendiente')
    asiento = models.OneToOneField(
        AsientoContable, on_delete=models.SET_NULL, null=True, blank=True, related_name='documento_rcv_compra',
    )
    fuera_periodo = models.BooleanField(
        default=False,
        help_text='Fecha documento distinta al mes/año del archivo RCV.',
    )

    class Meta:
        verbose_name = 'Documento compra RCV'
        verbose_name_plural = 'Documentos compra RCV'
        ordering = ['fecha_docto', 'folio']
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'tipo_doc', 'folio', 'proveedor'],
                name='unique_documento_rcv_compra',
            ),
        ]

    def __str__(self):
        return f'{self.tipo_doc}-{self.folio} {self.proveedor.rut}'

    @property
    def es_nota_credito(self):
        return self.tipo_doc == 61

    @property
    def monto_gasto(self):
        return self.monto_exento + self.monto_neto
