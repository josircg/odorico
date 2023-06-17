#
# Rotina de importação do citescore da Scopus - Josir - 22/02/2023
# O arquivo pode sempre ser recuperado a partir da URL https://www.scopus.com/sources
# A partir de 2022, o arquivo CSV deve ter as seguintes colunas (não necessariamente nessa ordem):
#
# ScopusID;Title;Print-ISSN;E-ISSN;Status;Citescore;Coverage;Source Type;ASJC;Publisher;Open Access;
#
# Mudanças em relação a importacao_scopus original:
#  - Marca o periódico como inativo
#  - passa a incluir o Source Type (Book Serie) na coluna Frequencia
#  - Historico/Coverage (Anos de atividade)
#

import datetime
import os
import time
import logging
import urllib3

from csv import DictReader
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction
from django.core.validators import URLValidator

from nucleo.apps import get_issn, validate_issn_code, log_object, normalize_name
from qualis.models import Periodico, Assunto, PeriodicoAssunto, PeriodicoISSN, Schema, PeriodicoIndicador

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("scopus.log", mode='a'),
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

    def handle(self, *args, **options):
        time_begin = time.time()

        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info('Processando arquivo %s' % filename)
        transaction.set_autocommit(False)
        urllib3.disable_warnings()

        crossref_schema = Schema.objects.get(sigla='ASJC')
        scopus_schema = Schema.objects.filter(sigla='CS2021').first()
        if not scopus_schema:
            scopus_schema = Schema.objects.create(descricao='Scopus 2021', sigla='CS2021',
                                                  ano_inicial=2021, ano_final=2021)
            logging.info('Schema CS2021 criado')

        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_inativos = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1

            scopus_id = line['ScopusID']
            # if scopus_id != '20447':
            # if tot_lidos < 2200:
            #    continue

            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('Print-ISSN', '').split(' ')
            issn = validate_issn_code(issn[0])
            eissn = validate_issn_code(line.get('E-ISSN', ''))
            if issn:
                issn_busca = issn
            elif eissn:
                issn_busca = eissn
            else:
                tot_invalidos += 1
                continue

            if eissn and eissn != issn:
                eissn = [ eissn ]
            else:
                eissn = []

            if not issn_busca:
                logging.error('ISSN Inválido %s' % issn)
                tot_invalidos += 1
                continue

            inclusao = False
            periodico = Periodico.objects.filter(issn=issn_busca).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn_busca).first()
                if not periodico:

                    # Se não estiver na base e estiver inativo, não perder tempo procurando no site do ISSN
                    if line.get('Status') == 'Inactive':
                        tot_inativos += 1
                        continue

                    issn_record = get_issn(issn_busca, extended=True)
                    if type(issn_record) == tuple:
                        issn, eissn, title, country, url = issn_record
                        if issn_busca != issn:
                            periodico = Periodico.objects.filter(issn=issn).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (issn, issn_busca))
                        else:
                            periodico = Periodico(issn=issn, nome=line.get('Title'))
                            if type(url) == list:
                                url = url[-1]
                            if url and len(url) < 200 and URLValidator(url):
                                periodico.url = url
                            inclusao = True

                        if len(eissn) > 0 and eissn[0] != '':
                            if validate_issn_code(eissn[0]):
                                periodico.eissn = eissn[0]
                            else:
                                print('E-ISSN inválido %s / Busca: %s' % (eissn[0],issn_busca))

                        periodico.dtvalidacao = dtvalidacao
                        menor_nome = line.get('Title')
                        for nome in title:
                            if nome and len(nome) < len(menor_nome) and len(nome) > 10:
                                menor_nome = nome
                        periodico.referencia = menor_nome[:80]
                        periodico.pais = country

                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            if not periodico.scopus_code:
                periodico.scopus_code = scopus_id

            elif periodico.scopus_code != scopus_id:
                logging.error('Erro Scopus ID Antigo:%s Novo:%s' % (periodico.scopus_code, scopus_id))
                tot_invalidos += 1
                continue

            if line['Publisher'] and not periodico.editora:
                periodico.editora = line['Publisher'][:200]

            periodico.nome = line.get('Title').strip()
            periodico.historico = line['Coverage'][:100]
            periodico.frequencia = line['Source Type'].strip()
            periodico.citescore = convert_number(line['Citescore'])
            status_anterior = periodico.status
            periodico.status = 'I' if line['Status'] == 'Inactive' else periodico.status
            # A precedência é sobre o modelo existente.
            # Mas se não houver indicação de Open Access, marcar como Trancado.
            if not periodico.modelo_economico:
                periodico.modelo_economico = None if line['Open Access'] == 'Unpaywall Open Acess' else 'T'
            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação Scopus', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            if periodico.status != status_anterior and periodico.status == 'I':
                log_object(periodico, 'Inativado pela Scopus')
            else:
                # Inclusão das áreas de conhecimento e do Histórico de Indicadores
                if line['ASJC']:
                    for asjc in line['ASJC'].split(';'):
                        if asjc.strip():
                            try:
                                assunto = Assunto.objects.get(schema=crossref_schema, cod_externo=asjc.strip())
                                assunto, _ = PeriodicoAssunto.objects.get_or_create(periodico=periodico, assunto=assunto)
                                assunto.save()
                                indicador, _ = PeriodicoIndicador.objects.get_or_create(periodico=periodico,
                                                                                        schema=scopus_schema,
                                                                                        area=assunto)
                                indicador.indicador = periodico.citescore
                                indicador.save()
                            except Assunto.DoesNotExist:
                                print('ASJC não encontrado: %s' % asjc)

            # Definição entre ISSN impresso ou eletrônico
            for code in eissn:
                if code:
                    try:
                        filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=code)
                        clean_code = ''.join(e for e in code if e.isalnum())
                        if line['Print-ISSN'] == clean_code:
                            filho.meio = 'P'
                        elif line['E-ISSN'] == clean_code:
                            filho.meio = 'E'
                        else:
                            filho.meio = 'E' if filho.meio is None else filho.meio
                        filho.save()
                    except Exception as e:
                        print('Erro incluindo PeriodicoISSN %s' % code)

            transaction.commit()

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos inválidos: %d' % tot_invalidos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de periódicos não incluídos (inativos): %d' % tot_inativos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
