from django.db import migrations, models


def backfill_sueldo_minimo(apps, schema_editor):
    Liquidacion = apps.get_model('rrhh', 'Liquidacion')
    IndicadorEconomico = apps.get_model('rrhh', 'IndicadorEconomico')
    for liq in Liquidacion.objects.filter(sueldo_minimo_valor=0).iterator():
        indicador = (
            IndicadorEconomico.objects.filter(ano__lte=liq.ano, mes__lte=liq.mes)
            .order_by('-ano', '-mes')
            .first()
        )
        if indicador:
            Liquidacion.objects.filter(pk=liq.pk).update(
                sueldo_minimo_valor=indicador.sueldo_minimo,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0007_contrato_cargo_liquidacion_snapshots'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacion',
            name='sueldo_minimo_valor',
            field=models.PositiveIntegerField(default=0, verbose_name='Sueldo mínimo (snapshot)'),
        ),
        migrations.RunPython(backfill_sueldo_minimo, migrations.RunPython.noop),
    ]
