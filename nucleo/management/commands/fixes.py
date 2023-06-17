from django.core.management.base import BaseCommand
from django.db.models import Count, Exists, OuterRef
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType

from nucleo.models import *
from qualis.models import *
from nucleo import clean_doi_url
from nucleo.apps import generate_hash, normalize_name, parse_titulo


class Command(BaseCommand):
    label = 'DB Fixes'

    def handle(self, *args, **options):

        # Popular PeriodicosISSN para facilitar a busca
        tot_excluido = 0
        for rec in Periodico.objects.all():
            master = Periodico.objects.filter(eissn=rec.issn).exclude(id=rec.id).first()
            if master:
                rec.delete()
                tot_excluido += 1
        print('Excluidos: %d' % tot_excluido)


        '''
        # Exclusão dos registros que foram gravados a partir do E-ISSN e não pelo ISSN-L
        tot_excluido = 0
        for rec in Periodico.objects.all():
            master = Periodico.objects.filter(eissn=rec.issn).exclude(id=rec.id).first()
            if master:
                rec.delete()
                tot_excluido += 1
        print('Excluidos: %d' % tot_excluido)
        '''

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

        # Periodico.objects.filter(issn__isnull=True).delete()

        tot_excluido = 0
        for rec in Periodico.objects.filter(issn__isnull=False).values('issn').annotate(cnt=Count('id')).filter(cnt__gte=2):
            base = Periodico.objects.filter(issn=rec['issn'], status='A').exclude(eissn='').order_by('qualis')
            if not base:
                base = Periodico.objects.filter(issn=rec['issn'])

            if base.count() > 1:
                if base[0].issn == base[0].eissn:
                    base = base[1]
                else:
                    base = base[0]
            else:
                base = base[0]

            for duplic in Periodico.objects.filter(issn=rec['issn']).exclude(id=base.id):
                Producao.objects.filter(periodico=duplic).update(periodico=base)
                print(duplic.issn)
                duplic.delete()
                tot_excluido += 1
        print('Excluidos: %d' % tot_excluido)

    def handle_cleanproducao(self, *args, **options):
        for p in Periodico.objects.all():
            if p.issn: p.issn = p.issn.upper()
            if p.eissn: p.eissn = p.eissn.upper()
            p.save()

        #tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')

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

        # Exclusão de alterações no próprio LogEntry
        type_id = ContentType.objects.get(model='logentry').id
        LogEntry.objects.filter(content_type_id=type_id).delete()

        for projeto in ProjetoPesquisa.objects.all():
            PesquisadorProjeto.objects.get_or_create(projeto=projeto, pesquisador=projeto.proponente)

