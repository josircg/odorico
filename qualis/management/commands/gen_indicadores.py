#
# Rotina que gera o histórico de indicadores a partir de um schema
# Utilizada sempre antes de uma nova importação de google, scopus, openalex para que o sistema tenha o indicador antigo.
#
# Josir - 05/2025
#

import time
import logging
from idlelib.pyparse import trans

from django.core.management import BaseCommand
from django.db import transaction

from qualis.models import Schema, PeriodicoIndicador, Periodico

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/gen_indicadores.log", mode='a'),
        logging.StreamHandler()
    ]
)

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, help='Código do Schema')

    def handle(self, *args, **options):
        time_begin = time.time()
        schema_code = 'QUALIS2024'
        schema = Schema.objects.filter(sigla=schema_code).first()
        if not schema:
            print(f'Schema {schema_code} não encontrado')
            return

        tot_lidos = 0
        tot_alterados = 0
        for periodico in Periodico.objects.filter(qualis_ant='ND').exclude(qualis='ND'):
            tot_lidos += 1
            indicador = periodico.periodicoindicador_set.filter(schema_id=schema.id).first()
            if indicador:
                periodico.qualis_ant = indicador.classe
                periodico.save()
                tot_alterados += 1

            if tot_lidos % 1000 == 0:
                print(f'Lidos: {tot_lidos} - Alterados: {tot_alterados}')

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total lidos: %d' % tot_lidos)
        logging.info('Total alterados: %d' % tot_alterados)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))


    def handle_sjr(self, *args, **options):
        time_begin = time.time()
        schema_code = 'SJR2022' # options['schema']
        schema = Schema.objects.filter(sigla=schema_code).first()
        if not schema:
            print(f'Schema {schema_code} não encontrado')
            return

        transaction.set_autocommit(False)
        tot_lidos = 0
        tot_incluidos = 0
        # for periodico in Periodico.objects.filter(oalex_code__isnull=False, oalex_h5__isnull=False):
        for periodico in Periodico.objects.filter(sjr__isnull=False):
            tot_lidos += 1

            record, incluido = PeriodicoIndicador.objects.get_or_create(periodico=periodico,schema=schema)
            # record.indicador = periodico.oalex_h5
            # record.indicador = periodico.citescore
            record.indicador = periodico.sjr
            record.save()
            transaction.commit()
            if incluido:
                tot_incluidos += 1

            if tot_lidos % 100 == 0:
                print(f'Lidos: {tot_lidos} - Incluídos: {tot_incluidos}')

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total lidos: %d' % tot_lidos)
        logging.info('Total incluídos: %d' % tot_incluidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
