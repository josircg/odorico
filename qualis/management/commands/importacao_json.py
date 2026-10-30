#
# Rotina de importação JSON - Josir - 25/05/2026
# Permite atualizar uma base de dados do Odorico com atualizações de outra instância
#
# O arquivo JSON é gerado pela rotina de exportacao_json
# Último processamento em 25/05/2026
#
import datetime
import json
import os
import time
import logging

from decimal import Decimal

from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction

from nucleo.apps import validate_issn_code, log_object, clean_texto
from nucleo.models import Producao
from qualis.models import Periodico, PeriodicoAssunto, PeriodicoIndicador, PeriodicoISSN, Schema, Assunto, \
    AreaConhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/import_json.log", mode='a'),
        logging.StreamHandler()
    ]
)

def import_json(file):
    tot_lidos = 0
    tot_incluidos = 0
    tot_invalidos = 0
    tot_atualizados = 0
    tot_inativados = 0
    tot_excluidos = 0
    tot_oalex = 0
    tot_naoatualizado = 0
    dt_corte = datetime.datetime(year=2026,month=3,day=20)

    for line in file.readlines():
        tot_lidos += 1
        if tot_lidos % 500 == 0:
            logging.info(f'Lidos:{tot_lidos} - Incluídos:{tot_incluidos} - '
                         f'Atualizados:{tot_atualizados} - Excluídos: {tot_excluidos}')

        registro = json.loads(line)
        issn = registro.get('issn')
        if not clean_texto(issn):
            logging.error('ISSN não preenchido')
            tot_invalidos += 1
            continue

        periodico = Periodico.objects.filter(issn=issn).first()

        if registro.get('status') == 'D':
            # se for exclusão e o registro já não existe, segue em frente
            if not periodico:
                continue

            logging.warning(f'ISSN excluído {issn}')
            producao = Producao.objects.filter(periodico=periodico)
            tot_producao = producao.count()
            if tot_producao > 0:
                candidato = Periodico.objects.filter(periodicoissn__issn=issn,status='A').first()
                if candidato:
                    producao.update(periodico=candidato)
                    tot_producao = 0

            if tot_producao == 0:
                PeriodicoISSN.objects.filter(periodico=periodico).delete()
                PeriodicoIndicador.objects.filter(periodico=periodico).delete()
                PeriodicoAssunto.objects.filter(periodico=periodico).delete()
                periodico.delete()
                tot_excluidos += 1
                continue

        inclusao = False
        if registro['nome'].upper() == registro['nome']:
            registro['nome'] = registro['nome'].capitalize()

        if not periodico:
            periodico = Periodico(issn=issn, nome=registro['nome'])
            inclusao = True
            tot_incluidos += 1
        else:
            if periodico.dtupdate >= dt_corte:
                logging.info(f'Já atualizado {periodico.issn}')
                tot_naoatualizado += 1
                continue
            periodico.nome = registro['nome']
            if periodico.status != registro['status'] and registro['status'] != 'A':
                periodico.status = registro['status']
                tot_inativados += 1

        if registro.get('area'):
            area = AreaConhecimento.objects.filter(id=registro['area']).first()
            if area:
                periodico.area = area
            else:
                logging.warning(f'Área não encontrada {registro["area"]}')
                break

        periodico.url = registro.get('eissn')
        periodico.url = registro.get('url')
        periodico.modelo_economico = registro.get('modelo_economico')
        periodico.qualis = registro.get('qualis')
        periodico.qualis_ant = registro.get('qualis_ant')
        periodico.pais = registro.get('pais')
        periodico.sistema = registro.get('sistema')
        periodico.frequencia = registro.get('frequencia')
        periodico.historico = registro.get('historico')
        periodico.referencia = registro.get('referencia')
        periodico.editora = registro.get('editora')
        periodico.google_code = registro.get('google_code')
        periodico.scopus_code = registro.get('scopus_code')
        periodico.doaj_code = registro.get('doaj_code')
        periodico.keywords = registro.get('keywords')
        if registro.get('google_h5'): periodico.google_h5 = Decimal(registro['google_h5'])
        if registro.get('google_h5m'): periodico.google_h5m = Decimal(registro['google_h5m'])
        if registro.get('citescore'): periodico.citescore = Decimal(registro['citescore'])
        if registro.get('oalex_h5'): periodico.oalex_h5 = Decimal(registro['oalex_h5'])
        if registro.get('sjr'): periodico.sjr = Decimal(registro['sjr'])
        if periodico.oalex_code is None and registro.get('oalex_code'):
            tot_oalex += 1
        periodico.oalex_code = registro.get('oalex_code')

        if registro['dtvalidacao']:
            dtvalidacao = datetime.datetime.strptime(registro['dtvalidacao'].split('T')[0], '%Y-%m-%d')
            periodico.dtvalidacao = dtvalidacao
        periodico.save()

        if inclusao:
            log_object(periodico, 'Importação JSON', inclusao=True)
        else:
            tot_atualizados += 1

        PeriodicoISSN.objects.filter(periodico=periodico).delete()
        for item in registro['issn_list']:
            PeriodicoISSN.objects.create(periodico=periodico, issn=item['issn'],
                                         meio=item['meio'],
                                         valido=item['valido'])

        for item in registro['indicadores_list']:
            # tenta encontrar o assunto do periódico
            indicador = PeriodicoIndicador.objects.filter(periodico=periodico,
                                                          schema__sigla=item['schema'],
                                                          area__cod_externo=item['cod_externo']).first()
            # caso não encontre, deve-se criar mas antes verificar se o schema e assunto já existem na base
            if not indicador:
                # Encontra o schema do assunto (que deve ter o mesmo código em todas as instâncias)
                try:
                    schema = Schema.objects.get(sigla=item['schema'])
                    assunto = Assunto.objects.filter(schema=schema, cod_externo=item['cod_externo']).first()
                    indicador = PeriodicoIndicador(periodico=periodico, schema=schema, area=assunto)
                except Schema.DoesNotExist:
                    logging.warning(f'Schema não encontrado: {item["schema"]}')
                    break
                except Assunto.DoesNotExist:
                    logging.warning(f'Assunto não encontrado: {item["schema"]}, {item["cod_externo"]}')
                    break

            indicador.classe = item.get('classe') or indicador.classe
            indicador.indicador = item.get('indicador') or indicador.indicador
            indicador.save()

        for item in registro['assunto_list']:
            # tenta encontrar o assunto do periódico
            p_assunto = PeriodicoAssunto.objects.filter(periodico=periodico,
                                                        schema__sigla=item['schema'],
                                                        assunto__cod_externo=item['cod_externo']).first()
            # caso não encontre, deve-se criar mas antes verificar se o schema e assunto já existem na base
            if p_assunto:
                if p_assunto.ordem != item['ordem']:
                    p_assunto.ordem = item['ordem']
                    p_assunto.save()
            else:
                # Encontra o schema do assunto (que deve ter o mesmo código em todas as instâncias)
                try:
                    schema = Schema.objects.get(sigla=item['schema'])
                    assunto = Assunto.objects.get(schema=schema, cod_externo=item['cod_externo'])
                    p_assunto = PeriodicoAssunto(periodico=periodico, schema=schema, assunto=assunto, ordem=item['ordem'])
                    p_assunto.save()
                except Schema.DoesNotExist:
                    logging.warning(f'Schema não encontrado: {item["schema"]}')
                    break
                except Assunto.DoesNotExist:
                    logging.warning(f'Assunto não encontrado: {item["schema"]}, {item["cod_externo"]}')
                    break

        transaction.commit()


    return (tot_lidos, tot_incluidos, tot_atualizados, tot_excluidos,
            tot_inativados, tot_naoatualizado, tot_oalex)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo com a atualização de periódicos em JSON')

    def handle(self, *args, **options):
        time_begin = time.time()

        filename = os.path.join(settings.BASE_DIR, 'media', options['arquivo'])
        file = open(filename, 'r', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')
        transaction.set_autocommit(False)
        result_stats = import_json(file)
        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de registros lidos: %d' % result_stats[0])
        logging.info('Periódicos incluídos: %d' % result_stats[1])
        logging.info('Periódicos atualizados: %d' % result_stats[2])
        logging.info('Periódicos excluídos: %d' % result_stats[3])
        logging.info('Periódicos inativados: %d' % result_stats[4])
        logging.info('Periódicos não atualizados: %d' % result_stats[5])
        logging.info('Openalex atualizados: %d' % result_stats[6])
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
