# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-04-23 13:04
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0026_auto_20200419_1730'),
    ]

    operations = [
        migrations.AlterField(
            model_name='producao',
            name='pais',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
