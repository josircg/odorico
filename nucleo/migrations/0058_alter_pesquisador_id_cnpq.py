from django.db import connection, migrations, models
from django.db.models import Count


def remove_duplicate(apps, schema_editor):
    pesquisador = apps.get_model("nucleo", "Pesquisador")
    producao = apps.get_model("nucleo", "Producao")
    autor = apps.get_model("nucleo", "ProducaoAutor")
    matricula = apps.get_model("nucleo", "Matricula")
    orientacao = apps.get_model("nucleo", "Orientacao")
    projeto = apps.get_model("nucleo", "PesquisadorProjeto")

    db = connection.cursor()
    db.execute(
        'select id_cnpq,count(*) from nucleo_pesquisador '
        ' where id_cnpq is not null group by id_cnpq having count(*) > 1')

    print()
    tot_records = 0
    for record in db.fetchall():
        target = None
        id_cnpq = record[0]
        for duplic in pesquisador.objects.filter(id_cnpq=id_cnpq).order_by('-sexo'):
            if not target:
                target = duplic.id
            else:
                print(duplic.id, '->', target)
                producao.objects.filter(pesquisador_id=duplic.id).update(pesquisador_id=target)
                autor.objects.filter(autor_id=duplic.id).update(autor_id=target)
                orientacao.objects.filter(aluno_id=duplic.id).update(aluno_id=target)
                matricula.objects.filter(pesquisador_id=duplic.id).update(pesquisador_id=target)
                projeto.objects.filter(pesquisador_id=duplic.id).update(pesquisador_id=target)
                duplic.delete()
                tot_records += 1
    print(f'{tot_records} merged')


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0057_producao_titulo_original'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pesquisador',
            name='id_cnpq',
            field=models.CharField(blank=True, max_length=16, null=True, unique=True, verbose_name='ID CNPQ'),
        ),
    ]
