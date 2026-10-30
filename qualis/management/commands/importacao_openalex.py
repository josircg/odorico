#
# Importação OpenAlex
# Através da API, a rotina busca todos os periódicos
# https://docs.openalex.org/api-entities/sources/get-lists-of-sources
#
# Obtendo os updates:
# aws s3 sync "s3://openalex/data/sources" --no-sign-request
# aws s3 sync "s3://openalex/legacy-data/sources/" --no-sign-request --exclude "*"  --include "updated_date=2025-12*"
# find . -name "*.gz" -print0 | while IFS= read -r -d $'\0' file; do gunzip "$file"; done
#
# Executado em 09/07/2024 - OALEX2023
# Executado em 18/05/2025 - OALEX2024
# A executar em 2026
#

import datetime
import json
import os
import time
import logging
import urllib3

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction
from collections import Counter

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, Assunto, PeriodicoAssunto, PeriodicoISSN, Schema, PeriodicoIndicador

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/openalex2026.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    tot_lidos = 0
    tot_incluidos = 0
    tot_invalidos = 0
    tot_atualizados = 0
    tot_novos_oalex = 0
    tot_issn_invalidos = 0
    tot_novos_paises = 0
    dtvalidacao = datetime.datetime.today()
    schema_indicador = Schema.objects.get(sigla='OA2025')
    domain_schema = Schema.objects.get(sigla='OALEXD')
    field_schema = Schema.objects.get(sigla='OALEXF')
    subfield_schema = Schema.objects.get(sigla='OALEXS')
    # se fast=True, o sistema não fará busca no Portal do ISSN
    fast = False
    # calcula apenas quantos registros serão tratados
    estimate = False
    # faz apenas a validação dos ISSN
    test_only = True

    def import_file(self, filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                self.tot_lidos += 1

                record = json.loads(line)

                if self.tot_lidos % 100 == 0:
                    print('Lidos:%d - Incluídos:%d - Atualizados:%d' %
                          (self.tot_lidos, self.tot_incluidos, self.tot_atualizados))

                if record['type'] != 'journal':
                    continue

                if self.estimate:
                    continue

                oalex_code = record['id'].split('/')[-1]
                #debug para tratar um único registro
                #if oalex_code != 'S146986746':
                #    continue

                periodico = None
                issn_candidatos = []
                if record['issn_l']:
                    issn_candidatos.append(record['issn_l'])
                if record['issn']:
                    issn_candidatos += record['issn']

                issn_list = []
                for issn in issn_candidatos:
                    if not issn in issn_list:
                        if validate_issn_code(issn):
                            issn_list.append(issn)
                            issn_index = PeriodicoISSN.objects.filter(issn=issn).first()
                            if issn_index:
                                periodico = issn_index.periodico
                            else:
                                periodico = Periodico.objects.filter(issn=issn).first()
                                if not periodico:
                                    periodico = Periodico.objects.filter(eissn=issn).first()
                        else:
                            logging.error(f'{oalex_code}: ISSN Inválido {issn}')
                            self.tot_issn_invalidos += 1

                if len(issn_list) == 0:
                    self.tot_invalidos += 1
                    continue

                # só testa quantos ISSN válidos são encontrados mas não grava nada
                if self.test_only:
                    if not periodico:
                        # estimativa de quantos serão incluídos
                        self.tot_incluidos += 1
                    continue

                if periodico:
                    if periodico.oalex_code and periodico.oalex_code != oalex_code:
                        logging.error(f'Código incompatível {oalex_code}/{periodico.oalex_code}')
                        self.tot_invalidos += 1
                        continue
                    else:
                        periodico.oalex_code = periodico.oalex_code or oalex_code
                        self.tot_atualizados += 1
                        inclusao = False
                        issn_record = None
                else:
                    inclusao = True
                    if self.fast:
                        issn_record = None
                        issn = issn_list[0]
                        title = record.get('display_name', '')
                    else:
                        # obtem os dados do Portal ISSN
                        issn_record = get_issn(issn_list[0])
                        if not isinstance(issn_record, dict):
                            logging.error('ISSN não encontrado no Portal: %s' % issn_list[0])
                            self.tot_invalidos += 1
                            continue

                        issn = issn_record['issn']
                        title_list = issn_record['names_list']

                        # verifica se o ISSN que veio do Portal já existe no Odorico
                        if issn != issn_list[0]:
                            periodico = Periodico.objects.filter(issn=issn).first()
                            if periodico:
                                logging.warning(f'{oalex_code}:ISSN-L errado:{issn_list[0]} correto:{issn}')
                                inclusao = False
                                self.tot_atualizados += 1
                            else:
                                # o ISSN-L do Portal tem preferência
                                issn_list.insert(0,issn)

                        # adiciona a lista que vem do ISSN
                        for eissn in issn_record['eissn_list']:
                            if eissn not in issn_list:
                                issn_list.append(eissn)

                        title = record.get('display_name')
                        if not title:
                            if len(title_list) > 0:
                                title = title_list[0]

                    if not title:
                        logging.error(f'Nenhum título encontrado {issn} {oalex_code}')
                        self.tot_invalidos += 1
                        continue

                    if inclusao:
                        periodico = Periodico(issn=issn, nome=title)
                        if len(issn_list) > 1 and issn_list[1] != issn:
                            periodico.eissn = issn_list[1]

                        if issn_record.get('country'):
                            periodico.pais = issn_record.get('country')[:200]
                            self.tot_novos_paises += 1

                        periodico.dtvalidacao = self.dtvalidacao
                        periodico.save()
                        self.tot_incluidos += 1
                        log_object(periodico, 'Importação OpenAlex', inclusao=True)

                # Prioriza a URL que vem do OpenAlex
                if not periodico.url:
                    if record.get('homepage_url'):
                        periodico.url = record['homepage_url'][:399]
                    elif issn_record and issn_record['url']:
                        if isinstance(issn_record['url'], list):
                            periodico.url = issn_record['url'][0][:399]
                        else:
                            periodico.url = issn_record['url'][:399]

                # o cadastro de países do Openalex está bichado...
                #if not periodico.pais and record['country_code']:
                #    pais = Pais.objects.filter(iso2=record['country_code']).first()
                #    if pais:
                #        periodico.pais = pais.name
                #        self.tot_novos_paises += 1
                #    else:
                #       logging.error('Pais não encontrado: %s' % record['country_code'])

                # Não dá para saber se é Diamond, mas dá para saber se é trancado
                if not periodico.modelo_economico and 'is_oa' in record:
                    periodico.modelo_economico = 'T' if not record['is_oa'] else None

                periodico.editora = periodico.editora or record.get('host_organization_name') or record.get('publisher')
                if not periodico.oalex_code:
                    periodico.oalex_code = oalex_code
                    self.tot_novos_oalex += 1
                periodico.oalex_h5 = record['summary_stats']['h_index']

                try:
                    periodico.save()
                except Exception as e:
                    print(f'{issn_list}: Erro {e}')
                    continue

                for issn in issn_list:
                    filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=issn)
                    filho.meio = 'E' if filho.meio is None else filho.meio
                    filho.save()

                indicador, incluido = PeriodicoIndicador.objects.get_or_create(periodico=periodico,
                                                                               schema=self.schema_indicador)
                indicador.indicador = periodico.oalex_h5
                indicador.save()

                # Topics
                if self.fast and not inclusao:
                    transaction.commit()
                    continue

                domains = Counter()
                fields = Counter()
                subfields = Counter()
                for topic in record.get('topics',[]):
                    domains[topic['domain']['id'].split('/')[-1]] += 1
                    fields[topic['field']['id'].split('/')[-1]] += 1
                    subfields[topic['subfield']['id'].split('/')[-1]] += 1

                # Assume-se que um periódico é sempre de uma único domínio
                if len(domains) > 0:
                    main_domain = domains.most_common()[0][0]
                    assunto = Assunto.objects.filter(schema=self.domain_schema, cod_externo=main_domain).first()
                    if assunto:
                        item, _ = PeriodicoAssunto.objects.get_or_create(schema=self.domain_schema,
                                                                         periodico=periodico,
                                                                         assunto=assunto)
                        item.save()

                ordem = 0
                # só considera os tópicos mais relevantes (que tenham mais da metade de referências que o máximo
                # por exemplo, se o maior topico tiver 5 ocorrências e o segundo apenas 2,
                # este segundo já não é registrado
                if len(fields) > 0:
                    max_counter = fields.most_common()[0][1]
                    for field in fields.most_common():
                        if field[1] >= max_counter // 2:
                            assunto = Assunto.objects.filter(schema=self.field_schema, cod_externo=field[0]).first()
                            if assunto:
                                item, _ = PeriodicoAssunto.objects.get_or_create(schema=self.field_schema, periodico=periodico,
                                                                                 assunto=assunto)
                                item.ordem = ordem
                                item.save()
                                ordem += 1

                if len(subfields) > 0:
                    if periodico.keywords:
                        keywords = periodico.keywords.lower().split(',')
                    else:
                        keywords = []
                    max_counter = subfields.most_common()[0][1]
                    # TODO: Rever a montagem das keywords a partir da rotina_atualizacao_portal_issn
                    for field in subfields.most_common():
                        if field[1] >= max_counter // 2:
                            assunto = Assunto.objects.filter(schema=self.subfield_schema, cod_externo=field[0]).first()
                            if 'Political Science' in assunto.descricao:
                                keywords += assunto.descricao.split(' and ')
                            else:
                                keywords.append(assunto.descricao)
                    periodico.keywords = ','.join(set(keywords)).lower()
                    periodico.save()

                transaction.commit()


    def handle(self, *args, **options):
        time_begin = time.time()

        urllib3.disable_warnings()
        transaction.set_autocommit(False)

        path = os.path.join(settings.BASE_DIR, 'media', 'oalex2026')
        para_processar = []
        for pasta_raiz, subpastas, arquivos in os.walk(path, topdown=False):
            for arquivo in arquivos:
                if not arquivo.endswith('manifest'):
                    para_processar.append(os.path.join(pasta_raiz, arquivo))

        para_processar.sort()

        for filename in para_processar:
            self.import_file(filename)

        time_end = time.time()
        t = round((time_end - time_begin)/60, 2)

        logging.info(f'Total de arquivos         : {len(para_processar)}')
        logging.info(f'Total de registros lidos  : {self.tot_lidos}')
        logging.info(f'Total de incluídos        : {self.tot_incluidos}')
        logging.info(f'Total de novos países     : {self.tot_novos_paises}')
        logging.info(f'Total de atualizados      : {self.tot_atualizados}')
        logging.info(f'Total de novos OAlex      : {self.tot_novos_oalex}')
        logging.info(f'Total INSS inválidos      : {self.tot_issn_invalidos}')
        logging.info(f'Total inválidos           : {self.tot_invalidos}')
        logging.info(f'Tempo de Processamento: {t} minutos')
