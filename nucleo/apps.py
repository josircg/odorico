from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from crossref.restful import Etiquette, Works
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.db.models.signals import post_save
from django.http import Http404
from django.utils.html import format_html
from django.utils.text import slugify
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_H
from stdnum import issn
from datetime import date

from crawler import get_cache, save_cache, get_page
from nucleo import clean_doi_url, doi_hashed, normalize_name

from .signals import aluno_post_save

URL_CNPQ = 'http://dgp.cnpq.br/dgp/espelhorh/%s'
URL_LATTES_VIEW = 'http://buscatextual.cnpq.br/buscatextual/visualizacv.do?id=%s&tipo=completo&idiomaExibicao=1'
URL_LATTES_XML = 'https://buscatextual.cnpq.br/buscatextual/download.do?metodo=apresentar&idcnpq=%s'


class NucleoConfig(AppConfig):
    name = 'nucleo'
    app_label = 'Núcleo'

    def ready(self):
        super().ready()
        post_save.connect(aluno_post_save, sender='nucleo.Aluno', dispatch_uid='aluno_post_save')


def get_sys_user():
    from django.contrib.auth.models import User
    user, _ = User.objects.get_or_create(username='sys')
    return user


def log_object(obj, mensagem, inclusao=False):
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.admin.models import LogEntry, ADDITION, CHANGE

    LogEntry.objects.log_action(
        user_id=get_sys_user().pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=u'%s' % obj,
        action_flag=ADDITION if inclusao else CHANGE,
        change_message=mensagem
    )


def intdef(s, default=None):
    """
    :s: string a converter
    :return: número inteiro
    """
    try:
        return int(s)
    except:
        return default


def clean_orcid(orcid):
    if not isinstance(orcid, str):
        return None

    orcid = ''.join(orcid.split())
    # Se a string ficou vazia após o split/join, retorna None
    if not orcid:
        return None

    orcid = orcid.replace('http://orcid.org/', '').replace('https://orcid.org/', '').replace(' ', '')

    if 'http:' in orcid:
        return None

    return orcid


def clean_texto(texto: str | None):
    if texto in EMPTY_VALUES:
        return None
    else:
        return texto.strip()


def get_cnpq_page(id_cnpq):
    soup = get_cache(f'cnpq_{id_cnpq}')
    if not soup:
        url = URL_CNPQ % id_cnpq
        soup = get_page(url, True, 30)
        if soup:
            save_cache(f'cnpq_{id_cnpq}', soup)
    return soup


def obtem_nome_cnpq(id_cnpq):
    nome = None
    soup = get_cnpq_page(id_cnpq)
    if soup:
        for lbl in soup.find_all('div', attrs={'class': 'ac'}):
            nome = lbl.findNext('h1').text
        if not nome:
            nome = soup.find('div', attrs={'class': 'controls'})
            if nome:
                nome = nome.text.split(';')[0].strip()
    return clean_texto(nome)


# Retorna a data de atualização do currículo no CNPQ ou Nulo caso não encontre o id_cnpq
def obtem_dt_cnpq(id_cnpq):
    soup = get_cnpq_page(id_cnpq)
    if soup:
        for lbl in soup.find_all('label', attrs={'class': 'control-label'}):
            if lbl.next == 'Última atualização do Currículo Lattes:':
                try:
                    texto = lbl.findNext('div').text
                    texto = re.sub(r"[\n\t\s]*", "", texto)
                    return datetime.strptime(texto, '%d/%m/%Y').date()
                except ValueError:
                    return None

        for lbl in soup.find_all('h4', attrs={'class': 'layout-cell-17'}):
            if 'result returns more than one elements' in lbl.text:
                return datetime.today().date()


def validate_id_cnpq(id_cnpq):
    if id_cnpq:
        try:
            id_cnpq = id_cnpq.strip()
            dt_cnpq = obtem_dt_cnpq(id_cnpq)
        except Exception as e:
            raise ValidationError('Consulta ao CNPQ fora do ar')
        if not dt_cnpq:
            raise ValidationError('ID CNPQ não existe')


# https://www.rfc-editor.org/rfc/rfc8254
def validate_issn_code(code):
    try:
        if 0 < len(code) < 8:
            code = code.zfill(8)
        if '-' not in code:
            code = issn.format(code)
        if issn.validate(code):
            return code
        else:
            return None
    except:
        return None


def get_issn(issn):
    """
    :param issn: issn code (or e-issn or issn-l)
    :return: dict(issn, eissn_list, names_list, country, url, invalid_list, status) ou uma string caso não exista
    """
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

        dados = {'issn': None, 'names_list': [], 'eissn_list': [], 'invalid_list': [],
                 'country': None, 'url': None, 'status': 'Active'}
        lista_issn = []
        titulo_tag = soup.find(class_='record__title')
        if titulo_tag:
            # Retira espaços extras e quebras de linha
            dados['names_list'].append(titulo_tag.get_text(strip=True).replace('Key title:', ''))

        '<span data-category="fre" >Unassigned or unreported ISSN</span>'
        status = soup.find('span', attrs={"data-category": "fre"})
        if status:
            status_text = status.get_text(strip=True)
            if 'Unassigned or unreported' in status_text:
                return 'Unassigned ISSN'

        '<span data-category="sup">Suppressed ISSN</span>'
        status = soup.find('span', attrs={"data-category": "sup"})
        if status:
            return 'Supressed ISSN'

        '<span data-category="can">Cancelled ISSN</span>'
        status = soup.find('span', attrs={"data-category": "can"})
        if status:
            return 'Cancelled ISSN'

        '<span data-category="wor">Provisional</span>'
        status = soup.find('span', attrs={"data-category": "wor"})
        if status:
            dados['issn'] = issn
            dados['status'] = 'Provisional'

        '<span class="text--grey text--s text--medium text--lining-numbers" data-cancelled-issn="0177-1094">'
        for span_cancelado in soup.find_all('span', attrs={"data-cancelled-issn": True}):
            dados['invalid_list'].append(span_cancelado['data-cancelled-issn'])

        '<span class="text--grey text--s text--medium text--lining-numbers" data-incorrect-issn="0091-3642">'
        for span_cancelado in soup.find_all('span', attrs={"data-incorrect-issn": True}):
            dados['invalid_list'].append(span_cancelado['data-incorrect-issn'])

        for dt in soup.find_all('dt'):
            label = dt.get_text(strip=True).lower()
            # O valor está logo a seguir ao termo (o próximo elemento irmão)
            dd = dt.find_next_sibling('dd')

            if dd:
                valor = dd.get_text(strip=True)
                if 'issn-l' in label:
                    if dados['issn'] is None:
                        dados['issn'] = valor
                    else:
                        lista_issn.append(valor)
                elif 'issn' in label and 'l' not in label and 'h' not in label:
                    for issn in valor.split(','):
                        lista_issn.append(issn.strip())
                elif 'country' in label or 'issn center responsible for the record' in label:
                    # Muitas vezes o país tem o nome e o código, limpamos aqui
                    if not dados['country']:
                        dados['country'] = valor.split('-')[0].strip().capitalize()

        title = soup.find(attrs={"data-key": "title-proper"})
        if title:
            dados['names_list'].append(title.get_text(strip=True))

        url = soup.find('li', attrs={"data-key": "resource-link"})
        if url:
            url = url.find('a')
            dados['url'] = url.get('href')

        for container in soup.find_all(attrs={"data-key": "other-media"}):
            # Dentro deste container, procuramos todos os links
            links = container.find_all('a')
            for link in links:
                href = link.get('href')
                if href:
                    lista_issn.append(href.split('/')[-1])

        if not dados['issn']:
            dados['issn'] = issn

        dados["eissn_list"] = [issn.strip() for issn in lista_issn if issn != dados['issn']]
        return dados

    except Exception as e:
        return f"Erro ao acessar a página: {e}"


def get_issn_old(code, extended=False):
    """
    :param code: issn code (or e-issn or issn-l)
    :param extended: return all possible names from other linked issns
    :return: dict(issn, eissn_list, names_list, country, url, invalid_list) ou uma string com a mensagem de erro
    """
    code_issn = validate_issn_code(code)
    try:
        response = requests.get('https://portal.issn.org/resource/ISSN/%s?format=json' % code, timeout=30, verify=False)
        if response.status_code == 200:
            dados = response.json()
        else:
            return f'{response.status_code}'
    except Exception as e:
        return '%s' % e

    try:
        graph = dados['@graph']
    except:
        print('ISSN Wrong JSON format: %s' % code)
        return 'NF'
    names = []
    invalid_issn = []
    code_eissn = []
    country = None
    url = None
    for res in graph:

        res_id = res.get('@id', '')

        if 'mainTitle' in res:
            lista = res['mainTitle']
            if type(lista) == str:
                lista = [lista]
            for item in lista:
                names.append(item.strip('.').strip().upper())

        if '#KeyTitle' in res_id and 'value' in res:
            lista = res['value']
            if type(lista) == str:
                lista = [lista]
            for item in lista:
                names.append(item.strip('.').strip().upper())

        if 'vocabulary/countries' in res_id:
            country = res['label'].capitalize()

        if res.get('isPartOf'):
            temp_code = res.get('isPartOf').split('/')[-1]
            if temp_code != code:
                code_eissn.append(code)
                code_issn = temp_code

        if res.get('isFormatOf'):
            lista = res.get('isFormatOf')
            if type(lista) == str:
                if code_issn != lista.split('/')[-1]:
                    code_eissn.append(lista.split('/')[-1])
            else:
                # obtem aqui apenas o primeiro e-issn
                for item in lista:
                    if code_issn != item.split('/')[-1]:
                        code_eissn.append(item.split('/')[-1])

        if res_id == 'resource/ISSN/%s' % code_issn:
            if res.get('url'):
                url = res.get('url')

        if 'resource/ISSN/' in res_id:
            incorret_issn = res.get('hasIncorrectISSN')
            if incorret_issn:
                if isinstance(incorret_issn, list):
                    invalid_issn += incorret_issn
                else:
                    invalid_issn.append(incorret_issn)

    # Remove os issn filhos duplicados
    code_eissn = list(dict.fromkeys(code_eissn))
    code_eissn.sort()

    if extended:
        if code_issn and code != code_issn:
            link_record = get_issn(code_issn)
        elif len(code_eissn) > 0 and code != code_eissn[-1]:
            link_record = get_issn(code_eissn[-1])
        else:
            link_record = None

        if isinstance(link_record, dict):
            names += list(set(link_record['names_list']) - set(names))
            if not country:
                country = link_record['country']
            if not url:
                url = link_record['url']

    return {'issn': code_issn, 'eissn_list': code_eissn, 'names_list': names, 'invalid_list': invalid_issn,
            'country': country, 'url': url}


def get_page_atribs(soup):
    atribs = {}
    if type(soup) is int:
        return atribs

    for meta in soup.find_all('meta'):
        if 'name' in meta.attrs and 'content' in meta.attrs:
            name = meta.attrs['name'].lower()
            if name == 'citation_title': name = 'title'
            if name == 'dc.title': name = 'title'
            if name == 'dc.identifier':
                scheme = meta.attrs.get('scheme', 'none')
                if scheme.lower() == 'issn':
                    atribs['citation_issn'] = [meta.attrs['content']]
            if name == 'keywords':
                atribs[name] = []
                for key in meta.attrs['content'].split(','):
                    for key2 in key.split(';'):
                        atribs[name].append(key2.lower().strip())
            else:
                if not atribs.get(name):
                    atribs[name] = [meta.attrs['content']]
                else:
                    atribs[name].append(meta.attrs['content'])

        if 'http-equiv' in meta.attrs and 'content' in meta.attrs:
            url = meta.attrs['content'].split('Redirect=')
            if len(url) == 2:
                url = url[1].split('%3F')[0].replace('%2F', '/').replace('%3A', ':')
                try:
                    redirect_soup = get_page(url)
                except:
                    redirect_soup = None
                if redirect_soup:
                    atribs = get_page_atribs(redirect_soup)
                else:
                    try:
                        redirect_soup = get_page(url.split('&')[0])
                        if redirect_soup:
                            atribs = get_page_atribs(redirect_soup)
                    except:
                        atribs = {}
                break
    return atribs


# 404: Não encontrado, 403: Existe mas está bloqueado, None: DOI Inválido
def get_doi_record(url_doi, fast=False):
    soup = get_doi_content(url_doi, fast)
    if soup:
        atribs = get_page_atribs(soup)
        soup = 200
    else:
        atribs = {}

    # Buscar também os dados via CrossRef
    etiquette = Etiquette('Odorico', settings.VERSION,
                          settings.API_IDENTIFIER, settings.DEFAULT_FROM_EMAIL)
    works = Works(etiquette=etiquette)
    crossref = works.doi(url_doi)
    if not crossref:
        if soup == 200:
            return atribs
        else:
            return soup
    else:
        if crossref.get('type', '') == 'journal':
            return {}
        else:
            atribs = {**atribs, **crossref, 'provenance': 'CrossRef'}

    return atribs


def generate_hash(texto=''):
    #
    # gera um hash hexadecimal de 32 caracteres a partir de uma string
    # caso a string esteja em branco gera um uuid aleatório
    #
    if len(texto) > 0:
        texto = slugify(normalize_name(texto))
        return hashlib.md5(texto.encode('utf-8')).hexdigest()
    else:
        return uuid.uuid4().hex


def generate_24hash(texto='', data_base=None):
    #
    # gera um hash a partir de uma string que contém a data em que ele foi gerado
    # dessa forma, cria-se um hash para um dia específico (ou para o dia corrente)
    #
    if len(texto) > 0:
        texto = slugify(normalize_name(texto + settings.SECRET_KEY))
        md5 = hashlib.md5(texto.encode('utf-8')).hexdigest()
        data_esperada = data_base or datetime.today()
        hash_date = data_esperada.strftime('%Y-%m-%d-') + settings.SECRET_KEY
        hash_date = hashlib.md5(hash_date.encode('utf-8')).hexdigest()
        return f'{md5}-{hash_date}'
    return None


def validate_24hash(texto='', hash_code=''):
    #
    # valida se um hash gerado  pela função generate_24hash no dia corrente ou no dia anterior é válido a partir de um texto base
    #
    if len(texto) > 0:
        if generate_24hash(texto) == hash_code:
            return True
        else:
            ontem = datetime.today() - timedelta(days=1)
            if generate_24hash(texto, ontem) == hash_code:
                return True
    return False


def parse_titulo(titulo):
    #
    # encontra o título do artigo/trabalho partir de um registro do Lattes HTML ou de uma referência ABNT
    #
    # Exemplo:
    # PECI, A. ; FORNAZIN, M. . The knowledge-building process of public administration research: a comparative
    # perspective between Brazil and North American contexts. INTERNATIONAL REVIEW OF ADMINISTRATIVE SCIENCES,
    # v. 83, p. 99-119, rint; Meio de divulgação: Digital. Homepage: ; Série: 1;
    #
    if '. .' in titulo:
        result = titulo.split('. .')[1]
    elif '..' in titulo:
        result = titulo.split('..')[1]
    elif ' . ' in titulo:
        result = titulo.split(' . ')[1]
    else:
        result = ''

    if not result:
        ultima = titulo.split('. ')
        if len(ultima) > 1:
            result = ultima[1]

    if '.' in result:
        result = result.split('.')[0]

    # se o resultado for muito pequeno, então a rotina não funcionou
    if len(result) < 15:
        result = titulo

    # limpa espaços extras
    result = ' '.join(result.split())

    return result


def get_doi_content(doi, fast=False):
    clean_doi = clean_doi_url(doi)
    if not clean_doi:
        return None

    hash_doi = doi_hashed(clean_doi)
    soup = get_cache(hash_doi)
    if not soup:
        if 'http' not in doi:
            url = 'https://doi.org/' + doi
        else:
            url = doi
        try:
            soup = get_page(url, fast)
            save_cache(hash_doi, soup)
        except:
            soup = None
    return soup


def get_issn_from_doi(url):
    soup = get_doi_content(url)
    if soup:
        metas = soup.find_all("meta")
        for meta in metas:
            atrib = meta.get('name')
            if atrib and atrib.lower() == 'dc.source.issn':
                return meta.get('content')
        for linha in soup.text.split('\n'):
            if linha and 'issn' in linha.lower():
                try:
                    result = linha.lower().split('issn')[1]
                    result = ''.join(c for c in result if c not in '"(){}<>:,.')[0:9]
                    issn.validate(result)
                    return result
                except:
                    None
    return None


def get_doi_metadata(url):
    soup = get_doi_content(url, True)
    if type(soup) != int:
        metas = soup.find_all("meta")
        for meta in metas:
            atributo = meta.get('name')
            if atributo == 'DC.Source.ISSN':
                return meta.get('content')
    return None


def doi_record_to_producao(doi, doi_record):
    """Faz o de/para do dicionário doi_record, para os campos da classe Producao"""

    def de_para(src, dest):
        """doi_record é um dicionário cujo o valor de cada chave é uma lista"""
        value = doi_record.get(src, [])
        if type(value) == list and len(value) > 0:
            value = value[0]

        if type(value) == str:
            result[dest] = value.strip()
        elif value:
            result[dest] = value

    result = {'doi': doi}
    de_para('title', 'titulo')
    try:
        de_para('language', 'idioma')
        de_para('dc.language', 'idioma')
        de_para('ISSN', 'serie')
        de_para('dc.source.issn', 'serie')
        de_para('dc.source.volume', 'volume')
        de_para('volume', 'volume')
        de_para('dc.date.issued', 'date')
        de_para('publisher', 'editora')
        de_para('citation_isbn', 'isbn')
        if result.get('date'):
            result['ano'] = int(result['date'].split('-')[0])
        elif doi_record.get('published-online'):
            result['ano'] = doi_record['published-online']['date-parts'][0][0]
        elif doi_record.get('published-print'):
            result['ano'] = doi_record['published-print']['date-parts'][0][0]
        elif doi_record.get('citation_publication_date'):
            result['ano'] = doi_record['citation_publication_date'][0]

    except Exception as e:
        print(f'{e}')
    return result


def save_doi(doi, doi_record):
    basedir = os.path.join(settings.BASE_DIR, 'cache')
    filename = os.path.join(basedir, '%s.json' % doi_hashed(doi))
    if not os.path.isdir(basedir):
        os.mkdir(basedir)
    with open(filename, 'w') as final_file:
        json.dump(doi_record, final_file)


def gerar_tabela_disciplinas(aluno):
    from nucleo.models import Inscricao
    inscricoes = Inscricao.objects.filter(aluno=aluno).select_related("turma__disciplina", "turma__periodo")

    periodos = defaultdict(list)
    for insc in inscricoes:
        disciplina = insc.turma.disciplina
        periodo = f'{insc.turma.periodo.ano}/{insc.turma.periodo.ident}'
        periodos[periodo].append((disciplina, insc))  # inclui a inscrição junto

    html = """
    <table class="historico-escolar-tabela">
      <thead>
        <tr>
          <th>Período</th>
          <th>Código</th>
          <th>Nome da Disciplina/RCC</th>
          <th>CrR</th>
          <th>CH</th>
          <th>Grau</th>
          <th>CrO</th>
          <th>Pontos</th>
          <th>SF/CR</th>
        </tr>
      </thead>
      <tbody>
    """

    acumulado = {"crr": 0, "ch": 0, "cro": 0, "pontos": 0}

    for periodo, lista in sorted(periodos.items()):
        # Se for um período especial (exemplo: trancado), insere linha informativa
        if not lista:
            html += f"""
            <tr>
                <td>{periodo}</td>
                <td colspan="8" style="text-align: left; font-style: italic; color: #666;">Matrícula trancada</td>
            </tr>
            """
            continue
        rowspan = len(lista) + 2
        html += f'<tr class="historico-escolar-inicio-periodo"><td rowspan="{rowspan}" style="vertical-align: middle;">{periodo}</td>'

        primeira = True
        totais_periodo = {"crr": 0, "ch": 0, "cro": 0, "pontos": 0}

        for disciplina, inscricao in lista:
            if not primeira:
                html += "<tr>"
            primeira = False

            crr = disciplina.creditos or 0
            ch = disciplina.carga_horaria or 0
            grau = inscricao.conceito or "ND"
            status = inscricao.get_status_display() or "ND"
            professores = inscricao.turma.docentes()

            # CrO e Pontos só se aprovado ou dispensado
            cro = crr if inscricao.status in ("A", "D") else 0
            pontos = cro  # pode ajustar fórmula se mudar

            totais_periodo["crr"] += crr
            totais_periodo["ch"] += ch
            totais_periodo["cro"] += cro
            totais_periodo["pontos"] += pontos

            html += f"""
                <td>{disciplina.codigo}</td>
                <td>{disciplina.titulo}<br><small>{professores}</small></td>
                <td>{crr}</td>
                <td>{ch}</td>
                <td>{grau}</td>
                <td>{cro}</td>
                <td>{pontos}</td>
                <td>{status}</td>
            </tr>
            """

        acumulado["crr"] += totais_periodo["crr"]
        acumulado["ch"] += totais_periodo["ch"]
        acumulado["cro"] += totais_periodo["cro"]
        acumulado["pontos"] += totais_periodo["pontos"]

        html += f"""
        <tr>
            <td rowspan="2" class="historico-escolar-totais-label">Totais:</td>
            <td class="historico-escolar-totais-periodo">No Período</td>
            <td class="historico-escolar-azul">{totais_periodo['crr']}</td>
            <td class="historico-escolar-azul">{totais_periodo['ch']}</td>
            <td class="historico-escolar-azul"></td>
            <td class="historico-escolar-azul">{totais_periodo['cro']}</td>
            <td class="historico-escolar-azul">{totais_periodo['pontos']}</td>
            <td class="historico-escolar-azul"></td>
        </tr>
        <tr>
            <td class="historico-escolar-totais-periodo">Acumulado</td>
            <td class="historico-escolar-escuro">{acumulado['crr']}</td>
            <td class="historico-escolar-escuro">{acumulado['ch']}</td>
            <td class="historico-escolar-escuro"></td>
            <td class="historico-escolar-escuro">{acumulado['cro']}</td>
            <td class="historico-escolar-escuro">{acumulado['pontos']}</td>
            <td class="historico-escolar-escuro"></td>
        </tr>
        """

    html += "</tbody></table>"
    return format_html(html)


def generate_qrcode_base64(link):
    qr = QRCode(
        version=1,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    base64_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return base64_img


MESES_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_por_extenso(d: date) -> str:
    return f"{d.day} de {MESES_PT[d.month - 1]} de {d.year}"
