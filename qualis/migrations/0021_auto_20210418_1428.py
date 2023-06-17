# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2021-04-18 14:28
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0020_auto_20210417_0648'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='periodicoissn',
            options={'verbose_name': 'ISSN Index'},
        ),
        migrations.AddField(
            model_name='periodico',
            name='editora',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
