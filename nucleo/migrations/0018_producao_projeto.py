# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-12-09 23:26
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0017_auto_20191209_0955'),
    ]

    operations = [
        migrations.AddField(
            model_name='producao',
            name='projeto',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='nucleo.ProjetoPesquisa'),
        ),
    ]
