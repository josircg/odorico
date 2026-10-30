# Processamento utilizado para marcar a área de conhecimento interna
# a partir das keywords
# Faz parte do estudo de periódicos de Comunicação e CI
#
# 07/2024


import os
import time
import logging

from collections import Counter
from csv import DictWriter, QUOTE_NONNUMERIC

from django.conf import settings
from django.core.management import BaseCommand

from qualis.models import Periodico, PeriodicoAssunto, Assunto, AreaConhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/area_keywords.log", mode='a'),
        logging.StreamHandler()
    ]
)


class Command(BaseCommand):

    def handle(self, *args, **options):

        time_begin = time.time()
        comunicacao = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')
        tot_comunicacao = 0
        tot_lidos = 0
        for periodico in Periodico.objects.filter(status='A', area__isnull=True, keywords__isnull=False):
            tot_lidos += 1
            if tot_lidos % 1000 == 0:
                logging.info(f'Lidos:{tot_lidos}')

            # rotina específica para encontrar periódicos de Comunicação
            # media, mass communication, journalism, media research, social communication, media systems
            fator_comunicacao = 0
            # Se comunicação for a primeira keyword, aumentar o fator
            primeiro = 2

            # Se certificando que está sem duplicados
            keywords = periodico.keywords.split(',')
            for index, keyword in enumerate(keywords):
                keywords[index] = keyword.lower()
            keywords = set(keywords)

            for keyword in keywords:
                clean_keyword = keyword.strip()
                if clean_keyword in (
                        'media', 'mass communication', 'journalism', 'media research',
                        'communication science',
                        'communication', 'social communication', 'communication media', 'cinema',
                        'television', 'public relations', 'film studies', 'advertising',):
                    fator_comunicacao += 2 + primeiro
                elif clean_keyword in ('cultural studies', 'semiotics', 'media studies',):
                    fator_comunicacao += 1
                else:
                    fator_comunicacao -= 1 + primeiro
                primeiro = 0

            if fator_comunicacao > 2:
                periodico.area = comunicacao
                tot_comunicacao += 1

            periodico.save()

        time_end = time.time()
        t = time_end - time_begin

        logging.info(f'Total de periódicos lidos: {tot_lidos}')
        logging.info(f'Total de Comunicação incluídos: {tot_comunicacao}')
        logging.info('Tempo de Processamento: %s minutos' % (round(t / 60, 2)))
