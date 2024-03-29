# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-09-28 22:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0007_auto_20190819_1512'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pesquisador',
            name='ano',
        ),
        migrations.AddField(
            model_name='matricula',
            name='dtconclusao',
            field=models.DateField(blank=True, null=True, verbose_name='Dt.Conclusão'),
        ),
        migrations.AddField(
            model_name='pesquisador',
            name='CPF',
            field=models.CharField(blank=True, max_length=11, null=True),
        ),
        migrations.AlterField(
            model_name='pesquisador',
            name='sexo',
            field=models.CharField(choices=[('M', 'Masculino'), ('F', 'Feminino')], max_length=1, null=True),
        ),
    ]
