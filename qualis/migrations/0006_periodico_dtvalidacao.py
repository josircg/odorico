# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-10-20 23:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0005_auto_20191212_1706'),
    ]

    operations = [
        migrations.AddField(
            model_name='periodico',
            name='dtvalidacao',
            field=models.DateField(blank=True, null=True),
        ),
    ]
