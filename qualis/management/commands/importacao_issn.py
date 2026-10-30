#
# Rotina de importação ISSN - Listagem de ISSNs geradas a partir de outras rotinas do ODORICO
# Utiliza a mesma estrutura da função
#
# O arquivo deve conter as seguintes colunas: issn, eissn_list, names_list, country, url
#
import ast
import csv
import datetime
import logging
import os
import time
import urllib3

from csv import DictReader

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, PeriodicoISSN, AreaConhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/importacao_issn.log", mode='a'),
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

        # issn;e-issn;title;url
        reader = DictReader(file, delimiter=',', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_atualizados = 0
        tot_invalidos = 0
        dtvalidacao = datetime.datetime.today()
        # issn, eissn_list, names_list, country, url, invalid_list
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            periodico = None
            issn = line.get('issn').upper()
            eissn_list = ast.literal_eval(line.get('eissn_list',''))
            titles = ast.literal_eval(line.get('names_list',''))
            inclusao = False
            eissn_list.insert(0, issn)

            if len(titles) == 0:
                logging.error(f'No titles found {issn}')
                continue

            for issn_busca in eissn_list:
                if not validate_issn_code(issn_busca):
                    tot_invalidos += 1
                    logging.error('ISSN Inválido %s' % issn_busca)
                    continue

                periodico = Periodico.objects.filter(issn=issn_busca).first()
                if periodico:
                    break

            if not periodico:
                periodico = Periodico(issn=issn, nome=titles[0])

                if len(eissn_list) > 1 and eissn_list[1] != '':
                    periodico.eissn = eissn_list[1]

                if not periodico.referencia:
                    menor_nome = titles[0]
                    for nome in titles:
                        if nome and len(nome) < len(menor_nome):
                            menor_nome = nome
                    if menor_nome != periodico.nome:
                        periodico.referencia = menor_nome[:80]

                if line.get('url'):
                    periodico.url = line.get('url')[:300]
                periodico.pais = line.get('country', None).split(',')[0]
                periodico.dtvalidacao = dtvalidacao
                periodico.save()
                inclusao = True

                log_object(periodico, 'Importação Sucupira', inclusao=True)
                tot_incluidos += 1

                for code in eissn_list:
                    if code != '':
                        filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=code)
                        filho.meio = 'E' if filho.meio is None else filho.meio
                        filho.save()

                transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
