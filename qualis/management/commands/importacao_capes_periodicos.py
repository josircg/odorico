#
# Rotina de validação da base Sucupira/CAPES
#
# A rotina verifica se o ISSN indicado no arquivo existe na base do Odorico ou na API do ISSN
# Grava um arquivo com os dados dos periódicos inexistentes no Odorico e recuperados na API do ISSN
# Josir - 28/06/2024
#

# CD_PROGRAMA_IES,NM_PROGRAMA_IES,SG_ENTIDADE_ENSINO,NM_ENTIDADE_ENSINO
# AN_BASE,ID_ADD_PRODUCAO_INTELECTUAL,ID_PRODUCAO_INTELECTUAL,NM_PRODUCAO,ID_TIPO_PRODUCAO,NM_TIPO_PRODUCAO,ID_SUBTIPO_PRODUCAO,NM_SUBTIPO_PRODUCAO
# ID_FORMULARIO_PRODUCAO,NM_FORMULARIO,ID_AREA_CONCENTRACAO,NM_AREA_CONCENTRACAO,ID_LINHA_PESQUISA,NM_LINHA_PESQUISA
# ID_PROJETO,NM_PROJETO,DH_INICIO_AREA_CONC,DH_FIM_AREA_CONC,DH_INICIO_LINHA,DH_FIM_LINHA,
# CD_IDENTIFICADOR_VEICULO,DS_TITULO_PADRONIZADO

import csv
import os
import logging
import urllib3

from django.conf import settings
from django.core.management import BaseCommand

from utils.stdlib import is_empty
from nucleo.apps import get_issn, validate_issn_code
from qualis.models import Schema, Periodico, Assunto, PeriodicoAssunto, PeriodicoIndicador


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s\n",
    handlers=[
        logging.FileHandler("logs/capes.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')

    def handle(self, *args, **options):
        filename = os.path.join(settings.BASE_DIR, 'data', options['arquivo'])
        file = open(filename, 'r', encoding='iso-8859-1')
        logging.info(f'Processando arquivo {filename}')
        urllib3.disable_warnings()

        issn_not_found = {}
        not_found_file = open(os.path.join(settings.BASE_DIR, 'data', 'not_found.csv'), 'w')
        writer = csv.DictWriter(not_found_file, delimiter=';',
                                fieldnames=['issn', 'eissn_list', 'names_list', 'country', 'url', 'invalid_list'])
        writer.writeheader()

        reader = csv.DictReader(file, delimiter=';', quotechar='"')
        tot_lidos = 0
        tot_invalidos = 0
        tot_validados = 0
        tot_inexistente = 0
        for line in reader:
            tot_lidos += 1

            issn = line['CD_IDENTIFICADOR_VEICULO']
            if not issn:
                continue

            issn = issn.upper()
            if not validate_issn_code(issn):
                tot_invalidos += 1
                logging.error('ISSN Inválido %s' % issn)
                continue

            periodico = Periodico.objects.filter(issn=issn).first()
            if not periodico:
                periodico = Periodico.objects.filter(eissn=issn).first()
                if not periodico:
                    tot_inexistente += 1
                    if issn in issn_not_found:
                        issn_not_found[issn] += 1
                    else:
                        issn_not_found[issn] = 1
                        issn_record = get_issn(issn)
                        if isinstance(issn_record, dict):
                            print(f'ISSN {issn} existe mas não está no Odorico')
                            writer.writerow(issn_record)
                        else:
                            logging.error('ISSN inexistente: %s' % issn)
                            continue

            tot_validados += 1
            if tot_lidos % 500 == 0:
                print('Lidos:%d - Validados:%d' % (tot_lidos, tot_validados))

        not_found_file.close()
        logging.info(f'Total de registros lidos: {tot_lidos}')
        logging.info(f'Total de Validados: {tot_validados}')
        logging.info(f'ISSN inválidos: {tot_invalidos}')
        logging.info(f'Inexistentes no Odorico: {tot_inexistente}')
