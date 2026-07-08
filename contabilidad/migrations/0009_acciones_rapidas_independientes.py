# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def migrar_acciones_por_cuenta_a_plantillas(apps, schema_editor):
    AccionRapidaCuenta = apps.get_model('contabilidad', 'AccionRapidaCuenta')
    CuentaAccionRapida = apps.get_model('contabilidad', 'CuentaAccionRapida')

    for accion in AccionRapidaCuenta.objects.select_related('cuenta').all():
        if accion.cuenta_id:
            accion.empresa_id = accion.cuenta.empresa_id
            accion.save(update_fields=['empresa_id'])
            CuentaAccionRapida.objects.get_or_create(
                cuenta_id=accion.cuenta_id,
                accion_id=accion.id,
                defaults={'orden': accion.orden},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0008_acciones_rapidas_fecha_corte'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='accionrapidacuenta',
            name='empresa',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='acciones_rapidas',
                to='core.empresa',
            ),
        ),
        migrations.CreateModel(
            name='CuentaAccionRapida',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('accion', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='asignaciones_cuentas',
                    to='contabilidad.accionrapidacuenta',
                )),
                ('cuenta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='asignaciones_acciones',
                    to='contabilidad.cuentacontable',
                )),
            ],
            options={
                'verbose_name': 'Asignación acción rápida',
                'verbose_name_plural': 'Asignaciones acciones rápidas',
                'ordering': ['orden', 'id'],
                'unique_together': {('cuenta', 'accion')},
            },
        ),
        migrations.RunPython(migrar_acciones_por_cuenta_a_plantillas, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='accionrapidacuenta',
            name='cuenta',
        ),
        migrations.RemoveField(
            model_name='accionrapidacuenta',
            name='orden',
        ),
        migrations.AlterField(
            model_name='accionrapidacuenta',
            name='empresa',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='acciones_rapidas',
                to='core.empresa',
            ),
        ),
        migrations.RenameModel(
            old_name='AccionRapidaCuenta',
            new_name='AccionRapida',
        ),
    ]
