# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rrhh', '0011_separar_cuentas_previred_sii'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_previred_por_pagar',
            field=models.ForeignKey(
                help_text='Todo lo que se declara y paga en Previred: AFP, salud, cesantía, SIS y AFC empleador.',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='contabilidad.cuentacontable',
                verbose_name='Previred por pagar',
            ),
        ),
        migrations.RemoveField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_afc_empleador_por_pagar',
        ),
        migrations.RemoveField(
            model_name='configuracioncentralizacionrrhh',
            name='cuenta_sis_por_pagar',
        ),
    ]
