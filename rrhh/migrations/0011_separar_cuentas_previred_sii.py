# Generated manually

from django.db import migrations, models
import django.db.models.deletion


def poblar_cuentas_nuevas(apps, schema_editor):
    Config = apps.get_model('rrhh', 'ConfiguracionCentralizacionRRHH')
    CuentaContable = apps.get_model('contabilidad', 'CuentaContable')

    for config in Config.objects.select_related('empresa', 'cuenta_previred_por_pagar').all():
        empresa = config.empresa
        cuenta_iu, _ = CuentaContable.objects.get_or_create(
            empresa=empresa,
            codigo='2.02.05',
            defaults={'nombre': 'Impuesto Único por Pagar (SII)', 'tipo': 'pasivo'},
        )
        cuenta_otros, _ = CuentaContable.objects.get_or_create(
            empresa=empresa,
            codigo='2.02.06',
            defaults={'nombre': 'Otros Descuentos al Personal', 'tipo': 'pasivo'},
        )
        config.cuenta_impuesto_unico_por_pagar = cuenta_iu
        config.cuenta_otros_descuentos = cuenta_otros
        config.save(update_fields=['cuenta_impuesto_unico_por_pagar', 'cuenta_otros_descuentos'])


class Migration(migrations.Migration):

    dependencies = [
        ('contabilidad', '0009_acciones_rapidas_independientes'),
        ('rrhh', '0010_configuracion_centralizacion_rrhh'),
    ]

    operations = [
        migrations.RenameField(
            model_name='configuracioncentralizacionrrhh',
            old_name='cuenta_cotizaciones_por_pagar',
            new_name='cuenta_previred_por_pagar',
        ),
        migrations.AlterField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_previred_por_pagar',
            field=models.ForeignKey(
                help_text='AFP, salud y seguro de cesantía del trabajador.',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Cotizaciones Previred por pagar',
            ),
        ),
        migrations.AddField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_impuesto_unico_por_pagar',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Impuesto único por pagar (SII)',
            ),
        ),
        migrations.AddField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_otros_descuentos',
            field=models.ForeignKey(
                help_text='Préstamos, sindicato y descuentos varios descontados del líquido.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Otros descuentos al personal',
            ),
        ),
        migrations.RunPython(poblar_cuentas_nuevas, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_impuesto_unico_por_pagar',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Impuesto único por pagar (SII)',
            ),
        ),
        migrations.AlterField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_otros_descuentos',
            field=models.ForeignKey(
                help_text='Préstamos, sindicato y descuentos varios descontados del líquido.',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Otros descuentos al personal',
            ),
        ),
    ]
