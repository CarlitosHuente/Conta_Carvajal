# Cargas familiares, préstamos, vacaciones, finiquitos, licencias y cotizaciones empleador.

from django.db import migrations, models
import django.db.models.deletion


def backfill_prestamo_cuotas(apps, schema_editor):
    Prestamo = apps.get_model('rrhh', 'Prestamo')
    for p in Prestamo.objects.all():
        if p.numero_cuotas > 0:
            p.monto_cuota = round(p.monto_total / p.numero_cuotas)
            p.save(update_fields=['monto_cuota'])


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0008_liquidacion_sueldo_minimo_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacion',
            name='cotizacion_afc_empleador',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='liquidacion',
            name='cotizacion_sis_empleador',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='liquidacion',
            name='total_asignacion_familiar',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='novedadmensual',
            name='folio_licencia',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Folio licencia'),
        ),
        migrations.AddField(
            model_name='novedadmensual',
            name='tipo_licencia',
            field=models.CharField(
                choices=[
                    ('NINGUNA', 'Sin licencia'),
                    ('COMUN', 'Licencia común'),
                    ('MEDICA', 'Licencia médica'),
                    ('MATERNAL', 'Licencia maternal/paternal'),
                ],
                default='NINGUNA',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='prestamo',
            name='descripcion',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='prestamo',
            name='monto_cuota',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.AlterField(
            model_name='prestamo',
            name='contrato',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='prestamos',
                to='rrhh.contrato',
            ),
        ),
        migrations.CreateModel(
            name='CargaFamiliar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=150)),
                ('rut', models.CharField(blank=True, default='', max_length=12)),
                (
                    'tipo_carga',
                    models.CharField(
                        choices=[
                            ('NORMAL', 'Carga normal'),
                            ('INVALIDEZ', 'Carga invalidez'),
                            ('MATERNAL', 'Carga maternal'),
                        ],
                        default='NORMAL',
                        max_length=10,
                    ),
                ),
                ('activa', models.BooleanField(default=True)),
                (
                    'trabajador',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cargas_familiares',
                        to='rrhh.trabajador',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Carga familiar',
                'verbose_name_plural': 'Cargas familiares',
            },
        ),
        migrations.CreateModel(
            name='CuotaPrestamoLiquidacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.PositiveIntegerField()),
                (
                    'liquidacion',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuota_prestamo',
                        to='rrhh.liquidacion',
                    ),
                ),
                (
                    'prestamo',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cuotas_liquidadas',
                        to='rrhh.prestamo',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='Finiquito',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_termino', models.DateField()),
                (
                    'motivo',
                    models.CharField(
                        choices=[
                            ('RENUNCIA', 'Renuncia voluntaria'),
                            ('DESPIDO', 'Despido (necesidades de la empresa)'),
                            ('MUTUO_ACUERDO', 'Mutuo acuerdo'),
                            ('VENCIMIENTO', 'Vencimiento de plazo'),
                        ],
                        max_length=20,
                    ),
                ),
                ('dias_vacaciones_pendientes', models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ('monto_vacaciones', models.PositiveIntegerField(default=0)),
                ('monto_indemnizacion', models.PositiveIntegerField(default=0)),
                ('monto_ultimo_sueldo', models.PositiveIntegerField(default=0, help_text='Sueldo proporcional u otros haberes del cierre')),
                ('total_bruto_finiquito', models.PositiveIntegerField(default=0)),
                ('observaciones', models.TextField(blank=True, default='')),
                ('fecha_emision', models.DateField(auto_now_add=True)),
                (
                    'contrato',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='finiquitos',
                        to='rrhh.contrato',
                    ),
                ),
            ],
            options={
                'ordering': ['-fecha_emision', '-id'],
            },
        ),
        migrations.CreateModel(
            name='MovimientoVacaciones',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField()),
                ('dias', models.DecimalField(decimal_places=2, max_digits=6)),
                (
                    'tipo',
                    models.CharField(
                        choices=[
                            ('DEVENGADO', 'Días devengados'),
                            ('GOZADO', 'Días gozados'),
                            ('AJUSTE', 'Ajuste manual'),
                        ],
                        max_length=10,
                    ),
                ),
                ('observacion', models.CharField(blank=True, default='', max_length=255)),
                (
                    'trabajador',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='movimientos_vacaciones',
                        to='rrhh.trabajador',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Movimiento de vacaciones',
                'verbose_name_plural': 'Movimientos de vacaciones',
                'ordering': ['-fecha', '-id'],
            },
        ),
        migrations.RunPython(backfill_prestamo_cuotas, migrations.RunPython.noop),
    ]
