# Generated by Django 3.2.18 on 2023-03-21 16:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('qualis', '0023_auto_20230222_1002'),
    ]

    operations = [
        migrations.AlterField(
            model_name='area',
            name='grande_area',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.grandearea'),
        ),
        migrations.AlterField(
            model_name='areaconhecimento',
            name='area_avaliacao',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.area'),
        ),
        migrations.AlterField(
            model_name='assunto',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='qualis.assunto'),
        ),
        migrations.AlterField(
            model_name='assunto',
            name='schema',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.schema'),
        ),
        migrations.AlterField(
            model_name='periodico',
            name='area',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='qualis.areaconhecimento'),
        ),
        migrations.AlterField(
            model_name='periodicoarea',
            name='area',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.areaconhecimento'),
        ),
        migrations.AlterField(
            model_name='periodicoarea',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.periodico'),
        ),
        migrations.AlterField(
            model_name='periodicoassunto',
            name='assunto',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.assunto'),
        ),
        migrations.AlterField(
            model_name='periodicoassunto',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.periodico'),
        ),
        migrations.AlterField(
            model_name='periodicoindicador',
            name='area',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='qualis.assunto'),
        ),
        migrations.AlterField(
            model_name='periodicoindicador',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.periodico'),
        ),
        migrations.AlterField(
            model_name='periodicoindicador',
            name='schema',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.schema'),
        ),
        migrations.AlterField(
            model_name='periodicoissn',
            name='periodico',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='qualis.periodico'),
        ),
    ]
