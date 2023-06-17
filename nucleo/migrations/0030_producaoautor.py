# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-09-14 15:59
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0029_auto_20200426_0833'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProducaoAutor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ordem', models.SmallIntegerField(default=0)),
                ('autor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='nucleo.Pesquisador')),
                ('producao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='nucleo.Producao')),
            ],
            options={
                'verbose_name': 'Autor',
                'verbose_name_plural': 'Autores',
            },
        ),
    ]
