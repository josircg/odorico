# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-12-09 22:54
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AreaConhecimento',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, verbose_name='Nome')),
                ('cod_capes', models.CharField(max_length=40, verbose_name='Cód.Capes')),
            ],
            options={
                'verbose_name': 'Área de Conhecimento',
                'verbose_name_plural': 'Áreas de Conhecimento',
            },
        ),
        migrations.AlterModelOptions(
            name='area',
            options={'verbose_name': 'Área de Avaliação', 'verbose_name_plural': 'Áreas de Avaliação'},
        ),
        migrations.AlterModelOptions(
            name='grandearea',
            options={'ordering': ('nome',), 'verbose_name': 'Grande Área', 'verbose_name_plural': 'Grandes Áreas'},
        ),
        migrations.AddField(
            model_name='periodico',
            name='qualis',
            field=models.CharField(default='ND', max_length=2),
        ),
        migrations.AddField(
            model_name='periodico',
            name='sistema',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='area',
            name='cod_capes',
            field=models.CharField(max_length=40, verbose_name='Cód.Capes'),
        ),
        migrations.AlterField(
            model_name='periodico',
            name='status',
            field=models.CharField(choices=[('A', 'Ativa'), ('F', 'Inativa')], default='A', max_length=1),
        ),
        migrations.AlterField(
            model_name='periodicoarea',
            name='area',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='qualis.AreaConhecimento'),
        ),
        migrations.AddField(
            model_name='areaconhecimento',
            name='area_avaliacao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='qualis.Area'),
        ),
        migrations.AddField(
            model_name='periodico',
            name='area',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='qualis.AreaConhecimento'),
        ),
    ]