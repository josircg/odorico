#
# Rotina de validação e importação a partir de uma lista de ISSNs
#
# Para item, a rotina busca no Portal ISSN para verificar se o código existe e para obter os atributos do periódico
# Josir - 17/04/2021
#

import datetime
import os
from csv import DictReader

import logging
import requests
from crossref.restful import Etiquette, Journals, build_url_endpoint
from django.conf import settings
from django.core.management import BaseCommand
from django.db import DataError, transaction

from utils.stdlib import is_empty
from nucleo.apps import get_issn, validate_issn_code
from qualis.models import Schema, Periodico, Assunto, PeriodicoAssunto, PeriodicoIndicador


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("periodicos.log", mode='w'),
        logging.StreamHandler()
    ]
)


class JornalsCustom(Journals):

    def journal(self, issn, only_message=True, timeout=1000):
        request_url = build_url_endpoint(
            '/'.join([self.ENDPOINT, str(issn)])
        )
        request_params = {}

        result = self.do_http_request(
            'get',
            request_url,
            data=request_params,
            custom_header=self.custom_header,
            timeout=timeout
        )

        if result.status_code == 404:
            return

        try:
            result = result.json()
        except:
            logging.error(f'Erro ao decodificar ISSN {issn}')
            return None

        return result['message'] if only_message is True else result


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')
        parser.add_argument('--qualis', type=int, help='Ano do Qualis')

    def handle(self, *args, **options):
        # filename = os.path.join(settings.BASE_DIR, 'data', 'periodicos.csv')
        qualis_base = options['qualis']
        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')
        etiquette = Etiquette('Odorico', 'v0.3', 'http://odorico.irdx.com.br', 'josir@irdx.com.br')
        crossref_schema = Schema.objects.get(sigla='ASJC')
        qualis_schema = Schema.objects.get(sigla='QUALIS%s' % qualis_base)
        capes_schema = Schema.objects.get(sigla='CAPES-AA')
        journals = JornalsCustom(etiquette=etiquette)
        logging.info(f'CrossRef conectado')
        transaction.set_autocommit(False)

        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_atualizados = 0
        tot_assuntos = 0
        tot_inativos = 0
        tot_validados = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1

            issn = line['ISSN']
            if not issn:
                continue

            # if line['Titulo'].upper() != 'WELLCOME OPEN RESEARCH':
            # if issn != '1981-3082':
            # if tot_lidos < 2800:
            #     continue

            issn = issn.upper()
            eissn = ''
            title = ''
            url = ''
            qualis = line.get('Qualis')
            if qualis:
                qualis = qualis[:2].strip()

            if not validate_issn_code(issn):
                logging.error('ISSN Inválido %s' % issn)
                continue

            periodico = Periodico.objects.filter(issn=issn).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn).first()
                if periodico:
                    novo_issn = periodico.issn
                    eissn = periodico.eissn

            if periodico and periodico.dtvalidacao:
                continue

            issn_record = get_issn(issn)
            if type(issn_record) == tuple:
                novo_issn, eissn, title, country, url = issn_record
                if type(url) == list:
                    url = url[-1]
                status = 'A'
                if novo_issn != issn:
                    if not periodico:
                        periodico = Periodico.objects.filter(issn=novo_issn).first()
            else:
                logging.error('ISSN inexistente: %s' % issn)
                tot_inativos += 1
                continue

            if not title:
                titulo = line.get('Título')
                if not titulo:
                    print('ISSN sem título %s' % issn)
                    titulo = 'VAZIO %s' % issn
            else:
                titulo = title[0]

            periodico.nome = titulo.upper().replace('(IMPRESSO)', '').replace('(ONLINE)', '').strip()

            crossref = None
            subjects = []
            '''
            if not periodico or periodico.periodicoassunto_set.count() != 0:
                try:
                    crossref = journals.journal(issn, timeout=120)
                    subjects = crossref['subjects']
                    title = crossref['title'].upper()
                    for rec_type in crossref['issn-type']:
                        if rec_type['type'] == 'electronic' and not eissn:
                            eissn = rec_type['value']
                        elif rec_type['type'] == 'print' and not novo_issn:
                            novo_issn = rec_type['value']
                except:
                    logging.warning(f'CrossRef notfound/timeout {issn}')
            '''

            if not periodico:
                tot_incluidos += 1
                periodico = Periodico(issn=novo_issn, eissn=eissn)

                periodico.url = line.get('URL', '')
                periodico.sistema = line.get('sistema',None)

                periodico.eissn = eissn
                if not periodico.url and url and len(url) < 200:
                    periodico.url = url
                periodico.pais = periodico.pais or country
                tot_validados += 1

            if novo_issn != periodico.issn:
                periodico.issn = novo_issn

            # TODO: Refazer a rotina de eissn pois o get_issn novo retorna uma lista
            if eissn and eissn != periodico.eissn:
                periodico.eissn = eissn

            if qualis_base == 2020 and qualis:
                periodico.qualis = qualis

            periodico.dtvalidacao = dtvalidacao
            periodico.status = status
            periodico.save()

            for subject in subjects:
                assunto, incluido = Assunto.objects.get_or_create(schema=crossref_schema,
                                                                  descricao=subject['name'],
                                                                  cod_externo=subject['ASJC'])
                if incluido:
                    tot_assuntos += 1
                PeriodicoAssunto.objects.get_or_create(periodico=periodico, assunto=assunto)

            if 'Área' in line:
                area, _ = Assunto.objects.get_or_create(schema=capes_schema, descricao=line['Área'])
                PeriodicoAssunto.objects.get_or_create(periodico=periodico, assunto=area)
            else:
                area = None

            if qualis:
                PeriodicoIndicador.objects.get_or_create(periodico=periodico,
                                                         schema=qualis_schema, area=area, classe=qualis)

            tot_atualizados += 1
            transaction.commit()

            if tot_atualizados % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d - Validados:%d' % (tot_lidos, tot_incluidos, tot_atualizados, tot_validados))

        logging.info('Total de registros lidos: %d' % tot_lidos)
        logging.info('Total de periódicos incluídos: %d' % tot_incluidos)
        logging.info('Total de periódicos inativos: %d' % tot_inativos)
        logging.info('Total de periódicos atualizados: %d' % tot_atualizados)
        logging.info('Total de novos assuntos: %d' % tot_assuntos)
