# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-11-17 16:42
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0041_auto_20201107_0905'),
    ]

    operations = [
        migrations.AlterField(
            model_name='projetopesquisa',
            name='nome',
            field=models.CharField(max_length=400),
        ),
    ]
