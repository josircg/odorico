#
# Rotina de importação DOAJ - Josir - 25/08/2023 / 23/06/2026
#
# 1a carga: doaj_20230621_1435_utf8.csv
# 2a carga: doaj_journalcsv_20260523_2320_utf8.csv
#
# O arquivo pode sempre ser recuperado a partir da URL https://doaj.org/docs/public-data-dump/
# Em 2026, passou a ficar no próprio site: https://doaj.org/docs/journal-csv
#
# A partir de 2022, o arquivo CSV deve ter as seguintes colunas:
#
# O arquivo deve conter as seguintes colunas:
# - Journal ISSN (print version)
# - Journal EISSN (online version)
# - Journal title
# - Publisher
# - URL in DOAJ
# - Country of publisher
# - Journal URL
# - Keywords
# - APC
#
# A rotina também tenta identificar através das palavras-chaves, os periódicos específicos de Comunicação
#
# O campo Subjects ainda não está sendo tratado - deve-se fazer uma rotina só para entender o schema classificatório, como este abaixo:
#
# Medicine: Surgery: Anesthesiology
# Agriculture: Agriculture (General) | Social Sciences: Industries. Land use. Labor: Special industries and trades: Agricultural industries
# Technology: Chemical technology: Chemical engineering | Technology: Technology (General): Industrial engineering. Management engineering: Information technology
#
import csv
import datetime
import logging
import os
import time
import urllib3

from csv import DictReader
from collections import Counter

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, PeriodicoISSN, AreaConhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/doaj.log", mode='a'),
        logging.StreamHandler()
    ]
)


def update_subjects(counter, subject_str):
    for subject in subject_str.split('|'):
        # A mesma grande área pode aparecer dobrada na string. Assim, a contagem só pode ocorrer uma única vez
        for topic in subject.split('.'):
            topic_list = topic.split(':')
            grand_area = topic_list[0].strip()
            counter[grand_area] += 1
            if len(topic_list) > 2:
                grand_area += ':'+topic_list[1].strip()
                counter[grand_area] += 1
            if len(topic_list) > 1:
                area = topic_list[-1].strip()
                if area != '':
                    counter[ grand_area+':'+area ] += 1

# Teste Unitário para testar a função update_subjects
def teste_subject_dict(self):
    subjects_dict = Counter()
    update_subjects(subjects_dict,
                    'Technology: Chemical technology: Chemical engineering | '
                    'Technology: Technology (General): Industrial engineering. Management engineering: '
                    'Information technology')
    update_subjects(subjects_dict,
                    'Education: Special aspects of education | Philosophy. Psychology. Religion: Psychology')
    return subjects_dict


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')

    def handle(self, *args, **options):
        time_begin = time.time()

        subjects_dict = Counter()

        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')
        transaction.set_autocommit(False)
        urllib3.disable_warnings()

        comunicacao = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')
        tot_comunicacao = 0

        # issn;e-issn;title;url
        reader = DictReader(file, delimiter=',', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('Journal ISSN (print version)')
            eissn = line.get('Journal EISSN (online version)')
            if issn:
                issn_busca = issn.upper()
            elif eissn:
                issn_busca = eissn.upper()
            else:
                tot_invalidos += 1
                continue

            if not validate_issn_code(issn_busca):
                logging.error(f'ISSN Inválido {issn_busca}')
                tot_invalidos += 1
                continue

            eissn = []
            if eissn and eissn != issn:
                if validate_issn_code(eissn):
                    eissn = [eissn]
                else:
                    logging.error(f'eISSN Inválido {eissn}')

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
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if not periodico:
                            eissn_list.append(issn)
                            periodico = Periodico.objects.filter(eissn__in=eissn_list).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (periodico.issn, issn_busca))
                        else:
                            if len(titles) == 0:
                                titles = [line.get('Journal title')]
                            periodico = Periodico(issn=issn, nome=titles[0])
                            inclusao = True
                            print('Novo ISSN encontrado:%s busca:%s' % (issn, issn_busca))

                        if len(eissn_list) > 0 and eissn_list[0] != '':
                            periodico.eissn = eissn_list[0]

                        if not periodico.referencia:
                            menor_nome = line.get('Journal title', '')
                            for nome in titles:
                                if nome and len(nome) < len(menor_nome):
                                    menor_nome = nome
                            periodico.referencia = menor_nome[:80]

                        if issn_record['url'] and not periodico.url:
                            periodico.url = issn_record['url'][:300]
                        periodico.dtvalidacao = dtvalidacao
                        periodico.pais = periodico.pais or issn_record['country'][:100]
                        periodico.save()
                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            periodico.url = periodico.url or line.get('Journal URL',None)[:300]

            if not periodico.pais:
                pais = line.get('Country of publisher', '').split(',')[0]
                if pais:
                    periodico.pais = pais.strip().capitalize()

            editora = line.get('Publisher', None)
            if not periodico.editora and editora:
                periodico.editora = editora[:200]

            if periodico.modelo_economico != 'P':
                if line.get('APC',None) == 'Yes':
                    periodico.modelo_economico = 'A'
                else:
                    periodico.modelo_economico = 'D'

            doaj_code = line['URL in DOAJ'].split('/')[-1]
            if periodico.doaj_code and periodico.doaj_code != doaj_code:
                logging.warning(f'DOAJ code mismatched: {periodico.doaj_code} / {doaj_code}')
            periodico.doaj_code = doaj_code

            # rotina específica para encontrar periódicos de Comunicação
            # media, mass communication, journalism, media research, social communication, media systems
            if periodico.keywords:
                primary_keywords = periodico.keywords.lower().split(',')
            else:
                primary_keywords = []
            primary_keywords += line['Keywords'].lower().split(',')
            final_keywords = []
            for keyword in primary_keywords:
                if 'studies' in keyword:
                    final_keywords.append(keyword)
                else:
                    final_keywords += keyword.split(' and ')

            fator_comunicacao = 0
            primeiro = 2 # Se comunicação for a primeira keyword, aumentar o fator
            keywords = []
            for keyword in set(final_keywords):
                clean_keyword = keyword.strip()
                keywords.append(clean_keyword)
                if clean_keyword in (
                        'media', 'mass communication', 'journalism', 'media research', 'media studies',
                        'communication science',
                        'communication', 'social communication', 'communication media', 'cinema', 'semiotics',
                        'television', 'public relations', 'film studies', 'advertising', 'cultural studies'):
                    fator_comunicacao += 2 + primeiro
                else:
                    fator_comunicacao -= 1 + primeiro
                primeiro = 0

            periodico.keywords = ','.join(set(keywords))

            if fator_comunicacao > 1 and periodico.area is None:
                periodico.area = comunicacao
                tot_comunicacao += 1

            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação DOAJ', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            # Adiciona os ISSN associados no ISSN Index
            if issn not in eissn:
                eissn.append(issn)

            for code in eissn:
                if code != '':
                    if not validate_issn_code(code):
                        logging.error('ISSN Inválido %s' % code)
                    filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=code)
                    filho.meio = 'E' if filho.meio is None else filho.meio
                    filho.save()

            # subjects study
            update_subjects(subjects_dict, line['Subjects'])

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de periódicos Comunicação: %d' % tot_comunicacao)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))

        with open('doaj_subject_areas.csv', 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(subjects_dict.items())
