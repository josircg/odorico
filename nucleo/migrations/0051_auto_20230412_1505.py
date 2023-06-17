# Generated by Django 3.2.18 on 2023-04-12 15:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0050_auto_20230412_1421'),
    ]

    operations = [
        migrations.AddField(
            model_name='producao',
            name='cidade',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='producao',
            name='editora',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='producao',
            name='meio',
            field=models.CharField(blank=True, choices=[('I', 'Impresso'), ('M', 'Mídia Magnética (fita, disquete, etc.)'), ('D', 'Mídia Digital (CD, DVD, Bluray, USB, etc.)'), ('F', 'Filme (inclusive online)'), ('H', 'Hipertexto(Website, blog etc.)'), ('O', 'Outro')], max_length=1, null=True, verbose_name='Meio de Divulgação'),
        ),
        migrations.AddField(
            model_name='producao',
            name='natureza_obra',
            field=models.CharField(blank=True, choices=[('O', 'Obra Única'), ('C', 'Coleção'), ('L', 'Coletânea'), ('D', 'Dicionário'), ('E', 'Enciclopédia')], max_length=1, null=True, verbose_name='Natureza da obra'),
        ),
        migrations.AddField(
            model_name='producao',
            name='organizacao',
            field=models.TextField(blank=True, null=True, verbose_name='Editores/Coordenação/Organização'),
        ),
        migrations.AddField(
            model_name='producao',
            name='tipo_obra',
            field=models.CharField(blank=True, choices=[('C', 'Capítulo'), ('V', 'Verbete'), ('A', 'Apresentação'), ('I', 'Introdução'), ('P', 'Prefacio'), ('O', 'Posfácio'), ('L', 'Obra completa(Livro)'), ('T', 'Trabalho Completo'), ('R', 'Resumo'), ('X', 'Resumo Expandido')], max_length=1, null=True, verbose_name='Tipo da Obra'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='validacao',
            field=models.CharField(choices=[('A', 'Em aberto'), ('I', 'Importado'), ('E', 'Editado'), ('V', 'Validado')], default='A', max_length=1, verbose_name='Validação'),
        ),
    ]
