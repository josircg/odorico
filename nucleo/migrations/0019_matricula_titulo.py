# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-12-12 20:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0018_producao_projeto'),
    ]

    operations = [
        migrations.AddField(
            model_name='matricula',
            name='titulo',
            field=models.TextField(blank=True, help_text='Título atual da Tese/Dissertação', null=True, verbose_name='Título'),
        ),
    ]
