#
# Rotina de importação da lista de Países - Josir - 25/08/2023
#
# O arquivo CSV deve conter os seguintes campos: iso3,iso2,nome,name,nombre,latitude,longitude
#

import datetime
import os
import time
import logging

from csv import DictReader

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction
from django.core.exceptions import ValidationError

from qualis.models import Pais

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("paises.log", mode='a'),
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

        reader = DictReader(file, delimiter=',', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        for line in reader:
            tot_lidos += 1

            code = line['iso3']
            try:
                pais, incluido = Pais.objects.get_or_create(
                    iso3=code,
                    defaults={'iso2': line['iso2'], 'nome': line['nome'], 'name': line['name'],
                              'phone_code': line['phone_code'].replace(' ', ''),
                              'latitude': line.get('latitude'),
                              'longitude': line.get('longitude')})
                if incluido:
                    tot_incluidos += 1
                pais.save()
            except ValidationError:
                print(line['iso3'])

        transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total lidos: %d' % tot_lidos)
        logging.info('Total incluídos: %d' % tot_incluidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
