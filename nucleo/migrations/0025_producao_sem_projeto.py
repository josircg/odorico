# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-01-13 09:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0024_projetopesquisa_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='producao',
            name='sem_projeto',
            field=models.BooleanField(default=False, verbose_name='Produção externa ao Programa'),
        ),
    ]
