#
# Rotina de importação de um schema e o assuntos associados
#
# O arquivo a ser importado deve ser um JSON contendo uma lista de schemas a serem importados.
#   Cada item da lista contém os seguintes atributos:
#       sigla: sigla do schema
#       descricao: descricao do schema
#       nota: nota associada ao schema
#       assuntos: lista dos assuntos onde cada elemento da lista contém a sigla, a descrição e o assunto pai.
#

import json
import os
import time
import logging

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from qualis.models import Schema, Assunto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/exportacao_schema.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo JSON')

    def handle(self, *args, **options):
        time_begin = time.time()

        filename = os.path.join(settings.BASE_DIR, 'media', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        schemas = json.loads(file.read())
        logging.info(f'Processando arquivo {filename}')
        transaction.set_autocommit(False)
        tot_incluidos = 0
        tot_alterados = 0
        novos_assuntos = 0
        for record in schemas:
            schema, novo = Schema.objects.get_or_create(sigla=record['sigla'],
                                                        defaults={'descricao': record['descricao'],
                                                                  'nota': record['nota']})
            if novo:
                tot_incluidos += 1
            else:
                tot_alterados += 1
            for item in record['assuntos']:
                assunto, novo = Assunto.objects.get_or_create(schema=schema, cod_externo=item['cod_externo'],
                                                              defaults={'descricao': item['descricao']})
                if novo:
                    novos_assuntos += 1

                if item.get('parent_schema'):
                    schema_pai = Schema.objects.get(sigla=item['parent_schema'])
                    parent = Assunto.objects.filter(schema=schema_pai, cod_externo=item['parent_cod'])
                    assunto.parent = parent[0]
                    assunto.save()

        transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Novos schemas: %d' % tot_incluidos)
        logging.info('Schemas alterados: %d' % tot_alterados)
        logging.info('Novos assuntos: %d' % novos_assuntos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
