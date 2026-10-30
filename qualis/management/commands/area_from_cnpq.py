#
# 21/11/2023: Importação das Áreas/Sub-Areas de conhecimento do CNPQ
# Não confundir com área de avaliação da CAPES
#
# O arquivo CSV é delimitado por ;
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
        logging.FileHandler("logs/area_cnpq.log", mode='a'),
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

        grande_area_schema = Schema.objects.get(sigla='CNPQ0')
        area_schema = Schema.objects.get(sigla='CNPQ1')
        subarea_schema = Schema.objects.get(sigla='CNPQ2')
        especializacao_schema = Schema.objects.get(sigla='CNPQ3')

        # NUMERO_NIVEL;CODIGO_AREA_CONHECIMENTO;CODIGO_GRANDE_AREA;NOME_GRANDE_AREA;CODIGO_AREA;
        # NOME_AREA;CODIGO_SUB_AREA;NOME_SUB_AREA;CODIGO_ESPECIALIDADE;NOME_ESPECIALIDADE
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_grandearea = 0
        tot_area = 0
        tot_subarea = 0
        tot_especialidade = 0
        grande_area = None
        area = None
        subarea = None
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info(f'Lidos: {tot_lidos}')

            if not grande_area or grande_area.cod_externo != line['CODIGO_GRANDE_AREA']:
                grande_area, novo = Assunto.objects.get_or_create(
                                        schema=grande_area_schema,
                                        cod_externo=line['CODIGO_GRANDE_AREA'],
                                        defaults={'descricao': line['NOME_GRANDE_AREA']})
                if novo:
                    grande_area.save()
                    tot_grandearea += 1

            if line['NUMERO_NIVEL'] == '1':
                continue

            if not area or area.cod_externo != line['CODIGO_AREA']:
                area, novo = Assunto.objects.get_or_create(
                                        schema=area_schema,
                                        cod_externo=line['CODIGO_AREA'],
                                        defaults={'descricao': line['NOME_AREA'], 'parent_id': grande_area.id})
                if novo:
                    area.save()
                    tot_area += 1

            if line['NUMERO_NIVEL'] == '2':
                continue

            if not subarea or subarea.cod_externo != line['CODIGO_SUB_AREA']:
                subarea, novo = Assunto.objects.get_or_create(
                                        schema=subarea_schema,
                                        cod_externo=line['CODIGO_SUB_AREA'],
                                        defaults={'descricao': line['NOME_SUB_AREA'], 'parent_id': area.id})
                if novo:
                    subarea.save()
                    tot_subarea += 1

            if line['NUMERO_NIVEL'] == '3':
                continue

            especialidade, novo = Assunto.objects.get_or_create(
                                    schema=especializacao_schema,
                                    cod_externo=line['CODIGO_ESPECIALIDADE'],
                                    defaults={'descricao': line['NOME_ESPECIALIDADE'], 'parent_id': subarea.id})
            if novo:
                especialidade.save()
                tot_especialidade += 1

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Registros lidos: %d' % tot_lidos)
        logging.info('Grande Areas incluídas   : %d' % tot_grandearea)
        logging.info('Areas incluídas          : %d' % tot_area)
        logging.info('SubAreas incluídas       : %d' % tot_subarea)
        logging.info('Especializações incluídas: %d' % tot_especialidade)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
