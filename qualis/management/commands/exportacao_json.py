# Processamento utilizado para exportar todos os periódicos
# Utilizado inicialmente no artigo de Periódicos Odorico na Revista Encontros Bibli
# Em 06/2024, foi adicionado a lista de keywords

import os
import datetime
import json
import logging
import time

from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict
from collections import Counter

from django.conf import settings
from django.core.management import BaseCommand

from qualis.models import Periodico, PeriodicoAssunto, PeriodicoISSN, PeriodicoIndicador

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/exportacao_json.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato JSON')

    def handle(self, *args, **options):
        filename = os.path.join(settings.BASE_DIR, 'media', options['arquivo'])
        if os.path.exists(filename):
            print(f'Arquivo {filename} já existe')
            return

        time_begin = time.time()
        file = open(filename, 'w', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')

        tot_lidos = 0
        schemas = Counter()
        limite = datetime.date(year=2025, month=6, day=1)
        for periodico in Periodico.objects.filter(dtupdate__gte=limite).order_by('id'):
            tot_lidos += 1
            #if tot_lidos > 1000:
            #    break

            if tot_lidos % 1000 == 0:
                logging.info(f'Lidos:{tot_lidos}')

            record = model_to_dict(periodico)
            record = {k: v for k, v in record.items() if v is not None}
            record['dtvalidacao'] = periodico.dtvalidacao

            issn_list = []
            for item in PeriodicoISSN.objects.filter(periodico=periodico):
                record_dict = model_to_dict(item)
                del record_dict['id']
                del record_dict['periodico']
                issn_list.append(record_dict)

            indicadores_list = []
            for item in PeriodicoIndicador.objects.filter(periodico=periodico).select_related('schema', 'area__schema'):
                schemas[item.schema.sigla] += 1
                indicador = {
                    'schema': item.schema.sigla,
                    'cod_externo': item.area.cod_externo if item.area else None,
                    'classe': item.classe,
                    'indicador': item.indicador}
                indicadores_list.append( indicador )

            assunto_list = []
            for item in PeriodicoAssunto.objects.filter(periodico=periodico).select_related('assunto', 'assunto__schema'):
                if item.assunto and item.assunto.cod_externo:
                    schemas[item.assunto.schema.sigla] += 1
                    assunto_list.append({
                        'schema': item.assunto.schema.sigla,
                        'cod_externo': item.assunto.cod_externo,
                        'ordem': item.ordem
                    })

            record['issn_list'] = issn_list
            record['assunto_list'] = assunto_list
            record['indicadores_list'] = indicadores_list
            file.write(json.dumps(record, cls=DjangoJSONEncoder))
            file.write('\n')

        file.close()
        time_end = time.time()
        t = time_end - time_begin

        logging.info(f'Total de periódicos processados: {tot_lidos}')
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
        logging.info(f'{schemas.most_common()}')

        filename = os.path.join(settings.BASE_DIR, 'media', 'schemas_' + options['arquivo'])
        file = open(filename, 'w', encoding='utf-8')
        file.write(json.dumps(list(schemas.keys())))
        file.write('\n')
        file.close()


