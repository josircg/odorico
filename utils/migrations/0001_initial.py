# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-09-21 20:21
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='EmailAgendado',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(default='', max_length=90)),
                ('status', models.CharField(choices=[('A', 'Aguardando envio manual...'), ('S', 'Enviando...'), ('R', 'Re-enviando'), ('E', 'Erro ao enviar'), ('K', 'Enviado')], default='S', max_length=1)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('to', models.TextField()),
                ('html', models.TextField()),
            ],
            options={
                'ordering': ('-date',),
            },
        ),
    ]