import urllib3

from django.conf import settings
from django.core.management import BaseCommand

from nucleo.apps import get_issn, validate_issn_code, log_object
from qualis.models import Periodico, PeriodicoISSN

import requests
from bs4 import BeautifulSoup


def extrair_dados_issn(issn):
    # 1. Definir um 'User-Agent' para o site não bloquear o acesso automático
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # 2. Fazer o pedido ao site
        url = f'https://portal.issn.org/resource/ISSN/{issn}'
        resposta = requests.get(url, headers=headers)
        resposta.raise_for_status()  # Verifica se houve erro de ligação

        # 3. Preparar o "analisador" de HTML
        soup = BeautifulSoup(resposta.text, 'html.parser')

        dados = {}

        titulo_tag = soup.find(class_='record__title')
        if titulo_tag:
            # Limpamos espaços extras e quebras de linha
            dados['Title'] = titulo_tag.get_text(strip=True).replace('Key title:','')

        for dt in soup.find_all('dt'):
            label = dt.get_text(strip=True).lower()
            # O valor está logo a seguir ao termo (o próximo elemento irmão)
            dd = dt.find_next_sibling('dd')

            if dd:
                valor = dd.get_text(strip=True)

                if 'issn-l' in label:
                    dados['ISSN-L'] = valor
                elif 'issn' in label and 'l' not in label and 'h' not in label:
                    dados['ISSN'] = valor
                elif 'country' in label:
                    # Muitas vezes o país tem o nome e o código, limpamos aqui
                    dados['Country'] = valor.split('-')[0].strip().capitalize()
                elif 'issn-h' in label:
                    dados['ISSN-H'] = valor

        dados["links"] = []
        for container in soup.find_all(attrs={"data-key": "other-media"}):
            # Dentro deste container, procuramos todos os links
            links = container.find_all('a')
            for link in links:
                texto = link.get_text(strip=True)
                href = link.get('href')
                if href:
                    dados["links"].append({texto: href.split('/')[-1]})
        return dados

    except Exception as e:
        return f"Erro ao aceder à página: {e}"


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--issn', type=str, help='ISSN Code')

    def handle(self, *args, **options):
        urllib3.disable_warnings()
        issn = options['issn']
        dados = get_issn(issn)
        print(dados)

    def handle_validate(self, *args, **options):
        issn = options['issn']
        urllib3.disable_warnings()
        if not validate_issn_code(issn):
            print('Código de ISSN Inválido %s' % issn)
            exit(1)

        #issn_record = get_issn_old(issn, extended=True)
        #print(issn_record)

