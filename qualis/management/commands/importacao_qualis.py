#
# Rotina de importação do Qualis Periódicos
# O arquivo pode sempre ser recuperado a partir da URL:
# https://sucupira.capes.gov.br/sucupira/public/consultas/coleta/veiculoPublicacaoQualis/listaConsultaGeralPeriodicos.jsf
#
# Campos necessários no CSV: ISSN;Título;Área de Avaliação;Estrato
# Última atualização em 25/05/2024 no Schema
# Nova atualização em 22/02/2026 com o Qualis 2026
#
# IMPORTANTE: Antes de executar a rotina, deve-se atualizar o qualis_ant com o valor corrente
#
#     update qualis_periodico set qualis_ant = qualis, qualis='ND' where qualis != ND'
#
import datetime
import os
import time
import logging
import urllib3

from csv import DictReader

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, Assunto, PeriodicoIndicador, PeriodicoISSN, Schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/qualis2026.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')
        parser.add_argument('--schema', type=str, help='Sigla do schema que está sendo importado')

    def handle(self, *args, **options):
        time_begin = time.time()

        schema_sigla = options['schema']
        schema = Schema.objects.filter(sigla=schema_sigla).first()
        if not schema:
            logging.error('Schema %s não encontrado' % schema_sigla)
            exit(1)

        dtvalidacao = datetime.datetime.today()
        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename} em {dtvalidacao}')
        urllib3.disable_warnings()
        transaction.set_autocommit(False)
        print(settings.DATABASES['default']['NAME'])

        # issn;titulo;area;estrato
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0  # Periódicos que tiveram o qualis atualizado
        tot_indicadores = 0
        ultimo_issn = ''
        for line in reader:
            tot_lidos += 1

            # if tot_lidos < 9800:
            #    continue

            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn_busca = line.get('ISSN', None)

            # despreza os duplicados
            if issn_busca == ultimo_issn:
                continue

            ultimo_issn = issn_busca
            #if not validate_issn_code(issn_busca):
            #    logging.error('ISSN Inválido %s' % issn_busca)
            #    tot_invalidos += 1
            #    continue

            # tentar incluir os que não tem ISSN válido
            if validate_issn_code(issn_busca):
                continue

            novo_qualis = line.get('Estrato')
            if novo_qualis not in ('A1','A2','A3','A4','B1','B2','B3','B4','C'):
                logging.error('Qualis inválido %s' % novo_qualis)
                tot_invalidos += 1
                continue

            inclusao = False
            eissn_list = []
            invalid_list = []
            periodico = Periodico.objects.filter(issn=issn_busca).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn_busca).first()
                if not periodico:
                    issn_record = get_issn(issn_busca)
                    if isinstance(issn_record, dict):
                        issn = issn_record['issn']
                        eissn_list = issn_record['eissn_list']
                        titles = issn_record['names_list']
                        country = issn_record['country']
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if not periodico:
                            eissn_list.append(issn)
                            eissn_list += invalid_list
                            periodico = Periodico.objects.filter(eissn__in=eissn_list).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                            if len(issn_record['invalid_list']) > 0:
                                if periodico.issn in issn_record['invalid_list']:
                                    log_object(periodico, 'ISSN original {periodico.issn} invalidado pelo portal ISSN')
                                    periodico.issn = issn
                                if periodico.eissn in issn_record['invalid_list']:
                                    log_object(periodico, 'eISSN {periodico.eissn} invalidado pelo portal ISSN')
                                    periodico.eissn = eissn_list[0]

                        else:
                            if len(titles) == 0:
                                titles = [line.get('Título')]
                            periodico = Periodico(issn=issn, nome=titles[0])
                            inclusao = True
                            print('Novo ISSN encontrado:%s busca:%s' % (issn, issn_busca))

                        if len(eissn_list) > 0 and eissn_list[0] != '':
                            periodico.eissn = eissn_list[0]
                        elif issn_busca != periodico.issn:
                            periodico.eissn = issn_busca

                        if not periodico.referencia:
                            menor_nome = line.get('Título')
                            for nome in titles:
                                if nome and len(nome) < len(menor_nome):
                                    menor_nome = nome
                            periodico.referencia = menor_nome[:80]
                        periodico.pais = periodico.pais or country
                        if issn_record['url'] and not periodico.url:
                            url = issn_record['url']
                            if type(url) == list:
                                if len(url) > 0:
                                    url = url[0]
                                else:
                                    url = None
                            if url:
                                periodico.url = url[:199]
                        periodico.dtvalidacao = dtvalidacao
                        periodico.qualis = novo_qualis
                        periodico.qualis_ant = 'ND'
                        periodico.save()
                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            if inclusao:
                log_object(periodico, 'Importação %s' % schema.descricao, inclusao=True)
                tot_incluidos += 1

            if novo_qualis != periodico.qualis_ant and not inclusao:
                tot_atualizados += 1
                log_object(periodico, f'Qualis atualizado: {periodico.qualis_ant} -> {novo_qualis}')
                periodico.qualis = novo_qualis
                periodico.save()

            for issn in eissn_list:
                filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=issn)
                filho.meio = 'E' if filho.meio is None else filho.meio
                if issn in invalid_list:
                    filho.valid = False
                filho.save()

            area_descricao = line.get('Área de Avaliação')
            area = Assunto.objects.filter(schema=schema, descricao=area_descricao).first()
            if area:
                indic = PeriodicoIndicador.objects.filter(periodico=periodico, schema=schema, area=area).first()
                if not indic:
                    indic = PeriodicoIndicador.objects.filter(periodico=periodico, schema=schema, area=None).first()
                    if not indic:
                        indic = PeriodicoIndicador(periodico=periodico, schema=schema)
                        inclusao = True
                indic.classe = novo_qualis
                indic.area = area
                indic.save()
                if inclusao:
                    tot_indicadores += 1
                # Exclui qualquer outro indicador sem classe
                PeriodicoIndicador.objects.filter(periodico=periodico, schema=schema, area=None).delete()
            else:
                logging.error(f'Área não encontrada {area_descricao}')

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos  : %d' % tot_lidos)
        logging.info('Total de incluídos        : %d' % tot_incluidos)
        logging.info('Total de novos indicadores: %d' % tot_indicadores)
        logging.info('Total de atualizados      : %d' % tot_atualizados)
        logging.info('Total inválidos           : %d' % tot_invalidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
