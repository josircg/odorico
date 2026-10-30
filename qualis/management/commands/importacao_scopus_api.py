#
# Rotina de importação via API da Scopus - Josir - 3/3/2023
# A partir de 2022, a planilha da Scopus deixou de trazer o percentil e o SJR
# Desta forma, temos que buscar via API
# Essa rotina atualiza o SJR de 2024 diretamente na classe Periodicos
# Como existe um limite semanal de 20k registros, a rotina deve ser executada em 2 ou 3 etapas.
#

import datetime
import time
import json
import logging
import urllib3
import requests

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import log_object
from qualis.models import Periodico, STATUS_ATIVIDADE, Schema, Assunto, PeriodicoIndicador

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scopus-2026.log", mode='a'),
        logging.StreamHandler()
    ]
)


def convert_number(s):
    try:
        return Decimal(s.replace(',', '.'))
    except InvalidOperation:
        return 0


class Command(BaseCommand):

    def handle(self, *args, **options):
        time_begin = time.time()
        transaction.set_autocommit(False)
        urllib3.disable_warnings()

        crossref_schema = Schema.objects.get(sigla='ASJC')
        tot_lidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_inativos = 0
        dtvalidacao = datetime.datetime.today()
        for periodico in Periodico.objects.filter(scopus_code__isnull=False, status='A', area_id__isnull=False):
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Atualizados:%d' % (tot_lidos, tot_atualizados))

            clean_issn = periodico.issn.replace('-','')
            uri = "https://api.elsevier.com/content/serial/title?issn=%s&view=citescore&apiKey=%s" % \
                  (clean_issn, settings.API_SCOPUS_KEY)
            response = requests.get(uri)
            json_data = json.loads(response.text)
            journal_data = json_data['serial-metadata-response']['entry'][0]
            if periodico.scopus_code != journal_data['source-id']:
                print('Scopus ID incompatível')
                tot_invalidos += 1
                continue

            for year_data in journal_data['citeScoreYearInfoList']['citeScoreYearInfo']:
                year = year_data['@year']
                if year == '2024':
                    detail = year_data['citeScoreInformationList'][0]['citeScoreInfo'][0]
                    citescore = convert_number(detail['citeScore'])
                    periodico.citescore = citescore
                    periodico.sjr = convert_number(journal_data['SJRList']['SJR'][0]['$'])
                    periodico.dtvalidacao = dtvalidacao
                    periodico.save()
                    schema, _ = Schema.objects.get_or_create(
                        descricao='Scopus %s' % year, sigla='CS%s' % year,
                        ano_inicial=year, ano_final=year)

                    for subject_rank in detail['citeScoreSubjectRank']:
                        asjc = subject_rank['subjectCode']
                        percentile = subject_rank['percentile']
                        try:
                            assunto = Assunto.objects.get(schema=crossref_schema, cod_externo=asjc.strip())
                        except Assunto.DoesNotExist:
                            print('Assunto não encontrado %s' % asjc.strip())
                            continue
                        indicador, _ = PeriodicoIndicador.objects.get_or_create(periodico=periodico,
                                                                                schema=schema, area=assunto)
                        indicador.classe = percentile
                        indicador.indicador = subject_rank.get('rank')
                        indicador.save()

            log_object(periodico, 'Scopus SJR atualizado', inclusao=False)
            tot_atualizados += 1

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos inválidos: %d' % tot_invalidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de periódicos não incluídos (inativos): %d' % tot_inativos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
