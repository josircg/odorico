#
# Rotina de importação da base SciMago
# O arquivo pode sempre ser recuperado a partir da URL:
# https://www.scimagojr.com/journalrank.php
#
# Campos necessários no CSV: Title;Type;Issn;Publisher;Open Access Diamond;SJR;Quartile;Country;Coverage
# A tabela contém também o ScopusID, mas essa rotina se baseia apenas nos ISSN
#
# Primeira importação em 22/02/2026
#
import datetime
import os
import time
import logging
import urllib3
from decimal import Decimal, InvalidOperation

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
        logging.FileHandler("logs/scimago2026.log", mode='a'),
        logging.StreamHandler()
    ]
)

def convert_number(s):
    try:
        return Decimal(s.replace(',', '.'))
    except InvalidOperation:
        return 0


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
        logging.info(f'Processando arquivo {filename} em {dtvalidacao}')
        urllib3.disable_warnings()
        transaction.set_autocommit(False)
        print(settings.DATABASES['default']['NAME'])

        # issn;titulo;area;estrato
        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0  # Periódicos que tiveram o qualis atualizado

        for line in reader:
            tot_lidos += 1

            if tot_lidos < 12200:
                continue

            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            if line['Type'] != 'journal':
                continue

            periodico = None
            issn_busca = None
            eissn_list = []
            for issn in line.get('Issn').split(','):
                issn_valido = validate_issn_code(issn)
                if issn_valido:
                    eissn_list.append(issn_valido)
                    if not periodico:
                        issn_busca = issn_valido
                        periodico = Periodico.objects.filter(issn=issn_busca).first()
                        if not periodico:
                            periodico = Periodico.objects.filter(eissn=issn_busca).first()

            if not issn_busca:
                tot_invalidos += 1
                continue

            sjr = convert_number(line.get('SJR'))

            inclusao = False
            invalid_list = []

            if not periodico:
                issn_record = get_issn(issn_busca)
                if isinstance(issn_record, dict):
                    issn = issn_record['issn']
                    eissn_list = issn_record['eissn_list']
                    titles = issn_record['names_list']
                    country = issn_record['country']
                    invalid_list = issn_record['invalid_list']
                    if issn_busca != issn:
                        periodico = Periodico.objects.filter(issn=issn).first()

                    if not periodico:
                        eissn_list.append(issn)
                        eissn_list += invalid_list
                        periodico = Periodico.objects.filter(eissn__in=eissn_list).first()

                    if periodico:
                        print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                        if len(issn_record['invalid_list']) > 0:
                            if periodico.issn in issn_record['invalid_list']:
                                log_object(periodico, 'ISSN original {periodico.issn} invalidado pelo portal ISSN')
                                periodico.issn = issn
                            if periodico.eissn in issn_record['invalid_list']:
                                log_object(periodico, 'eISSN {periodico.eissn} invalidado pelo portal ISSN')
                                periodico.eissn = eissn_list[0]

                    else:
                        if len(titles) == 0:
                            titles = [line.get('Title')]
                        periodico = Periodico(issn=issn, nome=titles[0])
                        inclusao = True
                        print('Novo ISSN encontrado:%s busca:%s' % (issn, issn_busca))

                    if len(eissn_list) > 0 and eissn_list[0] != issn:
                        periodico.eissn = eissn_list[0]

                    if not periodico.referencia:
                        menor_nome = line.get('Title')
                        for nome in titles:
                            if nome and len(nome) < len(menor_nome):
                                menor_nome = nome
                        periodico.referencia = menor_nome[:80]
                    periodico.pais = periodico.pais or country
                    if issn_record['url'] and not periodico.url:
                        url = issn_record['url']
                        if type(url) == list:
                            if len(url) > 0:
                                url = url[0]
                            else:
                                url = None
                        if url:
                            periodico.url = url[:199]
                    periodico.dtvalidacao = dtvalidacao
                else:
                    logging.error('ISSN não encontrado %s' % issn_busca)
                    tot_invalidos += 1
                    continue

            if not periodico.eissn:
                for issn in eissn_list:
                    if issn != periodico.issn:
                        periodico.eissn = issn

            if line['Publisher'] and not periodico.editora:
                periodico.editora = line['Publisher'][:200]

            modelo_ajustado = False
            if line['Open Access Diamond'] == 'Yes' and periodico.modelo_economico != 'D':
                periodico.modelo_economico = 'D'
                modelo_ajustado = True

            periodico.historico = periodico.historico or line['Coverage'][:100]
            periodico.pais = periodico.pais or line['Country'][:100]
            periodico.sjr = sjr
            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação %s' % schema.descricao, inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            if modelo_ajustado:
                log_object(periodico, 'Modelo ajustado via Scimago')

            for issn in eissn_list:
                filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=issn)
                filho.meio = 'E' if filho.meio is None else filho.meio
                if issn in invalid_list:
                    filho.valid = False
                filho.save()

            indic, _ = PeriodicoIndicador.objects.get_or_create(periodico=periodico, schema=schema)
            indic.classe = line['SJR Best Quartile']
            indic.indicador = line['H index']
            indic.save()

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos  : %d' % tot_lidos)
        logging.info('Total de incluídos        : %d' % tot_incluidos)
        logging.info('Total de atualizados      : %d' % tot_atualizados)
        logging.info('Total inválidos           : %d' % tot_invalidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
