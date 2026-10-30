#
# Rotina de importação do citescore da Scopus - Josir - 22/02/2023
# O arquivo pode sempre ser recuperado a partir da URL https://www.scopus.com/sources ou
#
# Para buscar apenas a lista de periódicos (sem o citescore):
# https://www.elsevier.com/solutions/scopus/how-scopus-works/content
#
# A partir de 2022, o arquivo CSV deve ter as seguintes colunas (não necessariamente nessa ordem):
# A partir de 2023, o arquivo CSV não tem mais a coluna de Citescore e Open Access
# Em 2026, somente o arquivo XLSX é enviado. Assim, o primeiro passo é transformá-lo em CSV com as colunas indicadas abaixo
#
# 2022: ScopusID;Title;Print-ISSN;E-ISSN;Status;Citescore;Coverage;Source Type;ASJC;Publisher;Open Access;
# 2023: ScopusID;Title;Print-ISSN;E-ISSN;Status;Coverage;Source Type;ASJC;Publisher
# 2026: ScopusID;Title;ISSN;E-ISSN;Status;Coverage;Source Type;Publisher;ASJC
#
# Mudanças em relação a importacao_scopus original:
#  - Avisa que o periódico foi marcado como inativo
#  - passa a incluir o Source Type (Book Serie) na coluna Frequencia
#  - Historico/Coverage (Anos de atividade)

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
        logging.FileHandler("logs/scopus-2026.log", mode='a'),
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

        asjc_schema = Schema.objects.get(sigla='ASJC')
        scopus_schema = Schema.objects.filter(sigla='CS2024').first()
        if not scopus_schema:
            Schema.objects.create(descricao='Scopus 2024', sigla='CS2024', ano_inicial=2024, ano_final=2024)
            logging.info('Schema CS2024 criado')

        reader = DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_incluidos = 0
        tot_invalidos = 0
        tot_atualizados = 0
        tot_scopus = 0
        tot_inativos = 0
        dtvalidacao = datetime.datetime.today()
        for line in reader:
            tot_lidos += 1

            scopus_id = line['ScopusID']
            # if scopus_id != '20447':
            # if tot_lidos < 2200:
            #    continue

            if line['Source Type'] != 'Journal':
                continue

            if tot_lidos % 100 == 0:
                logging.info('Lidos:%d - Incluídos:%d - Atualizados:%d' % (tot_lidos, tot_incluidos, tot_atualizados))

            issn = line.get('ISSN', '').split(' ')
            issn = validate_issn_code(issn[0])
            eissn = validate_issn_code(line.get('E-ISSN', ''))
            if issn:
                issn_busca = issn
            elif eissn:
                issn_busca = eissn
            else:
                tot_invalidos += 1
                continue

            eissn_list = [ issn ]
            if eissn and eissn != issn:
                eissn_list.append(eissn)

            # Se estiver inativo, não perder tempo procurando na base de periódicos
            if line.get('Status') == 'Inactive':
                tot_inativos += 1
                # continue

            # só tratar os inativos
            if line.get('Status') != 'Inactive':
                continue

            if not issn_busca:
                logging.error('ISSN Inválido %s' % issn)
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

                        if not periodico:
                            eissn_list.append(issn)
                            periodico = Periodico.objects.filter(eissn__in=eissn_list).first()

                        if periodico:
                            print('ISSN-L encontrado:%s busca:%s' % (periodico.issn, issn_busca))
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

                        if len(eissn_list) > 0 and eissn_list[0] != '':
                            periodico.eissn = eissn_list[0]
                        elif eissn:
                            periodico.eissn = eissn
                            eissn_list.append(eissn)

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
                        periodico.save()
                    else:
                        logging.error('ISSN não encontrado %s' % issn_busca)
                        tot_invalidos += 1
                        continue

            if not periodico.scopus_code:
                periodico.scopus_code = scopus_id
                tot_scopus += 1

            elif periodico.scopus_code != scopus_id:
                logging.error(f'Mudança Scopus ID Antigo:{periodico.scopus_code} Novo:{scopus_id} ({issn_busca})')
                periodico.scopus_code = scopus_id
                tot_scopus += 1
            else:
                continue

            if line['Publisher'] and not periodico.editora:
                periodico.editora = line['Publisher'][:200]

            periodico.nome = line.get('Title').strip()
            if not periodico.historico:
                periodico.historico = line['Coverage'][:100]
            if not periodico.frequencia:
                periodico.frequencia = line['Source Type'].strip()

            # A precedência é sobre o modelo existente.
            # Mas se não houver indicação de Open Access, marcar como Trancado.
            # if not periodico.modelo_economico:
            #    if line.get('Open Access', None):
            #        periodico.modelo_economico = None if line['Open Access'] == 'Unpaywall Open Acess' else 'T'

            # Antes a rotina marcava o periódico como Inativo, mas tivemos falsos positivos, ou seja,
            # o periódico estava Inativo apenas para a Scopus mas continuava ativo
            # Na nova lógica, o sistema apenas indica no log que o periódico está marcada como Inativo na Scopus
            if line['Status'] == 'Inactive' and periodico.status == 'A':
                 log_object(periodico, 'Scopus marcou o periódico como inativo')
                 periodico.citescore = None

            periodico.save()

            if inclusao:
                log_object(periodico, 'Importação Scopus', inclusao=True)
                tot_incluidos += 1
            else:
                tot_atualizados += 1

            #if citescore:
            #    indicador = PeriodicoIndicador.objects.filter(
            #        periodico=periodico, schema=scopus_schema).first()
            #    if indicador:
            #        indicador.indicador = periodico.citescore
            #        indicador.save()
            #    else:
            #        PeriodicoIndicador.objects.create(
            #            periodico=periodico, schema=scopus_schema, indicador=periodico.citescore
            #        )

            # Inclusão das áreas de conhecimento e do Histórico de Indicadores
            if line['ASJC'] and inclusao:
                for asjc in line['ASJC'].split(';'):
                    if asjc.strip():
                        try:
                            assunto = Assunto.objects.get(schema=asjc_schema, cod_externo=asjc.strip())
                            per_assunto, inclusao = PeriodicoAssunto.objects.get_or_create(
                                periodico=periodico,
                                assunto=assunto,
                                schema=asjc_schema)
                            if inclusao:
                                per_assunto.save()

                        except Assunto.DoesNotExist:
                            print('ASJC não encontrado: %s' % asjc)

            # Definição entre ISSN impresso ou eletrônico
            for code in eissn_list:
                if code:
                    try:
                        filho, inclusao = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=code)
                        if inclusao:
                            clean_code = ''.join(e for e in code if e.isalnum())
                            if line['ISSN'] == clean_code:
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

        logging.info('Registros lidos: %d' % tot_lidos)
        logging.info('Periódicos incluídos: %d' % tot_incluidos)
        logging.info('Periódicos com Scopus inserido: %d' % tot_scopus)
        logging.info('Periódicos inválidos: %d' % tot_invalidos)
        logging.info('Periódicos atualizados: %d' % tot_atualizados)
        logging.info('Periódicos não incluídos (inativos): %d' % tot_inativos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
