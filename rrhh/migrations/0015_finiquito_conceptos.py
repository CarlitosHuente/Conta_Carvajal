from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0014_liquidacion_manual_item_es_legal'),
    ]

    operations = [
        migrations.AddField(
            model_name='finiquito',
            name='conceptos',
            field=models.JSONField(blank=True, default=list, help_text='Líneas editables del finiquito: nombre y monto.'),
        ),
    ]
