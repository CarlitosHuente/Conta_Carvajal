from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0004_asientocontable_cuentacontable_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='asientocontable',
            name='origen_rrhh_ano',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Año origen RR.HH.'),
        ),
        migrations.AddField(
            model_name='asientocontable',
            name='origen_rrhh_mes',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Mes origen RR.HH.'),
        ),
        migrations.AddConstraint(
            model_name='asientocontable',
            constraint=models.UniqueConstraint(
                condition=models.Q(('origen_rrhh_ano__isnull', False), ('origen_rrhh_mes__isnull', False)),
                fields=('empresa', 'origen_rrhh_mes', 'origen_rrhh_ano'),
                name='unique_asiento_rrhh_periodo',
            ),
        ),
    ]
