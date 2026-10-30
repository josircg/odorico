#
# Rotina de importação do ASJC - Josir - 25/08/2023
#
# https://github.com/dhimmel/scopus
# https://service.elsevier.com/app/answers/detail/a_id/15181/supporthub/scopus/
#
# Nova importação feita em 02/2026

import datetime
import os
import time
import logging

from csv import DictReader

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from qualis.models import Assunto, Schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("asjc.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato TSV')

    def handle(self, *args, **options):
        time_begin = time.time()

        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')
        transaction.set_autocommit(False)

        crossref_schema = Schema.objects.get(sigla='ASJC')

        # asjc_code;asjc_description
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d' % (tot_lidos, tot_incluidos))

            code = line.get('Code')
            if code == '':
                continue

            code = int(line.get('Code',0))
            parent = (code // 100) * 100
            if parent == code:
                parent = None
            else:
                parent = Assunto.objects.get(schema=crossref_schema, cod_externo=parent)

            description = line.get('Description', None)
            assunto, incluido = Assunto.objects.get_or_create(schema=crossref_schema,
                                                              cod_externo=code,
                                                              defaults={'descricao': description})
            assunto.parent = parent
            assunto.save()

            if incluido:
                tot_incluidos += 1

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de classes incluídas: %d' % tot_incluidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
