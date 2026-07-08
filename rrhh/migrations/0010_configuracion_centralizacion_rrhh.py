# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0009_acciones_rapidas_independientes'),
        ('core', '0001_initial'),
        ('rrhh', '0009_rrhh_mejoras_operativas'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionCentralizacionRRHH',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cuenta_afc_empleador_por_pagar', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='contabilidad.cuentacontable',
                    verbose_name='AFC empleador por pagar',
                )),
                ('cuenta_cotizaciones_por_pagar', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='contabilidad.cuentacontable',
                    verbose_name='Cotizaciones previsionales por pagar',
                )),
                ('cuenta_gasto', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='contabilidad.cuentacontable',
                    verbose_name='Gasto remuneraciones',
                )),
                ('cuenta_sis_por_pagar', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='contabilidad.cuentacontable',
                    verbose_name='SIS empleador por pagar',
                )),
                ('cuenta_sueldos_por_pagar', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='+',
                    to='contabilidad.cuentacontable',
                    verbose_name='Sueldos por pagar',
                )),
                ('empresa', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='config_centralizacion_rrhh',
                    to='core.empresa',
                )),
            ],
            options={
                'verbose_name': 'Configuración centralización RR.HH.',
                'verbose_name_plural': 'Configuraciones centralización RR.HH.',
            },
        ),
    ]
