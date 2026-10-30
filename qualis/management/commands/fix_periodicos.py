''''
    Rotinas de Ajustes na base de Periódicos.

    periodicos_duplicados: encontra ISSNs duplicados em outras rotinas e marca-os como status=D e PeriodicoISSN com meio='D'
    Os registros não podem ser excluídos pois eles devem ser exportados para o ambiente de produção.
    Processo:
    1) Exportação JSON no ambiente de teste
    2) Importação JSON no ambiente de produção
    3) Exclusão dos Periodicos com status = 'D' e PeriodicoISSN com meio='D'


'''
import datetime
import logging

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from django.db.models import Count
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType

from qualis.models import *
from nucleo.models import Producao
from nucleo.apps import get_issn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/atualizacao.log", mode='a'),
        logging.StreamHandler()
    ]
)

# Incluir o ASJC de Comunicação para os periódicos selecionados como Comunicação
def insert_asjc(self, *args, **options):
    tot_registros = 0
    comunicacao = Assunto.objects.get(schema_id=1, descricao='Communication')
    for periodico in Periodico.objects.filter(status=Periodico.Status.AtIVA, area=1):
        if not PeriodicoAssunto.objects.filter(periodico=periodico, assunto=comunicacao).exists():
            PeriodicoAssunto.objects.create(periodico=periodico, schema=comunicacao.schema,
                                            assunto=comunicacao, ordem=0)
            tot_registros += 1
    print(f'Assuntos Incluídos: {tot_registros}')


# Exemplo de Update na Base
def update_modelo():
    with connection.cursor() as cursor:
        result = cursor.execute(
            "update qualis_periodico p set modelo_economico = 'U' where modelo_economico is null"
        )
        print(f'Registros alterados: {result}')


# Atualiza a área dos periódicos de CI que estejam marcados como Library Science pela Scopus e que
# ainda não tenham área
def update_area():
    with connection.cursor() as cursor:
        result = cursor.execute(
            "update qualis_periodico p set area_id = 2 where status = 'A' and area_id is null"
            "   and p.id in (select pa.periodico_id from qualis_periodicoassunto pa "
            " where schema_id = 1 and assunto_id = 216)"
            "   and (select count(*) from qualis_periodicoassunto pa where periodico_id = p.id) < 3"
        )
        print(f'Registros alterados: {result}')

        # Atualiza as áreas de Museologia
        result = cursor.execute(
            "update qualis_periodico p set area_id = 3 where area_id is null and status = 'A' and nome like '%Museum%';"
        )
        print(f'Registros inseridos em Museologia: {result}')

        # Incluir o ASJC de Comunicação para os periódicos de Comunicação
        # Mesma rotina que a função insert_asjc só que mais rápida
        result = cursor.execute(
            "insert into qualis_periodicoassunto (assunto_id, periodico_id, ordem, schema_id)"
            "(select 297, p.id, 0, 1 from qualis_periodico p where area_id = 1 and status = 'A' and not exists"
            "     (select * from qualis_periodicoassunto pa "
            "       where schema_id = 1 and assunto_id = 297 and pa.periodico_id = p.id))"
        )
        print(f'ASJC incluídos: {result}')

# Exclusão de alterações no próprio LogEntry
def clean_logentry():
    type_id = ContentType.objects.get(model='logentry').id
    LogEntry.objects.filter(content_type_id=type_id).delete()


def periodicos_duplicados():
    duplicados = (
        PeriodicoISSN.objects
        .exclude(meio='D')
        # .filter(issn='0098-1605')
        .values('issn')  # 1. GROUP BY issn
        .annotate(total=Count('periodico_id', distinct=True))  # 2. COUNT(DISTINCT periodico_id)
        .filter(total__gt=1)  # 3. HAVING total > 1
    )

    tot_lidos = 0
    tot_excluidos = 0
    tot_alterados = 0
    tot_item = 0
    logging.info('Registros a processar: %d' % duplicados.count())

    transaction.set_autocommit(False)
    dtvalidacao = datetime.datetime(year=2026,month=4,day=28)
    for duplicado in duplicados:

        tot_lidos += 1
        if Periodico.objects.filter(periodicoissn__issn=duplicado['issn'],dtupdate__lt=dtvalidacao).count() < 2:
            continue

        invalid_list = []
        issn_master = duplicado['issn']
        issn_record = None
        issn_list = []
        unlink_list = []
        candidatos = Periodico.objects.filter(periodicoissn__issn=duplicado['issn']).order_by('-id')
        for candidato in candidatos:
            if candidato.issn not in invalid_list:
                record = get_issn(candidato.issn)
                if isinstance(record, dict):
                    if not issn_record or issn_master in record['invalid_list']:
                        issn_record = record
                        issn_master = record['issn']
                    issn_list.append(record['issn'])
                    issn_list += record['eissn_list']
                    issn_list += record['invalid_list']
                    invalid_list += record['invalid_list']
                else:
                    # se houver marcação do ISSN inválido
                    invalid_list.append(candidato.issn)
                    logging.warning(f'ISSN inválido: {candidato.issn}, {record}')
                    if 'Erro' not in record and candidato.status == 'A':
                        candidato.historico = record
                        candidato.status = 'F'
                        candidato.save()

        if issn_master and issn_master != duplicado['issn']:
            print(f"{duplicado['issn']} -> ISSN-L correto: {issn_master}")

        master = Periodico.objects.filter(issn=issn_master).first()
        if not master and len(issn_list) > 0:
            master = Periodico.objects.filter(issn__in=issn_list).exclude(issn__in=invalid_list).first()

        if not master:
            master = candidatos.first()
            if master.issn not in issn_list:
                issn_record = get_issn(master.issn)
                if isinstance(issn_record, dict):
                    issn_master = issn_record['issn']
                    issn_list.append(issn_master)
                    issn_list += issn_record['eissn_list']
                    invalid_list += issn_record['invalid_list']
                else:
                    logging.warning(f'Nenhum registro válido {master.issn}, {duplicado["issn"]}, {issn_list}')
                    continue

        if issn_master != master.issn:
            master.eissn = master.issn
            master.issn = issn_master

        candidatos = candidatos.exclude(id=master.id)

        for secundario in candidatos:

            # se o secundário não estiver na lista de issns, basta remover o ISSN master do indíce do secundário
            # e marcar o issn secundário para ser marcado como inativo no master
            if secundario.issn not in issn_list and secundario.eissn not in issn_list:
                logging.info(f"Removendo index {duplicado['issn']} do Periódico {secundario.id} {secundario.issn}")
                if secundario.eissn == issn_master:
                    secundario.eissn = None
                    secundario.save()
                tot_item += PeriodicoISSN.objects.filter(periodico=secundario,issn=issn_master).update(meio='D')
                issn_list.append(secundario.issn)

            # verifica se o master está sem eissn e atribui o do secundário
            if not master.eissn and secundario.issn not in invalid_list:
                if secundario.issn != master.issn:
                    master.eissn = secundario.issn
                elif secundario.eissn != master.issn:
                    master.eissn = secundario.eissn

            # faz o merge dos registros do secundário para o master
            logging.info(f'{master.issn} {master.eissn} <- {secundario.issn} {secundario.eissn}')
            master.url = master.url or secundario.url
            master.sistema = master.sistema or secundario.sistema
            master.frequencia = master.frequencia or secundario.frequencia
            master.scopus_code = master.scopus_code or secundario.scopus_code
            master.google_code = master.google_code or secundario.google_code
            master.doaj_code = master.doaj_code or secundario.doaj_code
            master.oalex_code = master.oalex_code or secundario.oalex_code
            master.google_h5 = master.google_h5 or secundario.google_h5
            master.google_h5m = master.google_h5m or secundario.google_h5m
            master.oalex_h5 = master.oalex_h5 or secundario.oalex_h5
            master.citescore = master.citescore or secundario.citescore
            master.sjr = master.sjr or secundario.sjr
            master.area = master.area or secundario.area
            master.pais = master.pais or secundario.pais

            final_keywords = []
            if master.keywords:
                final_keywords += master.keywords.lower().split(',')
            if secundario.keywords:
                final_keywords += secundario.keywords.lower().split(',')
            master.keywords = ','.join(sorted(set(final_keywords)))

            if master.modelo_economico == 'U':
                master.modelo_economico = secundario.modelo_economico
            for indicador in PeriodicoIndicador.objects.filter(periodico=secundario):
                PeriodicoIndicador.objects.get_or_create(periodico=master,
                                                         schema=indicador.schema,
                                                         area=indicador.area,
                                                         defaults={'classe': indicador.classe,
                                                                   'indicador': indicador.indicador})
            for assunto in PeriodicoAssunto.objects.filter(periodico=secundario):
                dset = PeriodicoAssunto.objects.filter(periodico=master,
                                                       schema=assunto.schema,
                                                       assunto=assunto.assunto)
                if dset.count() > 1:
                    dset.delete()
                PeriodicoAssunto.objects.get_or_create(periodico=master,
                                                       schema=assunto.schema,
                                                       assunto=assunto.assunto,
                                                       defaults={'ordem': assunto.ordem})
            secundario.status = Periodico.Status.AEXCLUIR
            secundario.save()
            PeriodicoISSN.objects.filter(periodico=secundario).update(meio='D')
            tot_excluidos += 1

        # incluir todos os índices que foram encontrados no Portal do ISSN
        for issn in set(issn_list):
            if len(issn) != 9:
                logging.error(f'Invalid ISSN *{issn}*')
                continue
            indexes = PeriodicoISSN.objects.filter(periodico=master, issn=issn)
            valido = issn not in invalid_list
            if indexes:
                if indexes.count() > 1:
                    for duplic in indexes[1:]:
                        tot_excluidos += duplic.delete()
                indexes[0].meio = 'L' if issn == issn_master else indexes[0].meio
                indexes[0].valido = valido
                indexes[0].save()
            else:
                PeriodicoISSN.objects.create(periodico=master, issn=issn,
                                             meio='L' if issn == issn_master else 'O',
                                             valido=valido)

        master.status = Periodico.Status.ATIVA
        master.save()
        tot_alterados += 1
        transaction.commit()

    logging.info('Lidos: %d' % tot_lidos)
    logging.info('Alterados: %d' % tot_alterados)
    logging.info('Excluidos: %d' % tot_excluidos)
    logging.info('ISSN Item excluídos: %d' % tot_item)


class Command(BaseCommand):
    label = 'DB Fixes'

    def handle(self, *args, **options):
        periodicos_duplicados()

    def handle_periodicoISSN(self, *args, **options):
        # Popular PeriodicosISSN para facilitar a busca
        tot_excluido = 0
        for rec in Periodico.objects.all():
            master = Periodico.objects.filter(eissn=rec.issn).exclude(id=rec.id).first()
            if master:
                rec.delete()
                tot_excluido += 1
        print('Excluidos: %d' % tot_excluido)

        # Periodico.objects.filter(issn__isnull=True).delete()

        tot_excluido = 0
        for rec in Periodico.objects.all().values('issn').annotate(cnt=Count('id')).filter(cnt__gte=2):
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
