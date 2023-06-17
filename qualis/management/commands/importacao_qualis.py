import datetime
import os
import time
import logging
import urllib3

from csv import DictReader
from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, Assunto, PeriodicoIndicador, PeriodicoAssunto, PeriodicoISSN, Schema

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
        parser.add_argument('--schema', type=str, help='Sigla do schema que está sendo importado')

    def handle(self, *args, **options):
        time_begin = time.time()

        schema_sigla = options['schema']
        schema = Schema.objects.filter(sigla=schema_sigla).first()
        if not schema:
            logging.error('Schema %s não encontrado' % schema_sigla)
            exit(1)

        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info('Processando arquivo %s' % filename)
        urllib3.disable_warnings()
        transaction.set_autocommit(False)

        # issn;titulo;area;estrato
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0  # Periódicos que tiveram o qualis atualizado
        ultimo_issn = ''
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn_busca = line.get('issn', None)

            # despreza os duplicados
            if issn_busca == ultimo_issn:
                continue

            ultimo_issn = issn_busca
            if not validate_issn_code(issn_busca):
                logging.error('ISSN Inválido %s' % issn_busca)
                tot_invalidos += 1
                continue

            novo_qualis = line.get('estrato')
            if novo_qualis not in ('A1','A2','A3','A4','B1','B2','B3','B4','C'):
                logging.error('Qualis inválido %s' % novo_qualis)
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
                                title = [ line.get('titulo') ]
                            periodico = Periodico(issn=issn, nome=title[0])
                            inclusao = True
                            print('Novo ISSN encontrado:%s busca:%s' % (issn, issn_busca))

                        if len(eissn) > 0 and eissn[0] != '':
                            periodico.eissn = eissn[0]

                        periodico.dtvalidacao = dtvalidacao
                        menor_nome = line.get('titulo')
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
                log_object(periodico, 'Importação %s' % schema.descricao, inclusao=True)
                tot_incluidos += 1

            if novo_qualis != periodico.qualis:
                tot_atualizados += 1
                inclusao = True

            if inclusao:
                periodico.qualis = novo_qualis
                periodico.save()

            PeriodicoIndicador.objects.create(periodico=periodico, schema=schema, classe=novo_qualis)
            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de incluídos: %d' % tot_incluidos)
        logging.info('Total de atualizados: %d' % tot_atualizados)
        logging.info('Total inválidos: %d' % tot_invalidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
