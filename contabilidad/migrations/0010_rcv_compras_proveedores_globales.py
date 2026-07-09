# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0003_empresa_contabilidad_completa'),
        ('contabilidad', '0009_acciones_rapidas_independientes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asientocontable',
            name='tipo_asiento',
            field=models.CharField(
                choices=[
                    ('manual', 'Comprobante manual'),
                    ('f29', 'Centralización F29'),
                    ('rcv', 'Compra RCV'),
                    ('rrhh', 'Remuneraciones'),
                    ('pago', 'Pago a proveedores'),
                    ('cobro', 'Cobro a clientes'),
                ],
                default='manual',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='plantillacentralizacion',
            name='tipo_origen',
            field=models.CharField(
                choices=[
                    ('f29', 'Formulario 29 (Simplificada)'),
                    ('rcv', 'Registro de Compra y Ventas'),
                ],
                default='f29',
                max_length=10,
            ),
        ),
        migrations.CreateModel(
            name='ProveedorGlobal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rut', models.CharField(max_length=12, unique=True, verbose_name='RUT')),
                ('razon_social', models.CharField(max_length=255)),
                ('razon_social_sii', models.CharField(blank=True, default='', max_length=255)),
                ('rubro', models.CharField(blank=True, choices=[('', 'Sin clasificar'), ('farmacia', 'Farmacia / droguería'), ('insumos_medicos', 'Insumos médicos'), ('servicios', 'Servicios'), ('tecnologia', 'Tecnología'), ('otro', 'Otro')], default='', max_length=30)),
                ('notas', models.TextField(blank=True, default='')),
                ('activo', models.BooleanField(default=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('actualizado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Proveedor global',
                'verbose_name_plural': 'Proveedores globales',
                'ordering': ['razon_social'],
            },
        ),
        migrations.CreateModel(
            name='ImportacionRCVCompra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mes', models.PositiveSmallIntegerField()),
                ('ano', models.PositiveSmallIntegerField()),
                ('nombre_archivo', models.CharField(blank=True, default='', max_length=255)),
                ('total_filas', models.PositiveIntegerField(default=0)),
                ('filas_nuevas', models.PositiveIntegerField(default=0)),
                ('filas_duplicadas', models.PositiveIntegerField(default=0)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='importaciones_rcv_compra', to='core.empresa')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Importación RCV compras',
                'verbose_name_plural': 'Importaciones RCV compras',
                'ordering': ['-ano', '-mes', '-id'],
            },
        ),
        migrations.AddField(
            model_name='asientocontable',
            name='origen_importacion_rcv',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asientos_generados', to='contabilidad.importacionrcvcompra', verbose_name='Importación RCV origen'),
        ),
        migrations.CreateModel(
            name='EmpresaProveedor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('veces_contabilizado', models.PositiveIntegerField(default=0)),
                ('primera_compra', models.DateField(blank=True, null=True)),
                ('ultima_compra', models.DateField(blank=True, null=True)),
                ('cuenta_gasto_habitual', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='contabilidad.cuentacontable')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proveedores_vinculados', to='core.empresa')),
                ('proveedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vinculos_empresa', to='contabilidad.proveedorglobal')),
            ],
            options={
                'verbose_name': 'Proveedor por empresa',
                'verbose_name_plural': 'Proveedores por empresa',
            },
        ),
        migrations.CreateModel(
            name='DocumentoCompraRCV',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_doc', models.PositiveSmallIntegerField(verbose_name='Tipo documento')),
                ('tipo_compra', models.CharField(blank=True, default='', max_length=50)),
                ('folio', models.BigIntegerField()),
                ('fecha_docto', models.DateField()),
                ('fecha_recepcion', models.DateTimeField(blank=True, null=True)),
                ('monto_exento', models.BigIntegerField(default=0)),
                ('monto_neto', models.BigIntegerField(default=0)),
                ('monto_iva_recuperable', models.BigIntegerField(default=0)),
                ('monto_otro_impuesto', models.BigIntegerField(default=0)),
                ('monto_total', models.BigIntegerField(default=0)),
                ('razon_social_csv', models.CharField(blank=True, default='', max_length=255)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('contabilizada', 'Contabilizada'), ('omitida', 'Omitida')], default='pendiente', max_length=15)),
                ('fuera_periodo', models.BooleanField(default=False, help_text='Fecha documento distinta al mes/año del archivo RCV.')),
                ('asiento', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='documento_rcv_compra', to='contabilidad.asientocontable')),
                ('cuenta_gasto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='contabilidad.cuentacontable')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentos_rcv_compra', to='core.empresa')),
                ('importacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documentos', to='contabilidad.importacionrcvcompra')),
                ('proveedor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='documentos_compra', to='contabilidad.proveedorglobal')),
            ],
            options={
                'verbose_name': 'Documento compra RCV',
                'verbose_name_plural': 'Documentos compra RCV',
                'ordering': ['fecha_docto', 'folio'],
            },
        ),
        migrations.CreateModel(
            name='ProveedorCuentaStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contador', models.PositiveIntegerField(default=0)),
                ('cuenta', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='contabilidad.cuentacontable')),
                ('empresa', models.ForeignKey(blank=True, help_text='Vacío = estadística global del estudio (todas las empresas).', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='core.empresa')),
                ('proveedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stats_cuentas', to='contabilidad.proveedorglobal')),
            ],
            options={
                'verbose_name': 'Estadística cuenta proveedor',
                'verbose_name_plural': 'Estadísticas cuenta proveedor',
            },
        ),
        migrations.AddConstraint(
            model_name='empresaproveedor',
            constraint=models.UniqueConstraint(fields=('empresa', 'proveedor'), name='unique_empresa_proveedor'),
        ),
        migrations.AddConstraint(
            model_name='documentocomprarcv',
            constraint=models.UniqueConstraint(fields=('empresa', 'tipo_doc', 'folio', 'proveedor'), name='unique_documento_rcv_compra'),
        ),
        migrations.AddConstraint(
            model_name='proveedorcuentastats',
            constraint=models.UniqueConstraint(fields=('proveedor', 'cuenta', 'empresa'), name='unique_proveedor_cuenta_stats'),
        ),
    ]
