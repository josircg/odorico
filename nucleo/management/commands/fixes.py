import os

from django.core.management.base import BaseCommand
from django.db import connection
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType

from nucleo.apps import obtem_dt_cnpq
from nucleo.models import *


# from nucleo import clean_doi_url
# from nucleo.apps import generate_hash, normalize_name, parse_titulo


# Corrige o atributo orientacao.matricula das orientações ativas
def fix_orientacao_matricula():
    count = 0
    for orientacao in Orientacao.objects.filter(matricula__isnull=True).order_by('id'):
        if orientacao.status == STATUS_ATIVO:
            dataset = Matricula.objects.filter(pesquisador=orientacao.aluno).order_by('-ingresso')
        else:
            dataset = Matricula.objects.filter(pesquisador=orientacao.aluno).order_by('ingresso')
        for matricula in dataset:
            atual = Orientacao.objects.filter(aluno=orientacao.aluno, matricula=matricula, status='A').order_by('id')
            if not atual:
                orientacao.matricula = matricula
                orientacao.save()
                count += 1
                break
    print(f'Orientações Incluídas: {count}')
    count = Orientacao.objects.filter(matricula__isnull=True).count()
    if count > 0:
        print(f'Ainda ficaram {count} orientações em aberto')


def fix_matricula_atual():
    count = 0
    for aluno in Pesquisador.objects.filter(matricula__isnull=False):
        aluno.matricula_atual = aluno.matricula_set.order_by('-ingresso').first()
        aluno.save()
        count += 1
    print(f'Alunos atualizados: {count}')

from escola.models import Contato

def fix_contatos():
    with connection.cursor() as cursor:
        cursor.execute("select escola_discente.id, count(*)  "
                       "  from escola_discente LEFT JOIN escola_contato "
                       "    ON (`escola_discente`.`id` = escola_contato.discente_id) "
                       "group by escola_discente.id having count(*) > 1")
        excluidos = 0
        for discente in cursor.fetchall():
            contato_count = 0
            for contato in Contato.objects.filter(discente=discente[0]).order_by('id'):
                contato_count += 1
                if contato_count == 1:
                    continue
                else:
                    contato.delete()
                    excluidos += 1
        print(f'Excluídos:{excluidos}')


# Exclusão de alterações no próprio LogEntry
def clean_logentry():
    type_id = ContentType.objects.get(model='logentry').id
    LogEntry.objects.filter(content_type_id=type_id).delete()

def validate_id_cnpq():
    count = 0
    atualizados = 0
    for pesquisador in Pesquisador.objects.filter(id_cnpq__isnull=False):
        if pesquisador.dtupdate and pesquisador.dtupdate.year >= 2024:
            atualizados += 1
        else:
            data = obtem_dt_cnpq(pesquisador.id_cnpq)
            if not data:
                print(pesquisador.nome)
            count += 1
    print(f'Pesquisadores lidos: {count}')
    print(f'Pesquisadores atualizados: {atualizados}')


def fix_inscricao_matricula():
    for inscricao in Inscricao.objects.all():
        if not inscricao.aluno.matricula_atual:
            print(f'Aluno sem matrícula atual {inscricao.aluno}')
        else:
            inscricao.matricula = inscricao.aluno.matricula_atual
            inscricao.save()


class Command(BaseCommand):
    label = 'DB Fixes'

    def handle(self, *args, **options):
        fix_inscricao_matricula()
        # fix_matricula_atual()
        # fix_orientacao_matricula()
        # fix_contatos()
        # update_area()
        # update_modelo()
        # validate_id_cnpq()

    # Corrige produções sem autor original
    def handle_semautor(self, *args, **options):
        count = 0
        for producao in Producao.objects.all():
            if producao.producaoautor_set.filter(autor=producao.pesquisador).count() == 0:
                ProducaoAutor.objects.get_or_create(producao=producao, autor=producao.pesquisador)
                count += 1
        print(f'Autores Incluídos: {count}')

        count = 0
        tipo = TipoProducao.objects.get(cod_externo='TrabalhosTecnicos')
        tipo_correto = TipoProducao.objects.get(cod_externo='ApresentacoesTrabalho')
        for producao in Producao.objects.filter(tipo=tipo):
            if Producao.objects.filter(ident_unico=producao.ident_unico, tipo=tipo_correto).count() > 0:
                producao.producaoautor_set.all().delete()
                producao.delete()
            count += 1
        print(f'Produções excluídas: {count}')

        '''
        # Limpeza da Produção de Artigos
        for rec in Producao.objects.filter(ident_unico__isnull=True).select_related('pesquisador'):
        # for rec in Producao.objects.filter(id=20411).select_related('pesquisador'):
            if rec.doi:
                rec.doi = clean_doi_url(rec.doi)
                rec.save()

            if not rec.pesquisador.nome.split(' ')[-1] in rec.titulo.upper():
                continue

            if not rec.descricao:
                rec.descricao = rec.titulo

            prev = parse_titulo(rec.titulo)

            if prev:
                rec.titulo = prev
                rec.ident_unico = generate_hash(prev)
            rec.save()

        # Popular PeriodicoISSN
        for p in Periodico.objects.all():
            if p.issn:
                PeriodicoISSN.objects.get_or_create(periodico=p.periodico, issn=p.issn)
            if p.eissn:
                PeriodicoISSN.objects.get_or_create(periodico=p.periodico, issn=p.eissn)
        Producao.objects.filter(projeto__isnull=True, ano__lt=2017).delete()
        '''

    # Corrige o status de conclusão do curso dos alunos
    def handle_status_conclusao(self, *args, **options):
        tot_reg = 0
        loguser = User.objects.get_or_create(username='sys')[0]
        type_id = ContentType.objects.get(model='aluno').id
        for matricula in Matricula.objects.filter(status='C',pesquisador__nome__contains='JOBSON'):
            # verifica se existe alguma outra matrícula ativa
            ativas = Matricula.objects.filter(pesquisador=matricula.pesquisador, status='A').count()
            if ativas == 0:
                for orientacao in Orientacao.objects.filter(aluno__id=matricula.pesquisador.id, status='A'):
                    orientacao.status = STATUS_CONCLUIDA
                    orientacao.save()
                    LogEntry.objects.log_action(
                        user_id=loguser.id,
                        content_type_id=type_id,
                        object_id=matricula.pesquisador.id,
                        object_repr=u"%s" % matricula,
                        action_flag=ADDITION,
                        change_message='Orientação concluída'
                    )
                    tot_reg += 1
        print('Registros alterados: %d' % tot_reg)

        for projeto in ProjetoPesquisa.objects.all():
            PesquisadorProjeto.objects.get_or_create(projeto=projeto, pesquisador=projeto.proponente)
