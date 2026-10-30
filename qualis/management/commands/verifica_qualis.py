#
# Rotina de Verificação de periódicos que perderam o Qualis
# Essa rotina só será necessária para 2026. Para as futuras, a nova rotina já vai tratar desse caso
#
# Campos necessários no CSV: ISSN;Título;Área de Avaliação;Estrato
#
# Armazena todos os registros que estão contidos no arquivo em um dicionário
# Em seguida, para cada periódico que tenha o qualis != 'ND', verificar se ele não está no dicionário.
#     Se não estiver, marcar o qualis_ant = qualis e marcar o qualis = 'ND'
#
import datetime
import os
import time
import logging
import urllib3

from csv import DictReader

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, Assunto, PeriodicoIndicador, PeriodicoISSN, Schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/qualis2026.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')
        parser.add_argument('--schema', type=str, help='Sigla do schema que está sendo importado')

    def handle(self, *args, **options):
        time_begin = time.time()

        schema_sigla = options['schema']
        schema = Schema.objects.filter(sigla=schema_sigla).first()
        if not schema:
            logging.error('Schema %s não encontrado' % schema_sigla)
            exit(1)

        dtvalidacao = datetime.datetime.today()
        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Verificação Qualis com o arquivo {filename} em {dtvalidacao}')
        urllib3.disable_warnings()
        logging.info(settings.DATABASES['default']['NAME'])

        # issn;titulo;area;estrato
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0  # Periódicos que tiveram o qualis atualizado
        ultimo_issn = ''
        conjunto_base = {}
        for line in reader:
            tot_lidos += 1

            if tot_lidos % 1000 == 0:
                logging.info(f'Lidos:{tot_lidos}')

            issn_busca = line.get('ISSN', None)

            # despreza os duplicados
            if issn_busca == ultimo_issn:
                continue

            ultimo_issn = issn_busca
            novo_qualis = line.get('Estrato')
            if novo_qualis not in ('A1','A2','A3','A4','B1','B2','B3','B4','C'):
                logging.error('Qualis inválido %s' % novo_qualis)
                tot_invalidos += 1
                continue

            issn_record = PeriodicoISSN.objects.filter(issn=issn_busca).first()
            if issn_record:
                periodico = issn_record.periodico
            else:
                periodico = Periodico.objects.filter(issn=issn_busca).first()
                if not periodico:
                    periodico = Periodico.objects.filter(eissn=issn_busca).first()
                    if not periodico:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            conjunto_base[ periodico.id ] = issn_busca

        logging.info(f'Total de registros únicos: {len(conjunto_base)}')

        for periodico in Periodico.objects.exclude(qualis='ND'):
            if not periodico.id in conjunto_base:
                # periodico.qualis_ant = periodico.qualis
                # periodico.qualis = 'ND'
                # periodico.save()
                tot_atualizados += 1

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos  : %d' % tot_lidos)
        logging.info('Total de atualizados      : %d' % tot_atualizados)
        logging.info('Total inválidos           : %d' % tot_invalidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
