from django.db import migrations, models


def marcar_descuentos_legales(apps, schema_editor):
    ItemLiquidacion = apps.get_model('rrhh', 'ItemLiquidacion')
    prefijos = (
        'afp ',
        'salud ',
        'adicional isapre',
        'seguro de cesant',
        'impuesto ',
    )
    for item in ItemLiquidacion.objects.filter(tipo='DESCUENTO').iterator():
        nombre = (item.nombre or '').lower()
        if nombre.startswith(prefijos):
            ItemLiquidacion.objects.filter(pk=item.pk).update(es_legal=True)


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0013_contrato_usa_sueldo_minimo'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacion',
            name='manual',
            field=models.BooleanField(
                default=False,
                help_text='Si está activa, el proceso masivo no reemplaza esta liquidación.',
                verbose_name='Ingresada o editada a mano',
            ),
        ),
        migrations.AddField(
            model_name='itemliquidacion',
            name='es_legal',
            field=models.BooleanField(
                default=False,
                help_text='En descuentos: legal (AFP, salud, cesantía, impuesto) u otro descuento.',
                verbose_name='Descuento legal',
            ),
        ),
        migrations.RunPython(marcar_descuentos_legales, migrations.RunPython.noop),
    ]
