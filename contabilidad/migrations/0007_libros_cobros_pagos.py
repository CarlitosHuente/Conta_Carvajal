from django.db import migrations, models
import django.db.models.deletion


def asignar_subtipos_plan_base(apps, schema_editor):
  CuentaContable = apps.get_model('contabilidad', 'CuentaContable')
  mapa = {
      '1.01.01': 'caja',
      '1.01.02': 'banco',
      '1.01.03': 'clientes',
      '2.01.01': 'proveedores',
  }
  for codigo, subtipo in mapa.items():
      CuentaContable.objects.filter(codigo=codigo).update(subtipo_operacion=subtipo)


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0006_asiento_origen_plantilla'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuentacontable',
            name='subtipo_operacion',
            field=models.CharField(
                blank=True,
                choices=[
                    ('general', 'General'),
                    ('caja', 'Caja / Efectivo'),
                    ('banco', 'Banco'),
                    ('clientes', 'Clientes'),
                    ('proveedores', 'Proveedores'),
                ],
                default='general',
                max_length=20,
                verbose_name='Subtipo operativo',
            ),
        ),
        migrations.AddField(
            model_name='asientocontable',
            name='tipo_asiento',
            field=models.CharField(
                choices=[
                    ('manual', 'Comprobante manual'),
                    ('f29', 'Centralización F29'),
                    ('rrhh', 'Remuneraciones'),
                    ('pago', 'Pago a proveedores'),
                    ('cobro', 'Cobro a clientes'),
                ],
                default='manual',
                max_length=20,
                verbose_name='Tipo de asiento',
            ),
        ),
        migrations.CreateModel(
            name='AplicacionCobroPago',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.BigIntegerField(verbose_name='Monto aplicado')),
                ('tipo', models.CharField(choices=[('pago', 'Pago'), ('cobro', 'Cobro')], max_length=10)),
                ('asiento_pago', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aplicaciones', to='contabilidad.asientocontable')),
                ('linea_origen', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='aplicaciones_salida', to='contabilidad.lineaasiento')),
            ],
            options={
                'verbose_name': 'Aplicación cobro/pago',
                'verbose_name_plural': 'Aplicaciones cobro/pago',
            },
        ),
        migrations.RunPython(asignar_subtipos_plan_base, migrations.RunPython.noop),
    ]
