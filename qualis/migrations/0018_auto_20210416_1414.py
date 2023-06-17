# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2021-04-16 14:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0017_periodico_modelo_economico'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='periodicoissn',
            options={'verbose_name': 'ISSN Alternativos'},
        ),
        migrations.RemoveField(
            model_name='periodicoissn',
            name='primario',
        ),
        migrations.AlterField(
            model_name='periodicoissn',
            name='meio',
            field=models.CharField(choices=[('L', 'Link'), ('P', 'Impresso'), ('E', 'Eletrônico'), ('O', 'Outros')], default='O', max_length=1),
        ),
    ]
