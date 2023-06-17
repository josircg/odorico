import hashlib
import uuid

import requests
from crossref.restful import Etiquette, Works
from django.apps import AppConfig
from django.core.validators import EMPTY_VALUES
from django.utils.text import slugify
from stdnum import issn

from chupalattes import get_page, get_doi_content


class NucleoConfig(AppConfig):
    name = 'nucleo'


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


def intdef(s, default):
    """
    :s: string a converter
    :return: número inteiro
    """
    try:
        return int(s)
    except:
        try:
            return int(default)
        except:
            return None


def clean_orcid(orcid):
    if type(orcid) == str:
        orcid = orcid.replace('http://orcid.org/', '').replace('https://orcid.org/', '').replace(' ', '')
        if 'http:' in orcid:
            return None
        else:
            return orcid
    else:
        return None


def clean_id_cnpq(id_cnpq):
    if id_cnpq in EMPTY_VALUES:
        return None

    return id_cnpq.strip()


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


def get_issn(code, extended=False):
    """
    :param code: issn code (or e-issn or issn-l)
    :param extended: return all possible names from other linked issns
    :return: issn-l, eissn list, name list, country, url ou uma string com a mensagem de erro
    """
    title_tag = ''
    code_issn = validate_issn_code(code)
    try:
        response = requests.get('https://portal.issn.org/resource/ISSN/%s?format=json' % code, timeout=10, verify=False)
        dados = response.json()
    except Exception as e:
        return 'NF'

    try:
        graph = dados['@graph']
    except:
        print('ISSN Wrong JSON format: %s' % code)
        return 'NF'
    names = []
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

        if res_id == ('resource/ISSN/%s' % code_issn):
            if res.get('url'):
                url = res.get('url')

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

        if type(link_record) == tuple:
            names += list(set(link_record[2]) - set(names))
            if not country: country = link_record[3]
            if not url: url = link_record[4]

    return code_issn, code_eissn, names, country, url


def normalize_name(name, exc=['.', ',', '/', "'"]):
    if name:
        result = ''
        for c in name:
            c = ' ' if c in exc else c
            result += c
        return ' '.join(result.split()).upper()


def get_page_atribs(soup):
    atribs = {}
    if type(soup) == str:
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
                redirect_soup = get_page(url)
                if redirect_soup:
                    atribs = get_page_atribs(redirect_soup)
                else:
                    redirect_soup = get_page(url.split('&')[0])
                    if redirect_soup:
                        atribs = get_page_atribs(redirect_soup)
                break
    return atribs


def get_doi_record(url_doi, fast=False):
    soup = get_doi_content(url_doi, fast)
    if soup:
        atribs = get_page_atribs(soup)
        if len(atribs) > 0 and atribs.get('title'):
            return atribs

    # Se não houver ao menos o título, deve-se testar via CrossRef
    etiquette = Etiquette('Odorico', 'v0.2', 'http://odorico.irdx.com.br', 'josir@irdx.com.br')
    works = Works(etiquette=etiquette)
    atribs = works.doi(url_doi)
    if not atribs:
        return {}
    else:
        if atribs['type'] == 'journal':
            return {}
        else:
            atribs['provenance'] = 'CrossRef'
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


def doi_record_to_producao(doi, doi_record):
    """Faz o de/para do dicionário doi_record, para os campos da classe Producao"""

    def de_para(src, dest):
        """doi_record é um dicionário cujo o valor de cada chave é uma lista"""
        value = doi_record.get(src, [])[0]

        if value:
            dct[dest] = value.strip()

    dct = {'doi': doi}

    de_para('title', 'titulo')

    return dct
