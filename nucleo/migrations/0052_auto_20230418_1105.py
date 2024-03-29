# Generated by Django 3.2.18 on 2023-04-18 11:05

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0051_auto_20230412_1505'),
    ]

    operations = [
        migrations.AlterField(
            model_name='producao',
            name='doi',
            field=models.CharField(blank=True, db_index=True, max_length=200, null=True, verbose_name='DOI'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='isbn',
            field=models.CharField(blank=True, db_index=True, max_length=13, null=True, verbose_name='ISBN'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='tipo',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.tipoproducao', verbose_name='Tipo de Produção'),
        ),
        migrations.AlterField(
            model_name='relatorioanual',
            name='aprovado',
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
