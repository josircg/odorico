# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-10-26 18:05
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0037_auto_20201026_0102'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='producao',
            name='titulo_artigo',
        ),
        migrations.AddField(
            model_name='producao',
            name='descricao',
            field=models.TextField(blank=True, null=True, verbose_name='Descrição Completa'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='titulo',
            field=models.TextField(verbose_name='Título'),
        ),
    ]
