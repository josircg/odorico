# Generated by Django 3.2.18 on 2023-03-21 16:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0024_auto_20230321_1645'),
        ('nucleo', '0043_auto_20201118_2301'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alunolinha',
            name='aluno',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.aluno'),
        ),
        migrations.AlterField(
            model_name='alunolinha',
            name='linha',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.linhapesquisa'),
        ),
        migrations.AlterField(
            model_name='curso',
            name='programa',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.programa'),
        ),
        migrations.AlterField(
            model_name='linhapesquisa',
            name='programa',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.programa'),
        ),
        migrations.AlterField(
            model_name='matricula',
            name='curso',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.curso'),
        ),
        migrations.AlterField(
            model_name='matricula',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='orientacao',
            name='aluno',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='aluno', to='nucleo.aluno'),
        ),
        migrations.AlterField(
            model_name='orientacao',
            name='coorientacao',
            field=models.BooleanField(default=False, verbose_name='Coorientação'),
        ),
        migrations.AlterField(
            model_name='orientacao',
            name='matricula',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='nucleo.matricula'),
        ),
        migrations.AlterField(
            model_name='orientacao',
            name='orientador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orientador', to='nucleo.professor'),
        ),
        migrations.AlterField(
            model_name='pesquisadorfomento',
            name='fomento',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.fomento'),
        ),
        migrations.AlterField(
            model_name='pesquisadorfomento',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='pesquisadornomecitacao',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='pesquisadorprograma',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='pesquisadorprograma',
            name='programa',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.programa'),
        ),
        migrations.AlterField(
            model_name='pesquisadorprojeto',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='pesquisadorprojeto',
            name='projeto',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.projetopesquisa'),
        ),
        migrations.AlterField(
            model_name='pesquisadortitulacao',
            name='instituicao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.instituicao'),
        ),
        migrations.AlterField(
            model_name='pesquisadortitulacao',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='pesquisador',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='projeto',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='nucleo.projetopesquisa'),
        ),
        migrations.AlterField(
            model_name='producao',
            name='tipo',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.tipoproducao'),
        ),
        migrations.AlterField(
            model_name='producaoautor',
            name='autor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='nucleo.pesquisador'),
        ),
        migrations.AlterField(
            model_name='producaoautor',
            name='producao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.producao'),
        ),
        migrations.AlterField(
            model_name='professorlinha',
            name='linha',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.linhapesquisa'),
        ),
        migrations.AlterField(
            model_name='professorlinha',
            name='professor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.professor'),
        ),
        migrations.AlterField(
            model_name='programa',
            name='area',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='qualis.area'),
        ),
        migrations.AlterField(
            model_name='programa',
            name='instituicao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.instituicao'),
        ),
        migrations.AlterField(
            model_name='projetopesquisa',
            name='linha',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.linhapesquisa'),
        ),
        migrations.AlterField(
            model_name='projetopesquisa',
            name='proponente',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='nucleo.professor'),
        ),
    ]