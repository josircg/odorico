# Generated by Django 3.2.18 on 2023-04-12 14:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0049_auto_20230408_1144'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='relatorioanual',
            options={'verbose_name': 'Relatório de Produção', 'verbose_name_plural': 'Relatórios de Produção'},
        ),
        migrations.AddField(
            model_name='relatorioanual',
            name='sandwich_bolsa',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Bolsa'),
        ),
        migrations.AddField(
            model_name='relatorioanual',
            name='sandwich_descricao',
            field=models.CharField(blank=True, help_text='Descreva sua experiência durante o estágio sanduiche', max_length=200, null=True, verbose_name='Relato'),
        ),
        migrations.AddField(
            model_name='relatorioanual',
            name='sandwich_periodo',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Periodo'),
        ),
        migrations.AddField(
            model_name='relatorioanual',
            name='sandwich_universidade',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Universidade'),
        ),
        migrations.AlterField(
            model_name='relatorioanual',
            name='aprovado',
            field=models.BooleanField(blank=True, choices=[(True, 'Aprovar'), (False, 'Solicitar ajustes'), (None, '')], null=True),
        ),
        migrations.AlterField(
            model_name='relatorioanual',
            name='desenvolvimento',
            field=models.TextField(help_text='Descreva aqui os principais avanços de sua pesquisa de mestrado ou doutorado alcançados neste semestre. Você deve elaborar um texto substantivo de caráter acadêmico – e não meramente formal descrendo atividades realizadas. Considere a revisão bibliográfica realizada, coleta e análise de informações qualitativas e quantitativas, achados e interpretações desenvolvidas. Limite mínimo: 1000 palavras. Limite máximo: 2000 palavras.', null=True, verbose_name='Desenvolvimento da Pesquisa'),
        ),
        migrations.AlterField(
            model_name='relatorioanual',
            name='status',
            field=models.CharField(choices=[('I', 'Não iniciado'), ('E', 'Em edição'), ('C', 'Cadastro Ok'), ('R', 'Resumo Ok'), ('V', 'Validado'), ('A', 'Avaliado')], default='I', max_length=1),
        ),
    ]