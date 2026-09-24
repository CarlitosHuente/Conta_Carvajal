from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0015_finiquito_conceptos'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlantillaDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=40, unique=True)),
                ('nombre', models.CharField(max_length=120)),
                ('bloques', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'verbose_name': 'Plantilla de documento',
                'verbose_name_plural': 'Plantillas de documentos',
            },
        ),
    ]
