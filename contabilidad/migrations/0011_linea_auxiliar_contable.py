from django.db import migrations, models


def marcar_cuentas_auxiliar(apps, schema_editor):
    CuentaContable = apps.get_model('contabilidad', 'CuentaContable')
    codigos = ('1.01.03', '2.01.01', '2.01.02')
    for prefijo in codigos:
        CuentaContable.objects.filter(codigo__startswith=prefijo).update(requiere_auxiliar=True)


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0010_rcv_compras_proveedores_globales'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuentacontable',
            name='requiere_auxiliar',
            field=models.BooleanField(
                default=False,
                help_text='Habilita RUT, documento y centro de costo en las líneas del mayor.',
                verbose_name='Usa auxiliar (RUT / Doc / CC)',
            ),
        ),
        migrations.AddField(
            model_name='lineaasiento',
            name='auxiliar_rut',
            field=models.CharField(blank=True, default='', max_length=12, verbose_name='RUT auxiliar'),
        ),
        migrations.AddField(
            model_name='lineaasiento',
            name='auxiliar_doc',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='N° documento'),
        ),
        migrations.AddField(
            model_name='lineaasiento',
            name='centro_costo',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Centro de costo'),
        ),
        migrations.RunPython(marcar_cuentas_auxiliar, migrations.RunPython.noop),
    ]
