import io
import os
import re
from collections import Counter
from datetime import datetime, date
from enum import IntEnum
from typing import Any, Dict
from zipfile import ZipFile

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect

from chupalattes import get_dtupdate, get_producao, get_id_cnpq
from nucleo import str_to_date, similaridade, similar_name, normalize_name
from qualis.models import Pais, Periodico
from .apps import log_object, intdef, generate_hash, clean_orcid, clean_doi_url, validate_issn_code, get_issn
from .models import (Pesquisador, Producao, TipoProducao, ProducaoAutor, ProjetoPesquisa, ProfessorLinha,
                     PesquisadorProjeto, Instituicao, PesquisadorInstituicao, PesquisadorFormacao,
                     STATUS_INATIVA, STATUS_ATIVO,
                     TITULACAO_GRADUACAO, TITULACAO_MESTRADO, TITULACAO_DOUTORADO)

NIVEL_POR_TAG = {
    'graduacao': 'GR',
    'mestrado': 'ME',
    'doutorado': 'DO',
}

CONECTORES_SIGLA = {
    'de', 'do', 'da', 'dos', 'das', 'e', 'em', 'no', 'na', 'nos', 'nas',
    'para', 'com', 'a', 'o', 'as', 'os', 'ao', 'aos', 'à', 'às', 'por',
    'of', 'the', 'and', 'for', 'in',
}


class ImportLogLevel(IntEnum):
    INFO = messages.INFO
    SUCCESS = messages.SUCCESS
    WARNING = messages.WARNING
    ERROR = messages.ERROR


class InvalidXMLException(Exception):
    pass


class ISSNException(Exception):
    pass


class ImportXMLException(Exception):
    pass


def get_tipo_producao(cod):
    try:
        return TipoProducao.objects.get(cod_externo=cod)
    except TipoProducao.DoesNotExist:
        raise Exception('Tipo de Produção %s não encontrado' % cod)


def titulacao_do_xml(cv):
    """Deriva a titulação (D/M/G) da <formacao-academica-titulacao>."""
    formacao = cv.find('formacao-academica-titulacao')
    if formacao and formacao.find('doutorado'):
        return TITULACAO_DOUTORADO
    if formacao and formacao.find('mestrado'):
        return TITULACAO_MESTRADO
    return TITULACAO_GRADUACAO


def ano_para_data(texto):
    """Converte um ano (texto) em date(ano, 1, 1); None se inválido."""
    ano = intdef(texto, 0)
    return date(ano, 1, 1) if 1900 < ano < 2100 else None


def importar_formacao(cv, principal):
    """Cria PesquisadorFormacao (GR/ME/DO) a partir da formação acadêmica."""
    ft = cv.find('formacao-academica-titulacao')
    if not ft:
        return 0
    total = 0
    for nome_tag, nivel in NIVEL_POR_TAG.items():
        for tag in ft.find_all(nome_tag, recursive=False):
            nome_inst = (tag.attrs.get('nome-instituicao') or '').strip()[:100] or None
            ano_ini = ano_para_data(tag.attrs.get('ano-de-inicio'))
            ano_fim = ano_para_data(tag.attrs.get('ano-de-conclusao'))

            curso = tag.attrs.get('nome-curso',None)
            if not curso:
                area1 = tag.find('area-do-conhecimento-1')
                if area1:
                    curso = (area1.attrs.get('nome-da-sub-area-do-conhecimento') or '').strip()[:100] or None
                    if not curso:
                        curso = (area1.attrs.get('nome-da-area-do-conhecimento') or '').strip()[:100] or None

            PesquisadorFormacao.objects.get_or_create(
                pesquisador=principal, nivel=nivel,
                nome_instituicao=nome_inst, ano_entrada=ano_ini,
                defaults={'curso': curso, 'ano_conclusao': ano_fim},
            )
            total += 1
    return total


def instituicoes_ativas_do_xml(cv):
    """Nomes únicos de instituições com vínculo em aberto (mes-fim vazio)."""
    nomes = []
    for atuacao in cv.find_all('atuacao-profissional'):
        ativo = any(v.attrs.get('mes-fim', '').strip() == '' and v.attrs.get('carga-horaria-semanal')
                    for v in atuacao.find_all('vinculos'))
        nome = (atuacao.attrs.get('nome-instituicao') or '').strip()
        if ativo and nome and nome not in nomes:
            nomes.append(nome)
    return nomes


def gerar_sigla(nome, tamanho_maximo=10):
    """
    Gera a sigla de uma instituição a partir do seu nome.

    Usa a primeira letra de cada palavra significativa, ignorando conectores
    ("de", "do", "e", "para", etc.). Para nomes de palavra única, retorna as
    primeiras letras do próprio nome. O resultado é truncado a
    ``tamanho_maximo`` (default 10, igual ao campo Instituicao.sigla).
    """
    palavras = re.findall(r'[0-9A-Za-zÀ-ÿ]+', nome or '')
    significativas = [p for p in palavras if p.lower() not in CONECTORES_SIGLA]
    iniciais = [p[0] for p in significativas if p]
    if len(iniciais) >= 2:
        sigla = ''.join(iniciais)
    else:
        sigla = significativas[0] if significativas else (nome or '')
    return sigla[:tamanho_maximo].upper()


def get_or_create_periodico(issn, titulo):
    issn = validate_issn_code(issn)
    periodico = Periodico.objects.filter(issn=issn).first()
    if not periodico:
        periodico = Periodico.objects.filter(eissn=issn).first()

    if not periodico:
        link_record = get_issn(issn)
        if isinstance(link_record, dict):
            novo_issn = link_record['issn']
            eissn = None
            if type(link_record['eissn_list']) == list:
                if len(link_record['eissn_list']) != 0:
                    eissn = link_record['eissn_list'][0]

            if novo_issn != issn:
                periodico = Periodico.objects.filter(issn=novo_issn).first()

            if periodico:
                periodico.eissn = periodico.eissn or eissn
                periodico.dtvalidacao = datetime.today()
                periodico.save()
            else:
                title = link_record['names_list'][0]
                if title:
                    title = title.upper().replace('(IMPRESSO)', '').replace('(ONLINE)', '').strip()
                else:
                    title = titulo

                if link_record['url']:
                    url = link_record['url'][:199]
                else:
                    url = None

                periodico = Periodico(issn=novo_issn, eissn=eissn, nome=title,
                                      pais=link_record['country'][:29], url=url)
                periodico.qualis = 'NC'
                periodico.dtvalidacao = datetime.today()
                periodico.status = 'A'
                periodico.save()
                log_object(periodico, 'ISSN recuperado via Lattes XML')
        else:
            raise ISSNException('ISSN not found %s' % issn)

    return periodico


def limpar_string_xml(texto):
    if not texto:
        return texto

    def reparar(match):
        # Pega a sequência de caracteres "estranhos" encontrada pela regex
        sequencia_suja = match.group(0)
        try:
            # Tenta converter essa sequência específica:
            # interpreta como latin-1 para pegar os bytes originais e decodifica como utf-8
            return sequencia_suja.encode('iso-8859-1').decode('utf-8')
        except:
            # Se falhar (ex: não era um erro de verdade), retorna o original
            return sequencia_suja

    # Esta regex identifica o padrão de erro: um 'Ã' seguido de caracteres de extensão
    # Ela foca apenas onde o problema costuma estar, sem afetar o resto do documento
    # padrao_erro = re.compile(r'Ã[ƒÂ‚†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿]+')
    padrao_erro = re.compile(r'Ã[\x80-\xbf]|Ã[ƒÂ‚†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿\xad]')

    texto_corrigido = texto
    # Rodamos o loop 3 vezes para o caso de erros profundos (ÃƒÂ§)
    for _ in range(3):
        novo_texto = padrao_erro.sub(reparar, texto_corrigido)
        if novo_texto == texto_corrigido:
            break
        texto_corrigido = novo_texto

    return texto_corrigido


def xml_limpo(caminho_arquivo) -> str:
    # Leitura do arquivo XML, limpando o XML dos erros de encoding
    with open(caminho_arquivo, 'r', encoding='iso-8859-1') as f:
        xml_string = f.read()

    xml_string = limpar_string_xml(xml_string)

    return xml_string


def converte_data_lattes(texto):
    data = None
    if texto and len(texto) == 8:
        dia = intdef(texto[0:2], 0)
        mes = intdef(texto[2:4], 0)
        ano = intdef(texto[4:], 0)
        if dia * mes * ano != 0:
            try:
                data = date(day=dia, month=mes, year=ano)
            except:
                data = None
    return data


def verifica_lattes(id_cnpq: str):
    """
    Verifica se o id_cnpq existe no Lattes e retorna o nome do pesquisador ou None
    """
    nome = None
    filename = os.path.join(settings.BASE_DIR, 'data', id_cnpq + '.xml')
    if not os.path.exists(filename):
        if settings.PROXY_LATTES_URL:
            try:
                xml = get_lattes_from_proxy(id_cnpq)
            except (TimeoutError, InvalidXMLException) as e:
                return None
        else:
            # se não houver proxy para o lattes, então é um ambiente de teste e dessa forma o dev deve prover o arquivo
            # raise InvalidXMLException(f'Arquivo deve ser copiado para a pasta data no ambiente de teste')
            return None
    else:
        xml = xml_limpo(filename)

    soup = BeautifulSoup(xml, 'lxml')
    try:
        cv = soup.find('curriculo-vitae')
        dg = cv.find('dados-gerais')
    except Exception:
        raise InvalidXMLException('Arquivo XML Inválido')

    nome = normalize_name(dg.attrs.get('nome-completo', ''))
    id_lido = cv.attrs.get('numero-identificador', '')
    if id_lido != id_cnpq:
        raise InvalidXMLException('ID CNPQ inconsistente. Procure a secretaria.')

    return nome


def get_lattes_from_proxy(id_cnpq, pesquisador=None) -> str:
    # Busca um arquivo zip com o XML do pesquisador no Proxy Lattes
    # Grava na pasta data se achar
    response = requests.get(f'{settings.PROXY_LATTES_URL}/curriculo/{id_cnpq}', timeout=15)
    if response.status_code == 200:
        pathname = os.path.join(settings.BASE_DIR, 'data')
        filename = os.path.join(pathname, id_cnpq + '.xml')
        try:
            z = ZipFile(io.BytesIO(response.content))
            z.extractall(pathname)
            return xml_limpo(filename)
        except InvalidXMLException:
            os.remove(filename)
            raise
    else:
        if response.status_code == 404:
            raise ValidationError('ID CNPQ inexistente')
        else:
            raise TimeoutError(f'Erro ao recuperar currículo do CNPQ ({response.status_code})')


# obtem os dados do lattes de forma silenciosa, sem retornar mensagem para o usuário
def obtem_lattes(id_cnpq: str, com_producao:bool):
    filename = os.path.join(settings.BASE_DIR, 'data', id_cnpq + '.xml')
    # se não houver o canal com o Lattes via proxy, a única opção é o cache
    if not settings.PROXY_LATTES_URL:
        updated = os.path.exists(filename)
        if not updated:
            raise ImportXMLException('Currículo não encontrado na pasta')
    else:
        # se a carga do lattes for inferior a 30 dias, utilizar o cache
        try:
            ctime = os.path.getctime(filename)
            d = datetime.fromtimestamp(ctime)
            hoje = datetime.now()
            delta = hoje - d
            updated = delta.days < 30
        except FileNotFoundError:
            updated = False

    # se o arquivo existir no cache e estiver atualizado, não é necessário utilizar o proxy
    if updated:
        xml = xml_limpo(filename)
    else:
        xml = get_lattes_from_proxy(id_cnpq)

    resultado = import_xml(xml, com_producao=com_producao)
    return resultado


@login_required
def update_lattes(request, id_cnpq, com_producao=True):
    referer_url = request.META.get('HTTP_REFERER') or '/admin/nucleo/producao'
    try:
        resultado = obtem_lattes(id_cnpq, com_producao)
        processar_logs_view(request, resultado.get('logs', []))
    except requests.exceptions.ConnectTimeout as e:
        messages.error(request, f'Erro ao recuperar currículo do CNPQ')
    except Exception as e:
        messages.error(request, f'{e}')

    return redirect(referer_url)


# Rotina que importa a produção a partir do HTML
def import_html(html, request):
    soup = BeautifulSoup(html, 'html.parser')
    nome = soup.find('h2', attrs={'class': "nome"}).text
    try:
        div_id = soup.find('div', attrs={'id': "menu-informacoes-complementares"})
        div_id = div_id.find('a').get('href').split('id=')[1].split('&')[0]
    except:
        try:
            div_id = soup.find('span', attrs={'class': "linksFlow"}).find('a').get('href')
            div_id = div_id.split('id=')[1].split('&')[0]
        except:
            return None

    base_dir = os.path.join(settings.BASE_DIR, 'cache')
    if not os.path.exists(base_dir):
        os.mkdir(base_dir)
    html_file = open(os.path.join(base_dir, '%s.html' % div_id), mode='w', encoding='utf-8')
    html_file.write(html)
    html_file.close()

    nome = nome.upper()
    try:
        pesquisador = Pesquisador.objects.get(id_lattes=div_id)
        if nome != pesquisador.nome.upper():
            messages.warning(request, 'Nome do Pesquisador difere do nome no Lattes: %s' % nome)
        messages.info(request, 'Pesquisador %s atualizado com sucesso' % nome)
    except Pesquisador.DoesNotExist:
        if Pesquisador.objects.filter(nome=nome).count() > 0:
            messages.error(request, 'Já existe um pesquisador com outro ID Lattes no sistema:%s' % nome)
            messages.error(request, 'A importação não foi realizada')
            return redirect('/importacao_lattes/')
        pesquisador = Pesquisador.objects.create(nome=nome, id_lattes=div_id)
        messages.warning(request, 'Pesquisador %s inserido com sucesso' % nome)
    pesquisador.dtupdate = get_dtupdate(soup)
    pesquisador.id_cnpq = get_id_cnpq(soup)
    pesquisador.atualizado = True
    pesquisador.save()

    lista_producao = get_producao(soup)
    tot_producao = 0
    for item in lista_producao:
        try:
            tipo = TipoProducao.objects.get(cod_externo=item['type'])
        except TipoProducao.DoesNotExist:
            tipo = TipoProducao(descricao=item['type'], cod_externo=item['type'])
            tipo.save()

        ano = 1900
        for word in reversed(item['text'].replace('.', ' ').replace(';', ' ').replace(',', ' ').split(' ')):
            if not (word.isdigit() and len(word) != 4) and word[:4].isdigit():
                if 1960 < int(word[:4]) < 2100:
                    ano = word[:4]
                    break

        try:
            Producao.objects.get(pesquisador=pesquisador, tipo=tipo, titulo=item['text'], ano=ano)
        except Producao.DoesNotExist:
            producao = Producao(pesquisador=pesquisador,
                                tipo=tipo,
                                titulo=item['text'],
                                doi=item.get('doi', None),
                                ano=ano,
                                pais='br')
            producao.save()
            tot_producao += 1
    messages.info(request, 'Produções incluídas: %d' % tot_producao)
    return div_id


def import_xml(texto_xml: str, pesquisador: Pesquisador | None = None,
               save_file: bool = False,
               com_producao: bool = True) -> Dict[str, Any]:
    """
    Processa o currículo XML do Lattes e sincroniza os dados com o banco de dados.

    A função extrai informações de produção bibliográfica, técnica, projetos e
    rede de colaboradores, realizando a persistência e normalização dos registros.

    A rede de autores contém todos os autores com relacionamento com o pesquisador que está sendo importado
    Existem 2 tipos de chaves registradas: o ID_CNPQ e o hash com o nome compactado do autor
    Dessa forma, o sistema não precisa ir sempre na base para recuperar o pesquisador
    e consegue encontrar mais facilmente os pesquisadores pelo nome

    :param texto_xml: String contendo o conteúdo completo do arquivo XML (.lattes).
    :param pesquisador: Instância opcional do pesquisador dono do currículo para validação de identidade.
    :param save_file: Se True, salva uma cópia do XML no diretório de dados do sistema.
    :param com_producao: Se True, importa também as produções
    :return: Um dicionário contendo:
        - 'sucesso' (bool): Indica se a operação foi concluída sem erros fatais.
        - 'logs' (list): Lista de dicionários com 'nivel' (int) e 'texto' (str) para UI.
    """
    rede = {}
    warnings = ['Importação Lattes']
    # Contador de registros processados
    TOTAIS = Counter()
    logs = []

    def adicionar_log(nivel: ImportLogLevel, texto: str):
        logs.append({'nivel': nivel.value, 'texto': texto})

    def get_or_create_rede(nome_ator, pesquisador=None, id_cnpq=None):
        if not nome_ator and pesquisador:
            nome_ator = pesquisador.nome

        if ',' in nome_ator:
            inverted_name = nome_ator.split(',')
            inverted_name = inverted_name[1].split(' ') + [inverted_name[0].strip()]
            nome_ator = ' '.join([x for x in inverted_name if x])

        if not nome_ator:
            return None

        # verifica se o id_cnpq já existe para outro ator
        # se existir, desconsiderar o id_cnpq
        chave = similar_name(nome_ator)
        if id_cnpq:
            record = rede.get(id_cnpq, None)
            if record and chave != similar_name(record['nome']):
                warnings.append(f'id_cnpq mismatch:{id_cnpq}')
                id_cnpq = None
                record = None
                TOTAIS['id_cnpq_mismatch'] += 1
        else:
            record = None

        if not record:
            record = rede.get(chave)

        if record and not pesquisador:
            pesquisador = record.get('pesquisador')
            if pesquisador:
                if id_cnpq and id_cnpq != pesquisador.id_cnpq:
                    warnings.append('ID CNPQ mismatch: %s %s' % (id_cnpq, record.get('id_cnpq')))
                    chave = '#%s' % pesquisador.id_cnpq
                    TOTAIS['id_cnpq_mismatch'] += 1
                    record = None

                if id_cnpq and normalize_name(nome_ator) != normalize_name(pesquisador.nome):
                    short_name = pesquisador.nome.split()[0] + ' ' + pesquisador.nome.split()[-1]
                    short_name2 = nome_ator.split()[0] + ' ' + nome_ator.split()[-1]

                    if normalize_name(short_name) != normalize_name(short_name2):
                        warnings.append('Name mismatch: %s %s' % (nome_ator, pesquisador.nome))
                        TOTAIS['name_mismatch'] += 1

        if not record:
            nome_ator = normalize_name(nome_ator)
            record = {'nome': nome_ator[:129], 'pesquisador': pesquisador}
            rede[chave] = record
            if id_cnpq:
                rede[id_cnpq] = record
        else:
            record['nome'] = record['nome'][:129]

        if not record.get('pesquisador', None) and id_cnpq:
            pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
            if not pesquisador:
                pesquisador = Pesquisador(nome=nome_ator, id_cnpq=id_cnpq)
                pesquisador.save()
                log_object(pesquisador, 'Importação XML - Co-Autor')
                TOTAIS['autor_incluido'] += 1

        if not pesquisador:
            pesquisador = Pesquisador.objects.filter(nome__exact=nome_ator)
            if pesquisador.count() > 1:
                warnings.append('Homonimo: %s' % nome_ator)
                pesquisador = None
            else:
                pesquisador = pesquisador.first()

        rede[chave]['pesquisador'] = pesquisador

        return record

    dict_natureza = {
        "TEXTO_INTEGRAL": 'A', "REVISTAS_OU_PERIODICOS": 'A',
        "COMPLETO": 'A',
        "OBRA_UNICA": 'T',
        "COLECAO": 'C',
        "COLETANEA": 'L',
        "DICIONARIO": 'D',
        "ENCICLOPEDIA": 'E',
        "ENTREVISTA": 'e',
        "COMENTARIO": 'c',
        "MESA_REDONDA": 'm',
        "COMUNICAÇÃO": '5',
        "CONFERENCIA": '6',
        "CONGRESSO": '7',
        "SEMINARIO": '8',
        "LIVRO": "L", "LIVRO_ORGANIZADO_OU_EDICAO": "L", "LIVRO_PUBLICADO": "L",
        "SITE": 's',
        "BLOG": "b",
        "NAO_INFORMADO": None,
    }

    dict_meio = {
        "IMPRESSO": "I",
        "MAGNETICA": "M",
        "DIGITAL": "D", "MEIO_DIGITAL": "D", "CD": "D", "DVD": "D", "BLURAY": "D", "USB": "D",
        "FILME": "F",
        "HIPERTEXTO": "H",
        "OUTRO": "O"
    }

    dict_tipo_obra = {
        "CAPITULO": "C", "Capítulo de livro publicado": "C",
        "VERBETE": "V",
        "APRESENTACAO": "A",
        "INTRODUCAO": "I",
        "PREFACIO": "P",
        "POSFACIO": "O",
        "COMPLETO": 'T',
        "RESUMO": 'R',
        "RESUMOX": 'X',
        "ORGANIZACAO": '4',
        "CURADORIA": '1',
    }

    def normaliza(corrente, novo, tamanho_maximo=None, capitalize=True):
        result = corrente
        if not corrente and novo:
            result = novo
            if tamanho_maximo:
                result = result[:tamanho_maximo - 1]

        if result and capitalize:
            return result.capitalize()
        else:
            return result

    def producao_e_autores(pesquisador_original, tipo, doi=None, titulo=None, issn=None, titulo_periodico=None,
                           descricao=None, isbn=None, editora=None, idioma=None,
                           ano=None, serie=None, volume=None,
                           nome_evento=None, pais=None, cidade=None,
                           tag_autores=None, natureza_obra=None, meio=None, tipo_obra=None,
                           titulo_colecao=None, organizacao=None, abrangencia=None, url=None,
                           reedicao='N',
                           num_paginas=None, pagina_inicial=None, pagina_final=None, dt_publicacao=None):

        dt_publicacao = converte_data_lattes(dt_publicacao)
        if dt_publicacao and not ano:
            ano = dt_publicacao.year
        if ano < 2010:
            return

        if not titulo:
            raise Exception('Título da produção inexistente')

        producao = None
        if doi:
            producao = Producao.objects.filter(doi=doi).first()

        # Caso de prefácios/posfácios
        if isbn and natureza_obra == 'REVISTAS_OU_PERIODICOS' and len(isbn) == 8:
            issn = isbn
            isbn = None

        if isbn:
            producao = Producao.objects.filter(pesquisador=pesquisador_original, isbn=isbn).first()

        hash_ident = generate_hash(titulo)
        if not producao and hash_ident:
            producao = Producao.objects.filter(ident_unico=hash_ident, tipo=tipo).first()

        if issn:
            periodico = get_or_create_periodico(issn, titulo_periodico)
        else:
            periodico = None

        if pais:
            pais = pais[:30]
        elif periodico and periodico.pais:
            pais = periodico.pais[:30]

        if not producao:
            producao = Producao.objects.create(
                titulo=titulo, ident_unico=hash_ident, doi=doi, isbn=isbn,
                ano=ano, serie=serie, volume=volume,
                pesquisador=pesquisador_original, tipo=tipo, descricao=descricao,
                validacao=Producao.Status.ABERTO
            )
            TOTAIS['producao_incluida'] += 1

        producao.ano = producao.ano or ano
        producao.dt_publicacao = producao.dt_publicacao or dt_publicacao

        if producao.validacao == Producao.Status.ABERTO:
            producao.serie = serie
            producao.volume = volume
            producao.pais = normaliza(producao.pais, pais, 60)
            producao.idioma = normaliza(producao.idioma, idioma, 30)
            producao.descricao = producao.descricao or descricao
            producao.titulo_original = titulo
            if pagina_inicial:
                producao.pagina_inicial = producao.pagina_inicial or intdef(pagina_inicial)
            producao.pagina_final = producao.pagina_final or intdef(pagina_final)
            producao.num_paginas = producao.num_paginas or intdef(num_paginas)
            producao.editora = normaliza(producao.editora, editora, 300)
            producao.cidade = normaliza(producao.cidade, cidade, 200)
            producao.titulo_colecao = producao.titulo_colecao or titulo_colecao
            producao.organizacao = normaliza(producao.organizacao, organizacao)
            producao.url = normaliza(producao.url, url, 200, False)
            producao.reedicao = reedicao == 'S'

        for rec in producao.producaoautor_set.select_related('autor').all():
            get_or_create_rede(rec.nome, rec.autor)

        if tipo.cod_externo == 'anais' or tipo.cod_externo == 'ApresentacoesTrabalho':
            descricao = titulo + '. ' + tipo.descricao
            if nome_evento:
                descricao = descricao + '. ' + nome_evento
            if organizacao:
                descricao = descricao + '. ' + organizacao
            producao.descricao = descricao
            if abrangencia and len(abrangencia) > 0 and abrangencia[0] in ('R', 'I', 'N', 'L'):
                producao.abrangencia = abrangencia[0]

        elif tipo.cod_externo == 'LivrosCapitulos' or tipo.cod_externo == 'CapitulosLivrosPublicados':
            producao.descricao = titulo

        if periodico:
            producao.periodico = periodico

        if natureza_obra:
            producao.natureza_obra = dict_natureza.get(natureza_obra, None)

        if meio:
            producao.meio = dict_meio.get(meio, None)

        if tipo_obra:
            producao.tipo_obra = dict_tipo_obra.get(tipo_obra, None)

        producao.save()

        tot_autores = 0
        for tag in tag_autores:
            tot_autores += 1
            id_cnpq = tag.attrs.get('nro-id-cnpq', '')
            autor = get_or_create_rede(tag.attrs.get('nome-completo-do-autor', ''), id_cnpq=id_cnpq)
            try:
                if autor['pesquisador']:
                    prod_autor, included = \
                        ProducaoAutor.objects.get_or_create(producao=producao, autor=autor['pesquisador'])
                    prod_autor.nome = autor['nome']
                else:
                    prod_autor, included = \
                        ProducaoAutor.objects.get_or_create(producao=producao, nome=autor['nome'])
                prod_autor.ordem = intdef(tag.attrs.get('ordem-de-autoria', ''), 1)
                if prod_autor.ordem > 200 or prod_autor.ordem < 0:
                    prod_autor.ordem = 1
                prod_autor.save()
            except ProducaoAutor.MultipleObjectsReturned:
                included = False
                pass

            if producao.producaoautor_set.filter(autor=pesquisador_original).count() == 0:
                ProducaoAutor.objects.get_or_create(producao=producao, autor=pesquisador_original)

            if included:
                TOTAIS['novos_autores'] += 1

        # Sempre adicionar o pesquisador original como autor (nem sempre o Lattes traz essa info)
        if producao.producaoautor_set.filter(autor=pesquisador_original).count() == 0:
            ProducaoAutor.objects.get_or_create(producao=producao, autor=pesquisador_original)

        return

    try:
        soup = BeautifulSoup(texto_xml, 'lxml')
        try:
            cv = soup.find('curriculo-vitae')
            dg = cv.find('dados-gerais')
        except Exception:
            raise InvalidXMLException('Arquivo XML Inválido')

        nome = normalize_name(dg.attrs.get('nome-completo', ''))
        id_cnpq = cv.attrs.get('numero-identificador', '')
        orcid = dg.attrs.get('orcid-id')
        pais_str = dg.attrs.get('pais-de-nascimento', '') or dg.attrs.get('pais-de-nacionalidade', '')

        novo_pesquisador = False

        if not id_cnpq:
            raise ImportXMLException('ID CNPQ não encontrado no XML')

        if pesquisador:
            nome_obrigatorio = normalize_name(pesquisador.nome)
            if similaridade(nome_obrigatorio, nome) < 0.9:
                raise ImportXMLException(f'Nome incompatível com o registro do Lattes: {nome}/{nome_obrigatorio}')

            if pesquisador.id_cnpq and id_cnpq != pesquisador.id_cnpq:
                raise ImportXMLException(f'ID do CNPQ incompatível com o registro do Lattes: {id_cnpq}')

            principal = pesquisador
            if not principal.id_cnpq:
                principal.id_cnpq = id_cnpq

        else:
            principal = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()

        if save_file:
            path = os.path.join(settings.BASE_DIR, 'data', id_cnpq + '.xml')
            with open(path, 'w') as writer:  # grava o arquivo em "/data/"
                writer.write(soup.decode())

        transaction.set_autocommit(False)
        if not principal:
            principal = Pesquisador.objects.filter(nome=nome, id_cnpq__isnull=True)
            if principal:
                if principal.count() > 1:
                    raise ImportXMLException(f'Existe mais de um pesquisador com o nome {nome}')

                principal = principal.first()
                principal.id_cnpq = id_cnpq
            else:
                principal = Pesquisador.objects.create(id_cnpq=id_cnpq, nome=nome)
                novo_pesquisador = True

        if orcid:
            principal.orcid = clean_orcid(orcid)

        principal.nome = nome
        principal.pais = Pais.objects.filter(nome__icontains=pais_str).first()
        principal.dtupdate = str_to_date(cv.attrs['data-atualizacao'])
        principal.atualizado = True
        principal.situacao = titulacao_do_xml(cv)
        principal.save()
        if novo_pesquisador:
            log_object(principal, 'Importação Lattes', True)

        for nome_inst in instituicoes_ativas_do_xml(cv):
            instituicao = Instituicao.objects.filter(nome__icontains=nome_inst).first()
            if instituicao is None:
                instituicao = Instituicao.objects.create(
                    nome=nome_inst[:80], sigla=gerar_sigla(nome_inst))
                log_object(instituicao, f'Importação Lattes {id_cnpq}', True)
            obj, criado = PesquisadorInstituicao.objects.get_or_create(
                pesquisador=principal, instituicao=instituicao)
            if criado:
                mensagem = f'Instituição vinculada: {instituicao.nome}'
                adicionar_log(ImportLogLevel.INFO, mensagem)
                log_object(principal, mensagem)

        TOTAIS['formacao_incluida'] = importar_formacao(cv, principal)
        adicionar_log(ImportLogLevel.INFO, f'Formações importadas: {TOTAIS["formacao_incluida"]}')

        get_or_create_rede(nome, principal, id_cnpq)

        if soup.find_all('projeto-de-pesquisa'):
            for projeto_pesquisa in soup.find_all('projeto-de-pesquisa'):
                responsavel_projeto = list(filter(lambda p: p.attrs.get('flag-responsavel') == 'SIM',
                                                  projeto_pesquisa.find_all('integrantes-do-projeto')))
                integrantes = projeto_pesquisa.find_all('integrantes-do-projeto')

                nome_projeto = projeto_pesquisa.attrs.get('nome-do-projeto').upper()
                if not responsavel_projeto:
                    adicionar_log(ImportLogLevel.WARNING, f'Projeto {nome_projeto} não possui nenhum responsavel')
                    continue

                responsavel_projeto = responsavel_projeto[0].attrs
                nome_lider_projeto = normalize_name(responsavel_projeto.get('nome-completo'))
                id_lider_projeto = responsavel_projeto.get('nro-id-cnpq', None)

                # muitas vezes o id vem errado no XML, com o mesmo id do pesquisador principal
                # nesse caso, deve-se desprezar o id indicado no XML
                if id_lider_projeto == id_cnpq and nome_lider_projeto != principal.nome:
                    id_lider_projeto = None

                lider = get_or_create_rede(nome_lider_projeto, id_cnpq=id_lider_projeto)
                lider = lider.get('pesquisador')
                if lider:
                    projeto = ProjetoPesquisa.objects.filter(nome__icontains=nome_projeto, proponente=lider).first()
                    if projeto:
                        linha = projeto.linha
                    else:
                        linha = ProfessorLinha.objects.filter(professor=lider).first()
                        if linha:
                            linha = linha.linha

                    # se o líder não faz parte de nenhum programa da base, o projeto não precisa ser registrado
                    if linha:
                        if not projeto:
                            projeto = ProjetoPesquisa.objects.create(
                                nome=nome_projeto[:399],
                                descricao=projeto_pesquisa.attrs.get('descricao-do-projeto'),
                                proponente=lider,
                                linha=linha
                            )
                            TOTAIS['projetos_incluidos'] += 1
                else:
                    projeto = None

                if projeto:
                    projeto.status = (
                        STATUS_INATIVA if projeto_pesquisa.attrs.get('situacao') == 'CONCLUIDO' else STATUS_ATIVO
                    )
                    projeto.save()

                    for integrante in integrantes:
                        nome_integrante = normalize_name(integrante.attrs.get('nome-completo'))
                        id_integrante = integrante.attrs.get('nro-id-cnpq')
                        if id_integrante == id_cnpq and nome_integrante != principal.nome:
                            id_integrante = None

                        # insere integrante do projeto na rede do autores
                        record = get_or_create_rede(nome_integrante, id_cnpq=id_integrante)
                        pesquisador = record.get('pesquisador')
                        if pesquisador and projeto:
                            _, created = PesquisadorProjeto.objects.get_or_create(pesquisador=pesquisador, projeto=projeto)
                            if created:
                                TOTAIS['pesquisador_projeto'] += 1

        tag_producao = cv.find('producao-bibliografica')
        if tag_producao and com_producao:

            tipo_artigo = get_tipo_producao('artigo')
            tipo_congresso = get_tipo_producao('anais')
            tipo_midiaimpressa = get_tipo_producao('midiaImpressa')
            tipo_livro = get_tipo_producao('LivrosCapitulos')
            tipo_capitulo = get_tipo_producao('CapitulosLivrosPublicados')
            tipo_bibliografica = get_tipo_producao('Bibliografica')
            tipo_apresentacao = get_tipo_producao('apresentacao')
            tipo_software = get_tipo_producao('SoftwareSemPatente')
            tipo_curso = get_tipo_producao('curso')
            tipo_tecnica = get_tipo_producao('TrabalhosTecnicos')
            tipo_midiaeletronica = get_tipo_producao('midiaeletronica')
            tipo_webblog = get_tipo_producao('RedesSociais')

            #  Artigos em Periódicos
            tag_artigos = tag_producao.find('artigos-publicados')
            if tag_artigos:
                for art in tag_artigos.select('artigo-publicado'):
                    dados = art.find('dados-basicos-do-artigo')
                    detal = art.find('detalhamento-do-artigo')
                    titulo = dados.attrs.get('titulo-do-artigo', '')
                    try:
                        producao_e_autores(
                            principal, tipo_artigo, doi=clean_doi_url(dados.attrs.get('doi', '')),
                            titulo=titulo,
                            issn=detal.attrs.get('issn'),
                            titulo_periodico=detal.attrs.get('titulo-do-periodico-ou-revista'),
                            ano=intdef(dados.attrs['ano-do-artigo'], 1900),
                            idioma=dados.attrs.get('idioma'),
                            volume=detal.attrs.get('volume'),
                            serie=detal.attrs.get('serie'),
                            pagina_inicial=detal.attrs.get('pagina-inicial'),
                            pagina_final=detal.attrs.get('pagina-final'),
                            natureza_obra=dados.attrs.get('natureza'),
                            tag_autores=art.find_all('autores'),
                        )
                    except ISSNException as e:
                        adicionar_log(ImportLogLevel.ERROR, str(e))

            #  Artigos em Jornais e Revistas
            tag_biblio = tag_producao.find('textos-em-jornais-ou-revistas')
            if tag_biblio:
                for art in tag_biblio.select('texto-em-jornal-ou-revista'):
                    dados = art.find('dados-basicos-do-texto')
                    detal = art.find('detalhamento-do-texto')
                    titulo = dados.attrs.get('titulo-do-texto')
                    producao_e_autores(
                        principal, tipo_midiaimpressa,
                        titulo=titulo,
                        ano=intdef(dados.attrs.get('ano-do-texto'), 0),
                        idioma=dados.attrs.get('idioma'),
                        natureza_obra=dados.attrs.get('natureza'),
                        editora=detal.attrs.get('titulo-do-jornal-ou-revista'),
                        url=dados.attrs.get('home-page-do-trabalho'),
                        pagina_inicial=detal.attrs.get('pagina-inicial'),
                        pagina_final=detal.attrs.get('pagina-final'),
                        dt_publicacao=detal.attrs.get('data-de-publicacao'),
                        tag_autores=art.find_all('autores'),
                    )

            tag_biblio = tag_producao.find('prefacio-posfacio')
            if tag_biblio:
                for art in tag_producao.select('prefacio-posfacio'):
                    dados = art.find('dados-basicos-do-prefacio-posfacio')
                    detal = art.find('detalhamento-do-prefacio-posfacio')
                    titulo = dados.attrs.get('titulo')
                    volume = detal.attrs.get('volume')
                    if not volume:
                        volume = detal.attrs.get('numero-da-edicao-revisao')

                    producao_e_autores(
                        principal, tipo_bibliografica,
                        titulo=titulo,
                        ano=intdef(dados.attrs.get('ano'), 0),
                        pais=dados.attrs.get('pais-de-publicacao'),
                        idioma=dados.attrs.get('idioma'),
                        meio=dados.attrs.get('meio-de-divulgacao'),
                        tipo_obra=dados.attrs.get('tipo'),
                        natureza_obra=dados.attrs.get('natureza'),
                        isbn=detal.attrs.get('issn-isbn'),
                        editora=detal.attrs.get('editora-do-prefacio-posfacio'),
                        cidade=detal.attrs.get('cidade-da-editora'),
                        url=dados.attrs.get('home-page-do-trabalho'),
                        volume=volume,
                        tag_autores=art.find_all('autores'),
                    )

            # Trabalhos em Anais/Congressos
            tag_eventos = tag_producao.find('trabalhos-em-eventos')
            if tag_eventos:
                for evento in tag_eventos.select('trabalho-em-eventos'):
                    dados = evento.find('dados-basicos-do-trabalho')
                    detal = evento.find('detalhamento-do-trabalho')
                    producao_e_autores(
                        principal,
                        tipo=tipo_congresso,
                        titulo=dados.attrs.get('titulo-do-trabalho', ''),
                        doi=clean_doi_url(dados.attrs.get('doi')),
                        isbn=detal.attrs.get('isbn', ''),
                        nome_evento=detal.attrs.get('nome-do-evento', ''),
                        pais=dados.attrs.get('pais-do-evento', ''),
                        ano=intdef(detal.attrs.get('ano-de-realizacao'), 1900),
                        volume=detal.attrs.get('volume', ''),
                        serie=detal.attrs.get('serie', ''),
                        idioma=dados.attrs.get('idioma', ''),
                        titulo_colecao=detal.get('titulo-dos-anais-ou-proceedings', ''),
                        tag_autores=evento.find_all('autores'),
                    )

            # Livros e capítulos publicados
            tag_livros_e_capitulos = tag_producao.find('livros-e-capitulos')
            if tag_livros_e_capitulos:
                tag_livros = tag_livros_e_capitulos.find('livros-publicados-ou-organizados')
                if tag_livros:
                    for livro in tag_livros.select('livro-publicado-ou-organizado'):
                        dados = livro.find('dados-basicos-do-livro')
                        detal = livro.find('detalhamento-do-livro')
                        producao_e_autores(
                            principal,
                            tipo=tipo_livro,
                            titulo=dados.attrs.get('titulo-do-livro', ''),
                            doi=clean_doi_url(dados.attrs.get('doi')),
                            isbn=detal.attrs.get('isbn', ''),
                            ano=intdef(dados.attrs.get('ano'), 1900),
                            idioma=dados.attrs.get('idioma', ''),
                            tag_autores=livro.find_all('autores'),
                            editora=detal.attrs.get('nome-da-editora', ''),
                            cidade=detal.attrs.get('cidade-da-editora', ''),
                            natureza_obra=dados.attrs.get('tipo'),  # está invertido no XML
                            tipo_obra=dados.attrs.get('natureza'),
                            meio=dados.attrs.get('meio-de-divulgacao'),
                        )

                tag_capitulos = tag_livros_e_capitulos.find('capitulos-de-livros-publicados')
                if tag_capitulos:
                    for capitulo in tag_capitulos.select('capitulo-de-livro-publicado'):
                        dados = capitulo.find('dados-basicos-do-capitulo')
                        detal = capitulo.find('detalhamento-do-capitulo')
                        producao_e_autores(
                            principal,
                            tipo=tipo_capitulo,
                            titulo=dados.attrs.get('titulo-do-capitulo-do-livro', ''),
                            doi=clean_doi_url(dados.attrs.get('doi')),
                            isbn=detal.attrs.get('isbn', ''),
                            ano=intdef(dados.attrs.get('ano'), 1900),
                            idioma=dados.attrs.get('idioma', ''),
                            tag_autores=capitulo.find_all('autores'),
                            editora=detal.attrs.get('nome-da-editora', ''),
                            cidade=detal.attrs.get('cidade-da-editora', ''),
                            meio=dados.attrs.get('meio-de-divulgacao'),
                            tipo_obra=dados.attrs.get('tipo'),
                            titulo_colecao=detal.attrs.get('titulo-do-livro', ''),
                            organizacao=detal.attrs.get('organizadores', '')
                        )

            tag_tecnica = soup.find('producao-tecnica')
            if tag_tecnica:
                tipo_orgevento = get_tipo_producao('orgevento')
                for outras in tag_tecnica.select('organizacao-de-evento'):
                    dados = outras.find('dados-basicos-da-organizacao-de-evento')
                    detal = outras.find('detalhamento-da-organizacao-de-evento')
                    producao_e_autores(
                        principal,
                        titulo=dados.attrs.get('titulo'),
                        tipo=tipo_orgevento,
                        tipo_obra=dados.attrs.get('tipo'),
                        natureza_obra=dados.attrs.get('natureza'),
                        ano=intdef(dados.get('ano'), 1900),
                        idioma=dados.attrs.get('idioma'),
                        pais=dados.attrs.get('pais'),
                        editora=detal.attrs.get('instituicao-promotora'),
                        organizacao=detal.attrs.get('local'),
                        cidade=detal.attrs.get('cidade'),
                        reedicao=detal.attrs.get('flag-evento-itinerante'),
                        url=dados.attrs.get('home-page-do-trabalho'),
                        tag_autores=outras.find_all('autores'),
                    )

                for outras in tag_tecnica.select('programa-de-radio-ou-tv'):
                    dados = outras.find('dados-basicos-do-programa-de-radio-ou-tv')
                    detal = outras.find('detalhamento-do-programa-de-radio-ou-tv')
                    producao_e_autores(
                        principal,
                        titulo=dados.attrs.get('titulo'),
                        tipo=tipo_midiaeletronica,
                        natureza_obra=dados.attrs.get('natureza'),
                        ano=intdef(dados.get('ano'), 1900),
                        idioma=dados.attrs.get('idioma', ''),
                        pais=dados.attrs.get('pais', ''),
                        editora=detal.attrs.get('emissora', ''),
                        cidade=detal.attrs.get('cidade', ''),
                        url=dados.attrs.get('home-page', ''),
                        tag_autores=outras.find_all('autores'),
                    )

                for outras in tag_tecnica.select('midia-social-website-blog'):
                    dados = outras.find('dados-basicos-da-midia-social-website-blog')
                    detal = outras.find('detalhamento-da-midia-social-website-blog')
                    producao_e_autores(
                        principal,
                        titulo=dados.attrs.get('titulo'),
                        tipo=tipo_webblog,
                        natureza_obra=dados.attrs.get('natureza'),
                        ano=intdef(dados.get('ano'), 1900),
                        idioma=dados.attrs.get('idioma', ''),
                        pais=dados.attrs.get('pais', ''),
                        editora=detal.attrs.get('emissora', ''),
                        cidade=detal.attrs.get('cidade', ''),
                        url=dados.attrs.get('home-page', ''),
                        tag_autores=outras.find_all('autores'),
                    )

                for apresentacao in tag_tecnica.select('apresentacao-de-trabalho'):
                    dados = apresentacao.find('dados-basicos-da-apresentacao-de-trabalho')
                    detal = apresentacao.find('detalhamento-da-apresentacao-de-trabalho')
                    producao_e_autores(
                        principal,
                        tipo=tipo_apresentacao,
                        titulo=dados.attrs.get('titulo-do-trabalho-tecnico', dados.attrs.get('titulo', '')),
                        ano=intdef(dados.get('ano'), 1900),
                        doi=dados.attrs.get('doi', ''),
                        nome_evento=detal.attrs.get('nome-do-evento', ''),
                        organizacao=detal.attrs.get('instituicao-promotora', ''),
                        idioma=dados.attrs.get('idioma', ''),
                        pais=dados.attrs.get('pais', ''),
                        abrangencia=detal.get('classificacao-do-evento', ''),
                        tag_autores=apresentacao.find_all('autores'),
                    )

                for outras in tag_tecnica.select('curso-de-curta-duracao-ministrado'):
                    dados = outras.find('dados-basicos-de-curso-de-curta-duracao-ministrado')
                    detal = outras.find('detalhamento-de-curso-de-curta-duracao-ministrado')
                    if dados and detal:
                        producao_e_autores(
                            principal,
                            tipo=tipo_curso,
                            titulo=dados.attrs.get('titulo'),
                            ano=intdef(dados.get('ano'), 0),
                            idioma=dados.attrs.get('idioma'),
                            pais=dados.attrs.get('pais'),
                            url=dados.attrs.get('home-page-do-trabalho'),
                            tipo_obra=detal.attrs.get('participacao-dos-autores'),
                            meio=dados.attrs.get('meio-de-divulgacao'),
                            cidade=detal.attrs.get('pais'),
                            num_paginas=detal.attrs.get('duracao'),
                            editora=detal.attrs.get('instituicao-promotora-do-curso'),
                            organizacao=detal.attrs.get('local-do-curso'),
                            tag_autores=outras.find_all('autores')
                        )

                for outras in tag_tecnica.select('software'):
                    dados = outras.find('dados-basicos-do-software')
                    detal = outras.find('detalhamento-do-software')
                    if dados and detal:
                        producao_e_autores(
                            principal,
                            tipo=tipo_software,
                            titulo=dados.attrs.get('titulo-do-software'),
                            ano=intdef(dados.get('ano'), 0),
                            doi=dados.attrs.get('DOI', ''),
                            idioma=dados.attrs.get('idioma', ''),
                            pais=dados.attrs.get('pais', ''),
                            tag_autores=outras.find_all('autores')
                        )
                    else:
                        seq = outras.attrs.get('sequencia-producao', 0)
                        warnings.append(f'Dados do Software não encontrados {seq}')

                for item in tag_tecnica.select('TRABALHO-TECNICO'):
                    dados = item.find('dados-basicos-do-trabalho-tecnico')
                    detal = item.find('detalhamento-do-trabalho-tecnico')
                    autores = item.find_all('autores')
                    if dados and detal:
                        producao_e_autores(
                            principal,
                            tipo=tipo_tecnica,
                            titulo=dados.attrs.get('titulo-do-trabalho-tecnico', ''),
                            descricao=detal.attrs.get('finalidade'),
                            ano=intdef(dados.attrs.get('ano'), ''),
                            idioma=dados.attrs.get('idioma', ''),
                            pais=dados.attrs.get('pais', ''),
                            tag_autores=autores,
                        )

            # TODO: Inclusão do Préfacio e PósFacio a partir de Produção Técnica

            # Associação das Produções aos projetos
            tipos_producao = {'Trabalho publicado em anais de eventos(Completo)': 'anais',
                              'Artigo publicado em periódicos(Completo)': 'artigo',
                              'Livro publicado': 'LivrosCapitulos',
                              'Textos em Jornais e Revistas': 'midiaimpressa'}

            projetos_tag = soup.find_all('projeto-de-pesquisa')
            projetos_pesquisador = PesquisadorProjeto.objects.filter(pesquisador=principal)
            for projeto in projetos_tag:
                producoes_ct_projeto_tag = projeto.find('producoes-ct-do-projeto')
                nome_projeto = normalize_name(projeto.attrs.get('nome-do-projeto'))
                projeto_pesq = projetos_pesquisador.filter(projeto__nome=nome_projeto).first()
                if producoes_ct_projeto_tag and projeto_pesq:
                    for producao_tag in producoes_ct_projeto_tag.find_all('producao-ct-do-projeto'):
                        titulo_producao = producao_tag.attrs.get('titulo-da-producao-ct')
                        tipo_producao_cod = tipos_producao.get(producao_tag.attrs.get('tipo-producao-ct'))
                        if tipo_producao_cod:
                            hash_producao = generate_hash(titulo_producao)
                            producao = Producao.objects.filter(ident_unico=hash_producao,
                                                               tipo__cod_externo=tipo_producao_cod).first()
                            if producao:
                                if not producao.projeto:
                                    producao.projeto = projeto_pesq.projeto
                                    producao.save()
                                    TOTAIS['projetos_associado'] += 1
                                else:
                                    if not producao.projeto == projeto_pesq.projeto:
                                        warnings.append('Produção (%s) já possui um projeto diferente do'
                                                        ' que está sendo analisado (%s)' %
                                                        (producao, projeto_pesq.projeto))
                            else:
                                warnings.append('Projeto/Produção não encontrado (%s)' % titulo_producao)

        log_object(principal, '\n'.join(warnings))
        transaction.commit()
        adicionar_log(ImportLogLevel.SUCCESS, f'Importação bem sucedida: {principal.nome}')
        if TOTAIS["producao_incluida"] > 0:
            adicionar_log(
                 ImportLogLevel.SUCCESS,
                 f'Produções incluídas: {TOTAIS["producao_incluida"]} / Autores incluídos: {TOTAIS["autor_incluido"]}'
            )
            adicionar_log(ImportLogLevel.SUCCESS, f'Projetos Associados: {TOTAIS["projetos_associado"]}')
            adicionar_log(ImportLogLevel.SUCCESS, f'Projetos incluídos: {TOTAIS["projetos_incluidos"]}')
            adicionar_log(ImportLogLevel.SUCCESS, f'Pesquisadores incluídos em Projetos: '
                                                  f'{TOTAIS["pesquisador_projeto"]}')

    except (ImportXMLException, InvalidXMLException) as e:
        adicionar_log(ImportLogLevel.ERROR, str(e))
        return {'sucesso': False, 'logs': logs}

    return {'sucesso': True, 'logs': logs}


def processar_logs_view(request: HttpRequest, logs_importacao: list[dict[str, Any]]) -> None:
    """
    Consome a lista de logs gerada pela import_xml e as registra no sistema
    de mensagens do Django para exibição na View.

    :param request: O objeto HttpRequest da view atual.
    :param logs_importacao: A lista de dicionários contendo 'nivel' e 'texto'.
    """
    for log in logs_importacao:
        messages.add_message(request, log.get('nivel'), log.get('texto'))
