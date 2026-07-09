from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_permisoaccesousuario'),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='contabilidad_completa',
            field=models.BooleanField(
                default=True,
                help_text='Muestra el módulo de compras RCV. Desactívalo para usar solo F29 simplificado.',
                verbose_name='Contabilidad completa (RCV)',
            ),
        ),
    ]
