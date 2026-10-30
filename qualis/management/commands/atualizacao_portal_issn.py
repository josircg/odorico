#
# Rotina de atualização dos países e URL a partir do Portal ISSN
#
# A partir dos periódicos que não tem países, busca os dados diretamente do portal do ISSN
#
import csv
import datetime
from decimal import Decimal
import logging
import time

from collections import Counter

from django.core.management import BaseCommand

from utils.stdlib import is_empty
from nucleo.apps import get_issn, validate_issn_code
from qualis.models import Periodico, PeriodicoISSN, AreaConhecimento, Pais

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-3.3s] %(message)s",
    handlers=[
        logging.FileHandler("logs/sempaises.log", mode='a'),
        logging.StreamHandler()
    ]
)

from urllib.parse import urlparse


def obter_sufixo_nativo(url):
    """
    Extrai o TLD final de uma URL sem bibliotecas externas.
    """
    # 1. Adiciona o esquema (http) caso o usuário forneça apenas "www.site.com"
    # O urlparse precisa do protocolo para funcionar corretamente.
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    # 2. Extrai o "netloc" (ex: www.google.com.br)
    dominio_completo = urlparse(url).netloc

    # 3. Divide o domínio pelos pontos
    partes = dominio_completo.split('.')

    # 4. Retorna a última parte (o TLD final)
    if len(partes) > 1:
        return partes[-1]
    return None


class Command(BaseCommand):

    def handle(self, *args, **options):
        time_begin = time.time()

        paises = Counter()
        logging.info(f'Importação via Portal ISSN')
        comunicacao = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')
        tot_lidos = 0
        tot_atualizados = 0
        tot_invalidos = 0
        tot_comunicacao = 0
        #dtvalidacao = datetime.datetime.today().replace(hour=0,minute=0,second=0,microsecond=0)
        # select count(*) from qualis_periodico where status in ('I','F') and dtupdate > '2026-01-01';
        dtvalidacao = datetime.datetime(year=2026, month=1, day=1)
        for periodico in Periodico.objects.filter(status__in=('I','F'),
                                                  dtupdate__gt=dtvalidacao,
                                                  dtupdate__lt=dtvalidacao.replace(month=4,day=26)):
        #for periodico in Periodico.objects.filter(pais__isnull=True, status='A',
        #                                          dtvalidacao__lt=dtvalidacao):
            tot_lidos += 1
            if tot_lidos % 100 == 0:
                logging.info(f'Lidos:{tot_lidos} - Atualizados:{tot_atualizados} - Inválidos:{tot_invalidos}')

            issn_busca = periodico.issn
            issn_record = get_issn(issn_busca)
            if not isinstance(issn_record, dict):
                logging.error(f'ISSN não encontrado {issn_busca} {issn_record}')
                tot_invalidos += 1
                if periodico.status != 'F':
                    periodico.status = 'F'
                    if '400' not in issn_record:
                        periodico.historico = periodico.historico or issn_record[:80]
                periodico.dtvalidacao = dtvalidacao
                periodico.save()
                continue

            atualizado = False
            issn = issn_record['issn']
            eissn_list = issn_record['eissn_list']
            titles = issn_record['names_list']
            country = issn_record.get('country')
            if country:
                country = country[:100]

            if periodico.status != 'A':
                periodico.status = 'A'
                atualizado = True

            if issn_busca != issn:
                if Periodico.objects.filter(issn=issn).exists():
                    print(f'ISSN-L {issn_busca} marcado como duplicado')
                    periodico.status = 'F'
                    periodico.historico = 'Duplicado'
                    periodico.save()
                    tot_invalidos += 1
                    continue
                else:
                    print(f'ISSN-L encontrado:{issn} busca:{issn_busca}')
                    periodico.issn = issn
                    atualizado = True

            if len(eissn_list) > 0 and (is_empty(periodico.eissn) or periodico.eissn == periodico.issn):
                if len(eissn_list[0]) == 9:
                    periodico.eissn = eissn_list[0]
                    atualizado = True
                else:
                    print(f'Erro na lista de eissn {eissn_list}')

            if not periodico.referencia:
                menor_nome = None
                for nome in titles:
                    if menor_nome is None or (nome and len(nome) < len(menor_nome)):
                        menor_nome = nome
                if menor_nome and menor_nome.lower() != periodico.nome.lower():
                    periodico.referencia = menor_nome[:80]
                    atualizado = True

            if issn_record['url'] and not periodico.url:
                periodico.url = issn_record['url'][:300]
                atualizado = True

            if country == 'International':
                if periodico.url:
                    tld = obter_sufixo_nativo(periodico.url)
                    if tld:
                        pais = Pais.objects.filter(tld=tld).first()
                        if pais:
                            periodico.pais = pais.name
                            paises[periodico.pais] += 1
                            atualizado = True
            else:
                if country and periodico.pais != country:
                    periodico.pais = country
                    paises[periodico.pais] += 1
                    atualizado = True

            # Ajusta Keywords, removendo o "and"
            if periodico.keywords:
                primary_keywords = periodico.keywords.lower().split(',')
                final_keywords = []
                for keyword in primary_keywords:
                    if any(palavra in keyword for palavra in ('studies','education')):
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

                keywords = ','.join(sorted(set(keywords)))
                if keywords != periodico.keywords:
                    periodico.keywords = keywords
                    atualizado = True

                if fator_comunicacao > 1 and periodico.area is None:
                    print(f'Comunicação: {periodico.issn}: {keywords}')
                #   periodico.area = comunicacao
                #   periodico.save()
                    tot_comunicacao += 1

            if atualizado:
                tot_atualizados += 1
                periodico.dtvalidacao = dtvalidacao
                periodico.save()
                for code in issn_record['eissn_list']:
                    if validate_issn_code(code):
                        filho, _ = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=code)
                        filho.meio = 'E' if filho.meio is None else filho.meio
                        filho.save()

        time_end = time.time()
        t = time_end - time_begin

        logging.info(f'Registros lidos: {tot_lidos}')
        logging.info(f'Periódicos inválidos: {tot_invalidos}')
        logging.info(f'Periódicos atualizados: %d' % tot_atualizados)
        logging.info(f'Periódicos Comunicação: %d' % tot_comunicacao)
        logging.info(f'Tempo de Processamento: %s minutos' % (round(t / 60, 2)))

        with open('tot_paises.csv', 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(paises.items())
