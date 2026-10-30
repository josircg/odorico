#
# Rotina de importação do Australian and New Zealand Classification - Josir - 22/04/2026
# Utilizada pela área de Administração e Contabilidade
#
# Espera as colunas code e description
#

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
        logging.FileHandler("anz.log", mode='a'),
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

        schema, _ = Schema.objects.get_or_create(sigla='ANZ',
                                                 defaults={'description': 'Australian and New Zealand Classification'})

        # code;description
        reader = DictReader(file, delimiter=',', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d' % (tot_lidos, tot_incluidos))

            code = int(line.get('code',0))
            if code == 0:
                continue

            parent = code // 100
            if parent == 0:
                parent = None
            else:
                parent = Assunto.objects.get(schema=schema, cod_externo=parent)

            description = line.get('description', None)
            assunto, incluido = Assunto.objects.get_or_create(schema=schema,
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
