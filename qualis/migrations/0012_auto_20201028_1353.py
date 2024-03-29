# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2020-10-28 13:53
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0011_periodicoindicador_area'),
    ]

    operations = [
        migrations.CreateModel(
            name='PeriodicoISSN',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('issn', models.CharField(db_index=True, max_length=9, verbose_name='ISSN')),
                ('primario', models.BooleanField(default=False)),
                ('meio', models.CharField(choices=[('P', 'Impresso'), ('E', 'Eletrônico'), ('O', 'Outros')], max_length=1)),
            ],
            options={
                'verbose_name': 'Periódico ISSN',
            },
        ),
        migrations.AlterField(
            model_name='periodico',
            name='eissn',
            field=models.CharField(blank=True, db_index=True, max_length=9, null=True, verbose_name='Alt.ISSN'),
        ),
        migrations.AlterField(
            model_name='periodico',
            name='issn',
            field=models.CharField(blank=True, db_index=True, max_length=9, null=True, verbose_name='ISSN-L'),
        ),
        migrations.AddField(
            model_name='periodicoissn',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='qualis.Periodico'),
        ),
    ]
