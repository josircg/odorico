# Processamento utilizado para exportar todos os periódicos
# Utilizado inicialmente no artigo de Periódicos Odorico na Revista Encontros Bibli
# Em 06/2024, foi adicionado a lista de keywords

import os
import time
import logging

from collections import Counter
from csv import DictWriter, QUOTE_NONNUMERIC

from django.conf import settings
from django.core.management import BaseCommand

from qualis.models import Periodico, PeriodicoAssunto, Assunto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/exportacao.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', type=str, help='Nome do arquivo em formato CSV')
        parser.add_argument('--area', type=int, help='Código da Área')

    def handle(self, *args, **options):
        filename = os.path.join(settings.BASE_DIR, 'media', options['arquivo'])
        if os.path.exists(filename):
            print(f'Arquivo {filename} já existe')
            return

        time_begin = time.time()

        file = open(filename, 'w', encoding='utf-8')
        logging.info(f'Processando arquivo {filename}')

        fieldnames = ['ISSN', 'eISSN', 'Título', 'ASJC', 'Área', 'Qualis', 'Qualis Ant', 'Openalex H5', 'Google H5',
                      'Citescore', 'SJR', 'URL', 'País', 'Modelo', 'Keywords']
        writer = DictWriter(file, delimiter=';', quotechar='"', fieldnames=fieldnames,
                            quoting=QUOTE_NONNUMERIC)
        writer.writeheader()

        tot_lidos = 0
        dataset = Periodico.objects.filter(status='A')
        if options['area']:
            dataset.filter(area=options['area'])

        for periodico in dataset:
            tot_lidos += 1
            if tot_lidos % 1000 == 0:
                logging.info(f'Lidos:{tot_lidos}')
            record = {
                'ISSN': periodico.issn,
                # Código ISSN específico da publicação online;
                'eISSN': periodico.eissn,
                # Título completo sem abreviações ou extensões do tipo (ONLINE) ou (PRINT);
                'Título': periodico.nome,
                'Área': periodico.area.id if periodico.area else None,
                'Qualis': periodico.qualis,
                'Qualis Ant': periodico.qualis_ant
            }

            # AJSC: Descrição da Área segundo a Scopus. Caso exista mais de um, a descrição será separada por vírgula;
            asjc = PeriodicoAssunto.objects. \
                filter(periodico=periodico, assunto__schema__sigla='ASJC'). \
                values_list('assunto__cod_externo', flat=True)
            record['ASJC'] = ','.join(asjc)

            # keywords
            keywords = list(PeriodicoAssunto.objects.
                            filter(periodico=periodico, assunto__schema__sigla__in=('ASJC', 'WOS')).
                            values_list('assunto__descricao', flat=True))
            if periodico.keywords:
                keywords += periodico.keywords.split(',')
            ordered_keywords = Counter(keywords).most_common()
            record['Keywords'] = ','.join([x[0] for x in ordered_keywords])

            # Qualis: Estrato Qualis referente publicado em 2023 (Quadriênio 2017-2020) ou ND
            record['Qualis'] = periodico.qualis
            # OpenAlex H5: Índice H5 referente a 2024
            record['Openalex H5'] = periodico.oalex_h5
            # Google H5M: Índice H5 Mediana referente a 2020 calculado pelo Google (pode conter nulos)
            record['Google H5'] = periodico.google_h5
            # Citescore: ìndice Citescore da Scopus (pode conter nulos)
            record['Citescore'] = periodico.citescore
            # SJR: Índice SJR (pode conter nulos)
            record['SJR'] = periodico.sjr
            # URL: Endereço do periódico na web (pode conter nulos)
            record['URL'] = periodico.url
            # País: País da Editora do Periódico (pode conter nulos)
            record['País'] = periodico.pais
            # Modelo: Modelo Econômico - pode assumir 3 valores:
            # Diamond, APC e Bloqueado. Onde Diamond indica periódicos de acesso aberto sem nenhum tipo de cobrança
            # ou restrição de acesso. APC (Article Processing Charges) indica que o periódico cobra o autor e
            # Trancado indica que o acesso ao conteúdo é restrito apenas a quem paga por ele.'
            record['Modelo'] = periodico.modelo_economico
            writer.writerow(record)

        time_end = time.time()
        t = time_end - time_begin

        logging.info('Total de periódicos incluídos: %d' % tot_lidos)
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
