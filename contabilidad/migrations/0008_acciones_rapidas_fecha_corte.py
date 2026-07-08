# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0007_libros_cobros_pagos'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccionRapidaCuenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Ej: Pago, Cobro', max_length=80, verbose_name='Nombre de la acción')),
                ('tipo', models.CharField(choices=[('pago', 'Pago'), ('cobro', 'Cobro')], default='pago', max_length=10)),
                ('lado_pendiente', models.CharField(
                    choices=[('debe', 'Debe'), ('haber', 'Haber')],
                    default='haber',
                    help_text='Lado del mayor que queda por saldar (Debe o Haber).',
                    max_length=10,
                    verbose_name='Movimientos pendientes en',
                )),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('activa', models.BooleanField(default=True)),
                ('cuenta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='acciones_rapidas',
                    to='contabilidad.cuentacontable',
                )),
            ],
            options={
                'verbose_name': 'Acción rápida',
                'verbose_name_plural': 'Acciones rápidas',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LineaAccionRapida',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('accion', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lineas_contrapartida',
                    to='contabilidad.accionrapidacuenta',
                )),
                ('cuenta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='contabilidad.cuentacontable',
                )),
            ],
            options={
                'verbose_name': 'Contrapartida de acción rápida',
                'verbose_name_plural': 'Contrapartidas de acción rápida',
                'ordering': ['orden', 'id'],
            },
        ),
    ]
