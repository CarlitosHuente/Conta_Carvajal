from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0005_asiento_origen_rrhh'),
    ]

    operations = [
        migrations.AddField(
            model_name='asientocontable',
            name='origen_plantilla',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='asientos_generados',
                to='contabilidad.plantillacentralizacion',
                verbose_name='Plantilla de centralización',
            ),
        ),
        migrations.AddConstraint(
            model_name='asientocontable',
            constraint=models.UniqueConstraint(
                condition=models.Q(origen_f29__isnull=False, origen_plantilla__isnull=False),
                fields=('origen_f29', 'origen_plantilla'),
                name='unique_asiento_f29_plantilla',
            ),
        ),
    ]
