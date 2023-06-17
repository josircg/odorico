import datetime
import os
import time
import logging

from csv import DictReader
from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, PeriodicoISSN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("periodicos.log", mode='a'),
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

        # issn;e-issn;title;url
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('issn',None)
            eissn = line.get('e-issn', None)
            if issn:
                issn_busca = issn.upper()
            elif eissn:
                issn_busca = eissn.upper()
            else:
                tot_invalidos += 1
                continue

            if eissn and eissn != issn:
                eissn = [ eissn ]
            else:
                eissn = []

            if not validate_issn_code(issn_busca):
                logging.error('ISSN Inválido %s' % issn_busca)
                tot_invalidos += 1
                continue

            inclusao = False
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
                                title = [ line.get('title') ]
                            periodico = Periodico(issn=issn, nome=title[0])
                            inclusao = True

                        if len(eissn) > 0 and eissn[0] != '':
                            periodico.eissn = eissn[0]

                        periodico.dtvalidacao = dtvalidacao
                        menor_nome = line.get('title')
                        for nome in title:
                            if nome and len(nome) < len(menor_nome):
                                menor_nome = nome
                        periodico.referencia = menor_nome[:80]
                        periodico.pais = country

                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            if inclusao:
                log_object(periodico, 'Importação Diamond', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            if not periodico.url:
                periodico.url = line['url']
            periodico.modelo_economico = 'D'
            periodico.save()

            for code in eissn:
                if code != '':
                    if not validate_issn_code(code):
                        logging.error('ISSN Inválido %s' % code)
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
