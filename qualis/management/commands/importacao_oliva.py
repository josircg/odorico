#
# 08/2023 -
# Rotina não foi executada pois os ISSN indicados no arquivo não são confiáveis
# Deve-se refazer a rotina testando se os nomes ou URLs são próximos caso o ISSN seja achado
#

import datetime
import os
import re
import time
import logging
import urllib3
from Levenshtein import ratio

from urllib.parse import urlparse

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
        logging.FileHandler("logs/periodicos.log", mode='a'),
        logging.StreamHandler()
    ]
)


def remove_parenthesis(x):
    return re.sub("\(.*?\)|\[.*?\]","",x)


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
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_novasurls = 0
        tot_namefound = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            titulo = line.get('TÍTULO', None)
            link = line.get('LINK', None)
            parsed_url = urlparse(link)
            root_url = '%s://%s' % (parsed_url.scheme, parsed_url.netloc)

            issn = line.get('ISSN  ',None)
            periodico = None
            if issn:
                issn_busca = issn.upper()
            else:
                for cand in Periodico.objects.filter(url__istartswith=root_url):
                    if ratio(cand.titulo, titulo) > 0.8:
                        periodico = cand
                        break

                if periodico:
                    issn_busca = periodico.issn
                    tot_namefound += 1
                else:
                    tot_invalidos += 1
                    continue

            if not validate_issn_code(issn_busca):
                logging.error('ISSN Inválido %s' % issn_busca)
                tot_invalidos += 1
                continue

            inclusao = False
            atualizado = False
            if not periodico:
                periodico = Periodico.objects.filter(issn=issn_busca).first()

            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn_busca).first()
                if not periodico:
                    issn_record = get_issn(issn_busca, extended=True)
                    if type(issn_record) == tuple:
                        issn, eissn, title, country, url = issn_record
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                        else:
                            if len(title) == 0:
                                title = [ titulo ]
                            periodico = Periodico(issn=issn, nome=title[0])
                            inclusao = True

                        if len(eissn) > 0 and eissn[0] != '':
                            periodico.eissn = eissn[0]

                        periodico.dtvalidacao = dtvalidacao
                        menor_nome = titulo
                        for nome in title:
                            if nome and len(nome) < len(menor_nome):
                                menor_nome = nome
                        periodico.referencia = menor_nome[:80]
                        periodico.pais = country

                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            if not periodico.url:
                periodico.url = link
                atualizado = True
                tot_novasurls += 1

            if not periodico.pais:
                periodico.pais = line.get('PAÍS', None).split(',')[0]
                atualizado = True

            editora = line.get('INSTITUCIÓN EDITORA', None)
            if not periodico.editora and editora:
                periodico.editora = editora[:200]
                atualizado = True

            if periodico.modelo_economico != 'P':
                if line.get('APC',None) == 'SI':
                    periodico.modelo_economico = 'A'
                    atualizado = True

            if inclusao:
                periodico.save()
                log_object(periodico, 'Importação OLIVA', inclusao=True)
                tot_incluidos += 1
            else:
                if atualizado:
                    periodico.save()
                    tot_atualizados += 1

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de match by name: %d' % tot_namefound)
        logging.info('Total de novas URLs: %d' % tot_novasurls)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
