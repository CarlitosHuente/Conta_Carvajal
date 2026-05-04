# Cargo en contrato; snapshot fecha ingreso y cargo en liquidación; backfill seguro.

from django.db import migrations, models


def backfill_liquidacion_snapshots(apps, schema_editor):
    Liquidacion = apps.get_model('rrhh', 'Liquidacion')
    for liq in Liquidacion.objects.select_related('contrato').iterator():
        c = liq.contrato
        if not c:
            continue
        cargo = (getattr(c, 'cargo', '') or '')[:120]
        Liquidacion.objects.filter(pk=liq.pk).update(
            fecha_ingreso_contrato=c.fecha_inicio,
            cargo_contrato=cargo,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0006_alter_contrato_plan_salud_pactado'),
    ]

    operations = [
        migrations.AddField(
            model_name='contrato',
            name='cargo',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Cargo'),
        ),
        migrations.AddField(
            model_name='liquidacion',
            name='cargo_contrato',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='Cargo (snapshot)'),
        ),
        migrations.AddField(
            model_name='liquidacion',
            name='fecha_ingreso_contrato',
            field=models.DateField(
                blank=True,
                null=True,
                help_text='Fecha de inicio del contrato al momento de generar la liquidación.',
                verbose_name='Fecha ingreso contrato (snapshot)',
            ),
        ),
        migrations.RunPython(backfill_liquidacion_snapshots, migrations.RunPython.noop),
    ]
