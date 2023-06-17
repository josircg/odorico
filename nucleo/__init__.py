import hashlib
import Levenshtein
import datetime


def str_to_date(date_string):
    formats = ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%d %b %Y', '%d%m%Y']
    if date_string:
        for formato in formats:
            try:
                return datetime.datetime.strptime(date_string, formato).date()
            except:
                continue
    return None


def clean_doi_url(doi):
    parts = doi.lower().split('10.')
    result = ''
    for part in parts[1:]:
        result = result + '10.' + part
    if (',' in result) or ('/' not in result):
        return None
    else:
        return result


def doi_hashed(doi):
    doi = clean_doi_url(doi)
    url_hashed = hashlib.md5(doi.encode()).hexdigest()
    return url_hashed


def similaridade(str1, str2, absoluta=False):
    """
    Compara duas cadeias de caracteres e retorna a medida de similaridade entre elas, entre 0 e 1,
    onde 1 significa que as cadeias são idênticas ou uma é contida na outra.
    :param str1:
    :param str2:
    :param absoluta: se verdadeira, irá retornar 0 ou 1.
    :return: A medida de similaridade entre as cadeias, de 0 a 1.
    """
    str1 = str1.strip().lower()
    str2 = str2.strip().lower()

    if len(str1) == 0 or len(str2) == 0:
        return 0

    if len(str1) >= 20 and len(str2) >= 20 and (str1 in str2 or str2 in str1):
        return 1

    if not absoluta:
        dist = Levenshtein.ratio(str1, str2)
        if len(str1) >= 10 and len(str2) >= 10 and dist >= 0.90:
            return dist
    else:
        if len(str1) >= 10 and len(str2) >= 10 and Levenshtein.distance(str1, str2) <= 5:
            return 1
    return 0
