#
# Rotina de importação Scielo - Josir - 25/08/2023
# O arquivo pode sempre ser recuperado a partir da URL
# A partir de 2022, o arquivo CSV deve ter as seguintes colunas (não necessariamente nessa ordem):
#
# Colunas: 'Journals', 'scielo_url', ' Publisher', 'Status'
# O arquivo original da scielo envia o CSV com um espaço entre cada campo e
# o python se perde quando existe uma vírgula dentro do campo
#
# O ISSN deve ser buscado a partir do atributo pid= da coluna scielo_url
#
import datetime
import os
import time
import logging
import urllib3

from csv import DictReader
from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, PeriodicoISSN, AreaConhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scielo.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')

    def handle(self, *args, **options):
        time_begin = time.time()

        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')
        transaction.set_autocommit(False)
        urllib3.disable_warnings()

        reader = DictReader(file, delimiter=',', skipinitialspace=True, quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_inativados = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            url = line.get('scielo_url').replace('"', '').strip()
            if url and 'pid=' in url:
                pid = url.split('pid=')[1]
                issn = pid.split('&')[0]
            else:
                issn = None

            if issn:
                issn_busca = issn.upper()
            else:
                tot_invalidos += 1
                continue

            inativo = ('deceased' in line.get('status')) or ('suspended' in line.get('status'))

            if not validate_issn_code(issn_busca):
                logging.error('ISSN Inválido %s' % issn_busca)
                tot_invalidos += 1
                continue

            inclusao = False
            url = None
            periodico = Periodico.objects.filter(issn=issn_busca).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn_busca).first()
                if not periodico:

                    # se for inativo, não incluir na base
                    if inativo:
                        continue

                    issn_record = get_issn(issn_busca)
                    if isinstance(issn_record, dict):
                        issn = issn_record['issn']
                        title = issn_record['names_list']
                        eissn = issn_record['eissn_list']
                        url = issn_record['url'][:199]
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                        else:
                            if len(title) == 0:
                                title = [ line.get('journals') ]
                            periodico = Periodico(issn=issn, nome=title[0])
                            inclusao = True

                        if len(eissn) > 0 and eissn[0] != '':
                            periodico.eissn = eissn[0]

                        periodico.dtvalidacao = dtvalidacao
                        menor_nome = line.get('journals')
                        for nome in title:
                            if nome and len(nome) < len(menor_nome):
                                menor_nome = nome
                        periodico.referencia = menor_nome[:80]
                        periodico.pais = issn_record['country'][:29]

                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            periodico.url = periodico.url or url

            editora = line.get('publisher', None).replace('"','').strip()
            if not periodico.editora and editora:
                periodico.editora = editora[:200]

            # se já estiver marcado com Trancado, corrige-se para APC pois periodicos Scielo são de acesso aberto
            # caso contrário, assume-se que é diamond
            if periodico.modelo_economico == 'T':
                periodico.modelo_economico = 'A'
            else:
                periodico.modelo_economico = 'D'

            periodico.sistema = 'Scielo'
            if inativo:
                periodico.status = 'F'
                tot_inativados += 1
            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação Scielo', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=issn)
            filho.meio = 'E' if filho.meio is None else filho.meio
            filho.save()
            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de periódicos inativados: %d' % tot_inativados)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
