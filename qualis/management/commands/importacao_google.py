import datetime
import os
import time
import logging

from csv import DictReader
from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import validate_issn_code, log_object
from qualis.models import Periodico, Assunto, PeriodicoAssunto, PeriodicoISSN, Schema

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

        ajsc_schema = Schema.objects.get(sigla='ASJC')

        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_atualizados = 0
        tot_desativados = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 1000 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('issnl')

            eissn = line.get('issn', 'None').upper().split('||')
            for code in eissn:
                if code != 'NONE':
                    periodico_erro = Periodico.objects.filter(issn=code).first()
                    if periodico_erro:
                        periodico_erro.delete()
                        logging.error('E-ISSN existente na base %s - ISSNL:%s ' % (code,issn))
                        issn = None

            if not issn:
                continue

            issn = issn.upper()
            if not validate_issn_code(issn):
                logging.error('ISSN Inválido %s' % issn)
                continue

            periodico = Periodico.objects.filter(issn=issn).first()

            # Previne que o CSV não esteja desincronizado
            try:
                h5 = Decimal(line.get('h5'))
            except:
                logging.error('Erro no tratamento do H5 %s' % issn)
                continue

            if not periodico:
                tot_incluidos += 1
                periodico = Periodico(issn=issn)
                if len(eissn) > 0 and eissn[0] != '':
                    if not validate_issn_code(eissn[0]):
                        logging.error('ISSN Inválido %s' % eissn[0])
                        continue
                    periodico.eissn = eissn[0]
                periodico.nome = line.get('title')
                inclusao = True
            else:
                if periodico.google_code and periodico.google_code != line.get('venue'):
                    logging.error('Google Code é diferente da base %s. ISSN %s' % (line.get('venue'), issn))
                    continue
                if periodico.google_h5 == h5:
                    continue
                last_year = line.get('year')
                if last_year != '' and last_year < '2014':
                    periodico.status = 'F'
                    tot_desativados += 1
                    logging.warning('ISSN desativado: %s' % periodico.issn)
                tot_atualizados += 1
                inclusao = False

            periodico.dtvalidacao = dtvalidacao
            periodico.google_h5 = h5
            periodico.google_h5m = line.get('h5m')
            periodico.google_code = line.get('venue')
            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação Google H5', inclusao=True)

            ajsc = line.get('ajsc', ' ')
            if ajsc != '':
                assunto = Assunto.objects.filter(schema=ajsc_schema, cod_externo__iexact=line.get('ajsc')).first()
                if assunto:
                    PeriodicoAssunto.objects.get_or_create(assunto=assunto, periodico=periodico)

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
        logging.info('Total de periódicos desativados: %d' % tot_desativados)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
