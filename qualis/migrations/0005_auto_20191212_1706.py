# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-12-12 20:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0004_auto_20191209_2322'),
    ]

    operations = [
        migrations.AddField(
            model_name='periodico',
            name='eissn',
            field=models.CharField(blank=True, db_index=True, max_length=9, null=True, verbose_name='E-ISSN'),
        ),
        migrations.AlterField(
            model_name='periodico',
            name='qualis',
            field=models.CharField(choices=[('A1', 'A1'), ('A2', 'A2'), ('A3', 'A3'), ('A4', 'A4'), ('B1', 'B1'), ('B2', 'B2'), ('B3', 'B3'), ('B4', 'B4'), ('C', 'C'), ('ND', 'ND')], default='ND', max_length=2),
        ),
    ]
