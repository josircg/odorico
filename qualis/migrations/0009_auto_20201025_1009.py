# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-10-25 10:09
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0008_periodico_pais'),
    ]

    operations = [
        migrations.CreateModel(
            name='PeriodicoIndicador',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('classe', models.CharField(blank=True, max_length=2, null=True)),
                ('indicador', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='schema',
            name='ano_final',
            field=models.SmallIntegerField(blank=True, null=True, verbose_name='Ano Final'),
        ),
        migrations.AddField(
            model_name='schema',
            name='ano_inicial',
            field=models.SmallIntegerField(blank=True, null=True, verbose_name='Ano Inicial'),
        ),
        migrations.AlterField(
            model_name='periodico',
            name='nome',
            field=models.CharField(max_length=200, verbose_name='Nome completo'),
        ),
        migrations.AddField(
            model_name='periodicoindicador',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='qualis.Periodico'),
        ),
        migrations.AddField(
            model_name='periodicoindicador',
            name='schema',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='qualis.Schema'),
        ),
    ]
