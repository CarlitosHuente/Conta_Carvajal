# Generated manually for UF plan precision (e.g. 3.357)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0005_contrato_conceptos_variables'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contrato',
            name='plan_salud_pactado',
            field=models.DecimalField(
                decimal_places=3,
                default=0,
                help_text='Monto del plan (CLP o UF); hasta 3 decimales en UF (ej. 3,357)',
                max_digits=12,
            ),
        ),
    ]
