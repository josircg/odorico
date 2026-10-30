"""
Rotina de exportação de um schema e o assuntos associados.
Josir 05/2026

O arquivo a ser exportado deve ser um JSON contendo uma lista de schemas a serem importados.
   Cada item da lista contém os seguintes atributos:
       sigla: sigla do schema
       descricao: descricao do schema
       nota: nota associada ao schema
       assuntos: lista dos assuntos onde cada elemento da lista contém a sigla, a descrição e o assunto pai.

O arquivo pode ser importada em outra instalação através do management importacao_schema_json
"""

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
        logging.FileHandler("paises.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--destination', type=str, help='Nome do JSON Destino')
        parser.add_argument('--schemas', type=str, help='Nome do JSON com a lista de schemas')

    def handle(self, *args, **options):
        time_begin = time.time()

        # espera uma lista de schemas que serão exportados no formato ['ASJC', 'ANZ', 'DOAJ']
        filename = os.path.join(settings.BASE_DIR, 'media', options['schemas'])
        file = open(filename, 'r', encoding='utf-8')
        schemas_para_importar = json.loads(file.read())
        file.close()

        logging.info(f'Processando arquivo {filename}')

        filename = os.path.join(settings.BASE_DIR, 'media', options['destination'])
        if os.path.exists(filename):
            logging.error(f'Arquivo {filename} já existe')
            return

        transaction.set_autocommit(False)
        novos_assuntos = 0
        tot_gravados = 0
        schemas = []
        for record in Schema.objects.filter(sigla__in=schemas_para_importar):
            tot_gravados += 1
            schema = {'sigla': record.sigla, 'descricao': record.descricao.strip(), 'nota': record.nota,
                      'assuntos': []}
            for assunto in record.assunto_set.filter(cod_externo__isnull=False).order_by('cod_externo'):
                schema['assuntos'].append(
                    { 'cod_externo': assunto.cod_externo,
                      'descricao': assunto.descricao.strip(),
                      'parent_schema': assunto.parent.schema.sigla if assunto.parent else None,
                      'parent_cod': assunto.parent.cod_externo if assunto.parent else None}
                )
                novos_assuntos += 1
            schemas.append(schema)

        file = open(filename, 'w', encoding='utf-8')
        file.write(json.dumps(schemas, indent=2))
        file.write('\n')
        file.close()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Novos schemas: %d' % tot_gravados)
        logging.info('Novos assuntos: %d' % novos_assuntos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
