#
# Rotina de importação Web of Science - Josir - 25/08/2023
# O arquivo pode sempre ser recuperado a partir da URL https://mjl.clarivate.com/collection-list-downloads
#
# O arquivo deve conter as seguintes colunas:
# "Journal title","ISSN","eISSN","Publisher name","Publisher address","Languages","Web of Science Categories"
#
# A rotina também tenta identificar através das palavras-chaves, os periódicos específicos de Comunicação
# https://support.clarivate.com/ScientificandAcademicResearch/s/article/Web-of-Science-List-of-Subject-Classifications-for-All-Databases?language=en_US
#
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
from qualis.models import Periodico, AreaConhecimento, PeriodicoAssunto, PeriodicoISSN, Schema, Assunto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/wos.log", mode='a'),
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
        urllib3.disable_warnings()

        wos_schema, _ = Schema.objects.get_or_create(descricao='Web of Science', sigla='WOS')
        comunicacao = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')
        tot_comunicacao = 0

        reader = DictReader(file, delimiter=',', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_assuntos = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('ISSN',None)
            eissn = line.get('eISSN', None)
            if issn:
                issn_busca = issn.upper()
            elif eissn:
                issn_busca = eissn.upper()
            else:
                tot_invalidos += 1
                continue

            if eissn and eissn != issn:
                eissn_list = [eissn]
            else:
                eissn_list = []

            if not validate_issn_code(issn_busca):
                logging.error('ISSN Inválido %s' % issn_busca)
                tot_invalidos += 1
                continue

            inclusao = False
            periodico = Periodico.objects.filter(issn=issn_busca).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn_busca).first()
                if not periodico:
                    issn_record = get_issn(issn_busca)
                    if isinstance(issn_record, dict):
                        issn = issn_record['issn']
                        eissn_list = issn_record['eissn_list']
                        titles = issn_record['names_list']
                        country = issn_record['country']
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                        else:
                            if len(titles) == 0:
                                titles = [line.get('Journal title')]
                            periodico = Periodico(issn=issn, nome=titles[0])
                            inclusao = True

                        if len(eissn_list) > 0 and eissn_list[0] != '':
                            periodico.eissn = eissn_list[0]

                        if not periodico.referencia:
                            menor_nome = line.get('Título')
                            for nome in titles:
                                if nome and len(nome) < len(menor_nome):
                                    menor_nome = nome
                            periodico.referencia = menor_nome[:80]
                        periodico.pais = periodico.pais or country
                        if issn_record['url'] and not periodico.url:
                            periodico.url = issn_record['url'][:300]
                        periodico.dtvalidacao = dtvalidacao
                        periodico.save()

                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            editora = line.get('Publisher name', None)
            if not periodico.editora and editora:
                periodico.editora = editora[:200]

            periodico.save()

            # rotina específica para encontrar periódicos de Comunicação
            # media, mass communication, journalism, media research, social communication, media systems
            fator_comunicacao = 0
            primeiro = 2 # Se comunicação for a primeira keyword, aumentar o fator
            if periodico.keywords:
                keywords = periodico.keywords.split(',')
            else:
                keywords = []

            wos_categories = []
            for cat1 in line["Web of Science Categories"].split(','):
                for cat2 in cat1.split('|'):
                    wos_categories.append(cat2.strip())

            for categoria in wos_categories:
                clean_keyword = categoria.strip().lower()
                keywords.append(clean_keyword)
                if clean_keyword in (
                        'media', 'mass communication', 'journalism', 'media research', 'media studies',
                        'communication', 'social communication', 'communication media', 'cinema',
                        'television', 'public relations', 'film studies', 'advertising'):
                    fator_comunicacao += 2 + primeiro
                else:
                    fator_comunicacao -= 1 + primeiro
                primeiro = 0

                assunto, novo_assunto = Assunto.objects.get_or_create(schema=wos_schema, descricao=categoria)
                if novo_assunto:
                    tot_assuntos += 1
                PeriodicoAssunto.objects.get_or_create(assunto=assunto, periodico=periodico)

            periodico.keywords = ','.join(set(keywords))

            if fator_comunicacao > 0 and periodico.area is None:
                periodico.area = comunicacao
                periodico.save()
                tot_comunicacao += 1

            if inclusao:
                log_object(periodico, 'Importação WOS', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            for code in eissn_list:
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
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de periódicos Comunicação: %d' % tot_comunicacao)
        logging.info('Total de novos assuntos: %d' % tot_assuntos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
