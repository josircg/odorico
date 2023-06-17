import csv
import datetime
import os
import re
from collections import Counter, namedtuple
from zipfile import ZipFile

from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.views.main import PAGE_VAR
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator, PageNotAnInteger, InvalidPage
from django.db import transaction
from django.db.models import Q
from django.forms import all_valid
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt

from chupalattes import get_lista_paises, get_parse_issn, get_dtupdate, get_producao, get_id_cnpq, \
    get_doi_metadata
from nucleo import clean_doi_url, str_to_date
from nucleo.apps import *
from nucleo.forms import *
from nucleo.models import *
from qualis.models import Periodico, GrandeArea
from utils.text import build_wordcloud


def home(request):
    return render(request, 'home.html')


def handler404(request, *args, **argv):
    template = argv.get('template', '404.html')
    response = render(request, template)
    response.status_code = 404
    return response


def handler500(request, *args, **argv):
    response = render(request, '500.html')
    response.status_code = 500
    return response


def error(request):
    return


def doi_record(request, doi):
    data = get_doi_record(doi, fast=True)
    return HttpResponse(json.dumps(data), content_type='application/json')


def import_html(html, request):
    soup = BeautifulSoup(html, 'html.parser')
    nome = soup.find('h2', attrs={'class': "nome"}).text
    try:
        id = soup.find('div', attrs={'id': "menu-informacoes-complementares"})
        id = id.find('a').get('href').split('id=')[1].split('&')[0]
    except:
        try:
            id = soup.find('span', attrs={'class': "linksFlow"}).find('a').get('href')
            id = id.split('id=')[1].split('&')[0]
        except:
            return None

    base_dir = os.path.join(settings.BASE_DIR, 'cache')
    if not os.path.exists(base_dir):
        os.mkdir(base_dir)
    html_file = open(os.path.join(base_dir, '%s.html' % id), mode='w', encoding='utf-8')
    html_file.write(html)
    html_file.close()

    nome = nome.upper()
    try:
        pesquisador = Pesquisador.objects.get(id_lattes=id)
        if nome != pesquisador.nome.upper():
            messages.warning(request, 'Nome do Pesquisador difere do nome no Lattes: %s' % nome)
        messages.info(request, 'Pesquisador %s atualizado com sucesso' % nome)
    except Pesquisador.DoesNotExist:
        if Pesquisador.objects.filter(nome=nome).count() > 0:
            messages.error(request, 'Já existe um pesquisador com outro ID Lattes no sistema:%s' % nome)
            messages.error(request, 'A importação não foi realizada')
            return redirect('/importacao_lattes/')
        pesquisador = Pesquisador.objects.create(nome=nome, id_lattes=id)
        messages.warning(request, 'Pesquisador %s inserido com sucesso' % nome)
    pesquisador.dtupdate = get_dtupdate(soup)
    pesquisador.id_cnpq = clean_id_cnpq(get_id_cnpq(soup))
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
    return id


def file_upload(request, f):
    save_path = os.path.join(settings.MEDIA_ROOT, 'uploads', f.name)  # cria um path
    path = default_storage.save(save_path, request.FILES['arquivo_zip'])  # salva o arquivo no path
    return default_storage.path(path)  # retorna o path


def get_tipo_producao(cod):
    try:
        return TipoProducao.objects.get(cod_externo=cod)
    except TipoProducao.DoesNotExist:
        raise Exception('Tipo de Produção %s não encontrado' % cod)


def test_doi(doi):
    doi_formatado = clean_doi_url(doi)
    return Producao.objects.filter(doi=doi_formatado).first()


def similar_name(nome):
    nome_normalizado = normalize_name(nome)
    if nome_normalizado:
        nomes = nome_normalizado.split(' ')
        if len(nomes) < 2 or len(nomes[0]) == 1:
            return slugify(nome_normalizado)
        else:
            return slugify(nomes[0] + ' ' + nomes[-1])


def get_or_create_periodico(issn, titulo):
    issn = validate_issn_code(issn)
    periodico = Periodico.objects.filter(issn=issn).first()
    if not periodico:
        periodico = Periodico.objects.filter(eissn=issn).first()

    if not periodico:
        response_issn_api = get_issn(issn)
        if response_issn_api:
            novo_issn, eissn, title, country, url = response_issn_api
            if novo_issn:
                if novo_issn != issn:
                    periodico = Periodico.objects.filter(issn=novo_issn).first()

                if not periodico:
                    if title:
                        title = title.upper().replace('(IMPRESSO)', '').replace('(ONLINE)', '').strip()
                    else:
                        title = titulo

                    if isinstance(url, list):
                        url = url[-1]

                    if url:
                        url = url[:199]

                    periodico = Periodico(issn=novo_issn, eissn=eissn, nome=title, pais=country, url=url)
                    periodico.qualis = 'NC'
                    periodico.dtvalidacao = datetime.datetime.today()
                    periodico.status = 'A'
                    periodico.save()

    return periodico


def import_xml(request, arquivo, nome_obrigatorio):
    # A rede de autores contém todos os autores com relacionamento com o pesquisador que está sendo importado
    # Existem 2 tipos de chaves registradas: o ID_CNPQ e o hash com o nome compactado do autor
    # Dessa forma, o sistema não precisa ir sempre na base para recuperar o pesquisador
    # e consegue encontrar mais facilmente os pesquisadores pelo nome
    rede = {}

    # Contador de registros processados
    TOTAIS = Counter()

    def get_or_create_rede(nome, pesquisador=None, id_cnpq=None):
        if not nome and pesquisador:
            nome = pesquisador.nome

        if not nome:
            return

        chave = similar_name(nome)
        record = rede.get(chave)
        if record:
            pesquisador = record.get('pesquisador')
            if pesquisador:
                if id_cnpq and id_cnpq != pesquisador.id_cnpq:
                    messages.warning(request, 'ID CNPQ mismatch: %s %s' % (id_cnpq, record.get('id_cnpq')))
                    chave = '#%s' % pesquisador.id_cnpq
                    record = None

                if id_cnpq and normalize_name(nome) != normalize_name(pesquisador.nome):
                    short_name = pesquisador.nome.split()[0] + ' ' + pesquisador.nome.split()[-1]
                    short_name2 = nome.split()[0] + ' ' + nome.split()[-1]
                    if normalize_name(short_name) != normalize_name(short_name2):
                        if ',' in nome:
                            inverted_name = nome.split(',')
                            inverted_name = inverted_name[-1] + ' ' + inverted_name[0]
                        else:
                            inverted_name = ''
                        if normalize_name(inverted_name) != normalize_name(pesquisador.nome):
                            messages.warning(request, 'Name mismatch: %s %s' % (nome, pesquisador.nome))

        if not record:
            nome = normalize_name(nome)
            record = {'nome': nome, 'pesquisador': pesquisador}
            rede[chave] = record

        if not record.get('pesquisador', None) and id_cnpq:
            pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
            if not pesquisador:
                pesquisador = Pesquisador(nome=nome, id_cnpq=id_cnpq)
                pesquisador.save()
                TOTAIS['autor_incluido'] += 1

        if not pesquisador:
            pesquisador = Pesquisador.objects.filter(nome__exact=nome)
            if pesquisador.count() > 1:
                messages.warning(request, 'Homonimo: %s' % nome)
                pesquisador = None
            else:
                pesquisador = pesquisador.first()

        rede[chave]['pesquisador'] = pesquisador

        return record

    def producao_e_autores(pesquisador, tipo, doi=None, titulo=None, issn=None, titulo_periodico=None,
                           isbn=None, editora=None, idioma=None,
                           ano=None, serie=None, volume=None,
                           nome_evento=None, pais=None, instituicao=None,
                           tag_autores=None, natureza_obra=None, meio=None, tipo_obra=None):

        producao = None
        if doi:
            producao = Producao.objects.filter(doi=doi).first()

        elif isbn:
            producao = Producao.objects.filter(isbn=isbn).first()

        hash_ident = generate_hash(titulo)
        if not producao and hash_ident:
            producao = Producao.objects.filter(ident_unico=hash_ident, tipo=tipo).first()

        if issn:
            periodico = get_or_create_periodico(issn, titulo_periodico)
        else:
            periodico = None

        if pais: pais = pais[:20]

        if producao:
            if ano != 1900 or not producao.ano:
                producao.ano = ano
            producao.serie = serie
            producao.volume = volume
            producao.pais = pais
            producao.idioma = idioma
            for rec in producao.producaoautor_set.select_related('autor').all():
                get_or_create_rede(rec.nome, rec.autor)

        else:
            producao = Producao.objects.create(
                titulo=titulo, ident_unico=hash_ident, doi=doi, isbn=isbn,
                ano=ano, serie=serie, volume=volume,
                pesquisador=pesquisador, tipo=tipo,
                natureza_obra=natureza_obra, meio=meio, tipo_obra=tipo_obra,
            )
            TOTAIS['producao_incluida'] += 1

        if tipo.cod_externo == 'TrabalhosPublicadosAnaisCongresso' or tipo.cod_externo == 'ApresentacoesTrabalho':
            descricao = titulo + '. ' + tipo.descricao
            if nome_evento:
                descricao = descricao + '. ' + nome_evento
            if instituicao:
                descricao = descricao + '. ' + instituicao
            producao.descricao = descricao

        elif tipo.cod_externo == 'LivrosCapitulos' or tipo.cod_externo == 'CapitulosLivrosPublicados':
            producao.descricao = titulo + '. ' + editora

        if periodico:
            producao.periodico = periodico

        if natureza_obra:
            producao.natureza_obra = find_key_by_value(dict_livros_e_capitulos, natureza_obra)

        if meio:
            producao.meio = find_key_by_value(dict_livros_e_capitulos, meio)

        if tipo_obra:
           producao.tipo_obra = find_key_by_value(dict_livros_e_capitulos, tipo_obra)

        producao.save()

        for tag in tag_autores:
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
                prod_autor.ordem = tag.attrs.get('ordem-de-autoria', '')
                prod_autor.save()
            except ProducaoAutor.MultipleObjectsReturned:
                pass

            if included:
                TOTAIS['novos_autores'] += 1

    if not isinstance(arquivo, str):
        # caso não seja str decodificar
        arquivo.seek(0)
        arquivo = arquivo.read().decode('ISO-8859-1')

    soup = BeautifulSoup(arquivo, 'lxml')
    try:
        cv = soup.find('curriculo-vitae')
        dg = cv.find('dados-gerais')
    except:
        raise Exception('Arquivo XML inválido')

    principal = None
    nome = normalize_name(dg.attrs.get('nome-completo', ''))
    if nome_obrigatorio and nome_obrigatorio != nome:
        raise Exception('Nome do pesquisador incompatível com o registro do Lattes')

    id_cnpq = cv.attrs.get('numero-identificador', '')
    orcid = dg.attrs.get('orcid-id', '')

    path = os.path.join(settings.BASE_DIR, 'data', id_cnpq + '.xml')
    with open(path, 'w') as writer:  # grava o arquivo em "/data/"
        writer.write(soup.decode())

    transaction.set_autocommit(False)
    if id_cnpq:
        principal = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
        if not principal:
            principal = Pesquisador.objects.filter(nome=nome, id_cnpq__isnull=True)
            if principal:
                if principal.count() > 1:
                    messages.error(request, 'Existe mais de um pesquisador com o nome %s' % nome)
                    return
                principal = principal.first()
                principal.id_cnpq = clean_id_cnpq(id_cnpq)
            else:
                principal = Pesquisador.objects.create(id_cnpq=id_cnpq, nome=nome)
    else:
        messages.error(request, 'ID CNPQ não encontrado no XML')
        return

    if orcid:
        principal.orcid = clean_orcid(orcid)

    # TODO: Cadastrar a data em que o Lattes foi importado
    principal.nome = nome
    principal.dtupdate = str_to_date(cv.attrs['data-atualizacao'])
    principal.atualizado = True
    principal.save()

    get_or_create_rede(nome, principal)

    tipo_artigo = get_tipo_producao('artigo')
    tipo_congresso = get_tipo_producao('TrabalhosPublicadosAnaisCongresso')
    tipo_livro = get_tipo_producao('LivrosCapitulos')
    tipo_capitulo = get_tipo_producao('CapitulosLivrosPublicados')
    tipo_apresentacao = get_tipo_producao('ApresentacoesTrabalho')
    tipo_software = get_tipo_producao('SoftwareSemPatente')

    tag_producao = cv.find('producao-bibliografica')

    if soup.find_all('projeto-de-pesquisa'):
        for projeto_pesquisa in soup.find_all('projeto-de-pesquisa'):
            responsavel_projeto = list(filter(lambda p: p.attrs.get('flag-responsavel') == 'SIM',
                                              projeto_pesquisa.find_all('integrantes-do-projeto')))
            integrantes = projeto_pesquisa.find_all('integrantes-do-projeto')

            nome_projeto = projeto_pesquisa.attrs.get('nome-do-projeto').upper()
            if not responsavel_projeto:
                messages.warning(request, 'Projeto %s não possui nenhum responsavel' % nome_projeto)
                continue

            responsavel_projeto = responsavel_projeto[0].attrs
            nome_lider_projeto = normalize_name(responsavel_projeto.get('nome-completo'))
            id_lider_projeto = responsavel_projeto.get('nro-id-cnpq', None)
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
                            nome=nome_projeto,
                            descricao=projeto_pesquisa.attrs.get('descricao-do-projeto'),
                            proponente=lider,
                            linha=linha
                        )
                        TOTAIS['projetos_incluidos'] += 1
            else:
                projeto = None

            if projeto:
                projeto.status = STATUS_INATIVA \
                    if projeto_pesquisa.attrs.get('situacao') == 'CONCLUIDO' else STATUS_ATIVO
                projeto.save()

            for integrante in integrantes:
                # se for o pesquisador responsavel não procurar novamente
                nome_integrante = normalize_name(integrante.attrs.get('nome-completo'))
                id_integrante = integrante.attrs.get('nro-id-cnpq')

                # insere integrante do projeto na rede do autores
                record = get_or_create_rede(nome_integrante, id_cnpq=id_integrante)
                pesquisador = record.get('pesquisador')
                if pesquisador and projeto:
                    _, created = PesquisadorProjeto.objects.get_or_create(pesquisador=pesquisador, projeto=projeto)
                    if created:
                        TOTAIS['pesquisador_projeto'] += 1

    if tag_producao:
        #  Artigos em Periódicos
        tag_artigos = tag_producao.find('artigos-publicados')
        if tag_artigos:
            for art in tag_artigos.select('artigo-publicado'):
                dados = art.find('dados-basicos-do-artigo')
                detal = art.find('detalhamento-do-artigo')
                producao_e_autores(
                    principal, tipo_artigo, doi=clean_doi_url(dados.attrs.get('doi', '')),
                    titulo=dados.attrs.get('titulo-do-artigo', ''),
                    issn=detal.attrs.get('issn'),
                    titulo_periodico=detal.attrs.get('titulo-do-periodico-ou-revista'),
                    ano=intdef(dados.attrs['ano-do-artigo'], 1900),
                    idioma=dados.attrs.get('idioma', ''),
                    volume=detal.attrs.get('volume', ''),
                    serie=detal.attrs.get('serie', ''),
                    tag_autores=art.find_all('autores'),
                )

        # Trabalhos em eventos
        tag_eventos = tag_producao.find('trabalhos-em-eventos')
        if tag_eventos:
            for tra_even in tag_eventos.select('trabalho-em-eventos'):
                dados = tra_even.find('dados-basicos-do-trabalho')
                detal = tra_even.find('detalhamento-do-trabalho')
                producao_e_autores(
                    principal,
                    tipo=tipo_congresso,
                    titulo=dados.attrs.get('titulo-do-trabalho', ''),
                    doi=dados.attrs.get('doi', ''),
                    isbn=detal.attrs.get('isbn', ''),
                    nome_evento=detal.attrs.get('nome-do-evento', ''),
                    pais=dados.attrs.get('pais-do-evento', ''),
                    ano=intdef(detal.attrs.get('ano-de-realizacao'), 1900),
                    volume=detal.attrs.get('volume', ''),
                    serie=detal.attrs.get('serie', ''),
                    idioma=dados.attrs.get('idioma', ''),
                    tag_autores=detal.find_all('autores'),
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
                        doi=dados.attrs.get('doi', ''),
                        isbn=detal.attrs.get('isbn', ''),
                        ano=intdef(dados.attrs.get('ano'), 1900),
                        idioma=dados.attrs.get('idioma', ''),
                        tag_autores=detal.find_all('autores'),
                        editora=detal.attrs.get('nome-da-editora', '') + '.' + detal.attrs.get('cidade-da-editora', ''),
                        natureza_obra=dados.attrs.get('natureza'),
                        meio=dados.attrs.get('meio-de-divulgacao'),
                        tipo_obra=dados.attrs.get('tipo'),
                    )

            tag_livros = tag_livros_e_capitulos.find('capitulos-de-livros-publicados')
            if tag_livros:
                for livro in tag_livros.select('capitulos-de-livros-publicados'):
                    dados = livro.find('dados-basicos-do-livro')
                    detal = livro.find('detalhamento-do-livro')
                    producao_e_autores(
                        principal,
                        tipo=tipo_capitulo,
                        titulo=dados.attrs.get('titulo-do-livro', ''),
                        doi=dados.attrs.get('doi', ''),
                        isbn=detal.attrs.get('isbn', ''),
                        ano=intdef(dados.attrs.get('ano'), 1900),
                        idioma=dados.attrs.get('idioma', ''),
                        tag_autores=detal.find_all('autores'),
                        editora=detal.attrs.get('nome-da-editora', '') + '.' + detal.attrs.get('cidade-da-editora', ''),
                        meio=dados.attrs.get('meio-de-divulgacao'),
                        tipo_obra=dados.attrs.get('tipo'),
                    )

        tag_apresentacao = soup.find('producao-tecnica')
        if tag_apresentacao:
            for apresentacao in tag_apresentacao.select('apresentacao-de-trabalho'):
                dados = apresentacao.find('dados-basicos-da-apresentacao-de-trabalho')
                detal = apresentacao.find('detalhamento-da-apresentacao-de-trabalho')
                producao_e_autores(
                    principal,
                    tipo=tipo_apresentacao,
                    titulo=dados.attrs.get('titulo', ''),
                    ano=intdef(dados.get('ano'), 1900),
                    doi=dados.attrs.get('doi', ''),
                    nome_evento=detal.attrs.get('nome-do-evento', ''),
                    instituicao=detal.attrs.get('instituicao-promotora', ''),
                    idioma=dados.attrs.get('idioma', ''),
                    pais=dados.attrs.get('pais', ''),
                    tag_autores=detal.find_all('autores'),
                )

        tag_producaoTecnica = soup.find('PRODUCAO-TECNICA')
        if tag_producaoTecnica:
            for producao in tag_producaoTecnica.select('SOFTWARE'):
                dados = producao.find('DADOS-BASICOS-DO-SOFTWARE')
                detal = producao.find('DETALHAMENTO-DO-SOFTWARE')
                producao_e_autores(
                    principal,
                    tipo=tipo_software,
                    titulo=dados.attrs.get('TITULO-DO-SOFTWARE'),
                    ano=intdef(dados.get('ANO'), ''),
                    doi=dados.attrs.get('DOI', ''),
                    idioma=dados.attrs.get('IDIOMA', ''),
                    pais=dados.attrs.get('PAIS', ''),
                    tag_autores=detal.attrs.find_all('AUTORES')
                )

        # software = tag_apresentacao.find_all("software")

        # TODO: Inclusão do Préfacio e PósFacio a partir de Produção Técnica

        # Associação das Produções aos projetos
        tipos_producao = {'Trabalho publicado em anais de eventos(Completo)': 'TrabalhosPublicadosAnaisCongresso',
                          'Artigo publicado em periódicos(Completo)': 'artigo',
                          'Livro publicado': 'LivrosCapitulos'}

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
                                    messages.error(request,
                                                   'Produção (%s) já possui um projeto diferente do'
                                                   ' que está sendo analisado (%s)' %
                                                   (producao, projeto_pesq.projeto))
                        else:
                            messages.error(request,
                                           'Projeto/Produção não encontrado (%s)' % titulo_producao)

        transaction.commit()
        messages.success(request, 'Importação bem sucedida: %s' % principal.nome)
        messages.success(request, 'Produções incluídas: %d' % TOTAIS['producao_incluida'])
        messages.success(request, 'Projetos Associados: %d' % TOTAIS['projetos_associado'])
        messages.success(request, 'Autores incluídos: %d' % TOTAIS['autor_incluido'])
    else:
        transaction.commit()
        messages.success(request, 'Importado com sucesso! (Obs.: Sem produções bibliográficas)')

    messages.success(request, 'Projetos incluídos: %d' % TOTAIS['projetos_incluidos'])
    messages.success(request, 'Pesquisadores incluídos em Projetos: %d' % TOTAIS['pesquisador_projeto'])


def importacao_lattes(request, hash=None):
    try:
        if request.user.is_authenticated:
            nome_obrigatorio = None
            relatorio_anual = None
        else:
            relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'),
                                                hash_auth=hash)
            nome_obrigatorio = relatorio_anual.pesquisador.nome.upper()

        if request.method == 'POST':
            form = ImportForm(request.POST, request.FILES, has_hash=relatorio_anual is not None)

            if form.is_valid():
                arquivo_zip = request.FILES.get('arquivo_zip')
                arquivo_xml = request.FILES.get('arquivo_xml')

                try:
                    if arquivo_zip:
                        zipfile = ZipFile(arquivo_zip.file, 'r')

                        for xml_name in zipfile.namelist():
                            arquivo_xml = zipfile.open(xml_name)
                            import_xml(request, arquivo_xml, nome_obrigatorio)
                    elif arquivo_xml:
                        import_xml(request, arquivo_xml, nome_obrigatorio)
                    else:
                        raise Exception('Nenhum arquivo enviado')

                except Exception as e:
                    messages.error(request, e)

                if relatorio_anual is not None:
                    to = relatorio_anual.get_absolute_url()
                else:
                    to = 'importacao_lattes'

                return redirect(to)
        else:
            form = ImportForm(has_hash=relatorio_anual is not None)

        return render(request, 'import_lattes.html', {'form': form, 'aluno': hash})
    except Http404:
        if hash is not None:
            return handler404(request, template='avaliacao_anual_404.html')
        else:
            raise


def importacao_dummy(request):
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            messages.info(request, 'Importação bem sucedida')
            return redirect('/importacao_dummy/')
        else:
            messages.error(request, 'Grave algum texto')
    else:
        form = ImportForm()

    return render(request, 'import_dummy.html', {'form': form})


@xframe_options_exempt
def agenda_defesas(request):
    context = {}
    today = datetime.date.today()
    quali = Matricula.objects.filter(dtquali__gte=today).order_by('dtquali')
    dataset = quali.values_list('pesquisador__nome', 'curso__descricao', 'dtquali', 'titulo', 'pesquisador__id')
    result = []
    for reg in dataset:
        result.append({
            'titulo': reg[3],
            'aluno': reg[0],
            'tipo': 'Qualificação de %s' % reg[1],
            'orientador': Aluno.objects.get(id=reg[4]).orientador,
            'data': reg[2],
            'local': 'IBICT - 4º andar - Sala de Reuniões',
        })

    defesa = Matricula.objects.filter(dtdefesa__gte=today).order_by('dtdefesa')
    dataset = defesa.values_list('pesquisador__nome', 'curso__descricao', 'dtdefesa', 'titulo', 'pesquisador__id')
    for reg in dataset:
        result.append({
            'titulo': reg[3],
            'aluno': reg[0],
            'tipo': 'Defesa de %s' % reg[1],
            'orientador': Aluno.objects.get(id=reg[4]).orientador,
            'data': reg[2],
            'local': 'IBICT - 4º andar - Sala de Reuniões',
        })

    result = sorted(result, key=lambda i: i['data'])

    context['valores'] = result
    return render(request, 'agenda_defesas.html', {'result': context})


@xframe_options_exempt
@csrf_exempt
def defesas_realizadas(request):
    context = {}
    result = []

    try:
        mes = int(request.GET.get('mes')) if request.GET.get('mes') else 0
        ano = int(request.GET.get('ano')) if request.GET.get('ano') else 0
        if mes and ano:
            defesa = Matricula.objects.filter(dtdefesa__month=mes, dtdefesa__year=ano)
            dataset = defesa.values_list('pesquisador__nome', 'curso__descricao', 'dtdefesa', 'titulo',
                                         'pesquisador__id')

            keys = ['Título', 'Aluno', 'Tipo', 'Orientador(a)', 'Data']

            for reg in dataset:
                result.append({
                    'Título': reg[3],
                    'Aluno': reg[0],
                    'Tipo': 'Defesa de %s' % reg[1],
                    'Orientador(a)': Aluno.objects.get(id=reg[4]).orientador,
                    'Data': reg[2],
                })

            quali = Matricula.objects.filter(dtquali__month=mes, dtquali__year=ano)
            dataset = quali.values_list('pesquisador__nome', 'curso__descricao', 'dtquali', 'titulo', 'pesquisador__id')
            for reg in dataset:
                result.append({
                    'Título': reg[3],
                    'Aluno': reg[0],
                    'Tipo': 'Qualificação de %s' % reg[1],
                    'Orientador(a)': Aluno.objects.get(id=reg[4]).orientador,
                    'Data': reg[2],
                })

            result = sorted(result, key=lambda i: i['Data'])
            context['valores'] = result
            context['keys'] = keys
        else:
            context['valores'] = result

    except ValueError:
        pass

    return render(request, 'defesas_realizadas.html', {'result': context})


def normaliza_matriz(queryset):
    matriz_default = {'A1': 0, 'A2': 0, 'A3': 0, 'A4': 0, 'B1': 0, 'B2': 0, 'B3': 0, 'B4': 0, 'C': 0,
                      'ND': 0, 'NC': 0, 'TOTAL': 0}
    for rec in queryset:
        qualis = rec['producao__periodico__qualis']
        count = rec['cnt']
        if nvl(qualis, '*') in matriz_default:
            matriz_default[qualis] = count
        else:
            matriz_default['ND'] = count

        matriz_default['TOTAL'] += count

    return matriz_default


def resumo_qualis(request, id):
    context = {}
    result = []
    context['labels'] = \
        [{'value': 'Pesquisador', 'style': '500px;'},
         {'value': 'A1', 'style': '50px;'},
         {'value': 'A2', 'style': '50px;'},
         {'value': 'A3', 'style': '50px;'},
         {'value': 'A4', 'style': '50px;'},
         {'value': 'B1', 'style': '50px;'},
         {'value': 'B2', 'style': '50px;'},
         {'value': 'B3', 'style': '50px;'},
         {'value': 'B4', 'style': '50px;'},
         {'value': 'C', 'style': '50px;'},
         {'value': 'ND', 'style': '50px;'},
         {'value': 'NC', 'style': '50px;'},
         {'value': 'TOTAL', 'style': '50px;'},
         ]
    ultimos_anos = [now().year - i for i in range(4)]
    tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
    total_professores = 0
    try:
        programa = Programa.objects.get(id=id)
        for r in PesquisadorPrograma.objects.filter(programa=programa):
            total_professores += 1
            producoes = ProducaoAutor.objects.filter(autor=r.pesquisador, producao__tipo=tipo_artigo,
                                                     producao__ano__in=ultimos_anos). \
                values('producao__periodico__qualis').annotate(cnt=Count('producao__id'))

            matriz = normaliza_matriz(producoes)
            result.append({
                'Pesquisador': r.pesquisador.nome,
                **matriz
            })

        result = sorted(result, key=lambda i: i['Pesquisador'])

        context['values'] = result
        context['soma'] = total_professores
        context['titulo'] = 'Resumo Qualis de %d a %d - PPG %s' % (ultimos_anos[-1], ultimos_anos[0],
                                                                   programa.descricao)

        producoes = ProducaoAutor.objects.filter(autor__pesquisadorprograma__programa=programa,
                                                 producao__tipo=tipo_artigo, producao__ano__in=ultimos_anos). \
            values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))
        matriz = normaliza_matriz(producoes)
        context['totalizadores'] = [{
            'TOTAL_PESQUISADORES': context['soma'],
            **matriz
        }]

    except Programa.DoesNotExist:
        context['titulo'] = 'Programa %d não encontrado.' % id
        context['labels'] = []

    if request.POST:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="resumo_qualis.csv"'
        header = list(map(lambda la: la['value'], context['labels']))
        csv_intl = csv.DictWriter(response, fieldnames=header, delimiter=',', quotechar='"',
                                  quoting=csv.QUOTE_MINIMAL)
        csv_intl.writeheader()

        for row in result:
            csv_intl.writerow(row)

        csv_intl.writerow(matriz)

        return response

    else:
        return render(request, 'resumo_qualis.html', {'result': context})


def producao_projeto(request, id_lattes):
    context = {}
    result = []
    producoes = []
    context['total'] = 0

    pesquisador = Pesquisador.objects.filter(id_lattes=id_lattes)
    if pesquisador:
        producoes = Producao.objects.filter(pesquisador=pesquisador.get(), ano__gte=2017).order_by('tipo', 'ano')
        producoes = producoes.values_list('titulo', 'projeto__nome', 'id', 'sem_projeto')
        context['total'] = producoes.count()
        context['titulo'] = 'Produção x Projeto - %s' % pesquisador.get()

    for producao in producoes:
        if producao[3]:
            result.append({
                'titulo': producao[0][:360] + '...',
                'projeto': 'Fora do Programa',
                'id': producao[2]
            })
        else:
            result.append({
                'titulo': producao[0][:360] + '...',
                'projeto': producao[1],
                'id': producao[2]
            })

    context['values'] = result
    context['labels'] = \
        [{'value': 'Título'},
         {'value': 'Projeto'}, ]

    return render(request, 'producao_projeto.html', {'result': context})


def producao_edit(request, id):
    context = {}
    producao = Producao.objects.get(id=id)
    projetos_pesquisador = list(PesquisadorProjeto.objects.filter(pesquisador=producao.pesquisador))

    if request.method == 'POST':
        sem_projeto = request.POST['sem_projeto']
        if sem_projeto == 'True':
            producao.projeto = None
            producao.sem_projeto = True
            producao.save()
        else:
            projeto_id = request.POST['projeto']
            projeto_pesquisa = ProjetoPesquisa.objects.get(id=projeto_id)
            producao.projeto = projeto_pesquisa
            producao.sem_projeto = sem_projeto
            producao.save()

        producoes = Producao.objects.filter(pesquisador=producao.pesquisador,
                                            ano__gte=2017,
                                            projeto__isnull=True, sem_projeto=False).order_by('tipo', 'ano')
        if producoes.count() == 0:
            # Se o não encontrar proximo redireciona pra listagem
            messages.info(request, 'Todas as produções já foram associadas. Obrigado!')
            return redirect('producao_projeto', producao.pesquisador.id_lattes)
        else:
            return redirect('producao_edit', producoes[0].id)

    if producao.projeto:
        context['projeto_select'] = producao.projeto.id
    else:
        context['projeto_select'] = 0

    context['titulo'] = 'Produção x Projeto - %s' % producao.pesquisador
    context['tipo'] = producao.tipo.descricao
    context['lattes'] = producao.pesquisador.id_lattes
    context['producao'] = producao
    context['projetos'] = projetos_pesquisador

    return render(request, 'producao_edit.html', {'result': context})


def linha_professor(request, id_linha):
    professores = PesquisadorPrograma.objects.all()
    professor_linha = ProfessorLinha.objects.filter(linha=id_linha)
    professores_id = []
    for pl in professor_linha:
        for prof in professores:
            if pl.professor == prof.pesquisador:
                professores_id.append({
                    'id': pl.professor.id,
                    'name': pl.professor.nome,
                })

    return HttpResponse(json.dumps(professores_id), content_type='application/json')


def novo_projeto(request, id_lattes):
    context = {}
    professor = Pesquisador.objects.filter(id_lattes=id_lattes)
    if professor:
        if request.method == 'GET':
            url_redirect = '/' + request.GET['redirect'].split("'")[1]
            request.session['redirect'] = url_redirect
        elif request.method == 'POST':
            pesquisador_linha = ProfessorLinha.objects.filter(professor=professor.get())
            if pesquisador_linha:
                if request.POST['titulo']:
                    projeto = ProjetoPesquisa.objects.create(
                        nome=request.POST['titulo'],
                        proponente=professor.get(),
                        linha=pesquisador_linha[0].linha)
                    PesquisadorProjeto.objects.get_or_create(projeto=projeto, pesquisador=projeto.proponente)
                    return redirect(request.session['redirect'])
                else:
                    messages.error(request, 'Informe o título do projeto. Ele é obrigatório.')
            else:
                messages.warning(request, 'Este pesquisador não está em nehuma linha de pesquisa.')
        context['id_lattes'] = id_lattes
        context['professor'] = professor
    else:
        messages.warning(request, 'Não existe nenhum pesquisador com esse id lattes')
    return render(request, 'novo_projeto.html', {'result': context})


def producao_analise(request, id_producao):
    producao = Producao.objects.get(id=id_producao)
    tipo = TipoProducao.objects.get(id=producao.tipo_id).cod_externo
    if tipo == 'artigo':
        # buscar DOI, confere ano da publicação e título do artigo
        if not producao.periodico:

            if producao.doi:
                producao.doi = clean_doi_url(producao.doi)
                issn = get_doi_metadata(producao.doi)
            else:
                issn = None

            if not issn:
                issn = get_parse_issn(producao.descricao)

            if issn:
                periodico = Periodico.objects.filter(Q(issn=issn) | Q(eissn=issn)).first()
                if periodico:
                    producao.periodico = periodico
                    messages.success(request, 'Revista associada. ISSN: %s' % issn)
                else:
                    messages.success(request, 'ISSN (%s) encontrado mas o periódico não está registrado na base' % issn)
            else:
                messages.warning(request, 'ISSN não encontrado. Selecione a revista manualmente.')

        # Esse é para os casos em que o título foi importado via HTML
        # Quando todos tiverem sido convertidos, esse if pode morrer
        if not producao.descricao:
            producao.descricao = producao.titulo

        producao.titulo = parse_titulo(producao.descricao)
        producao.save()

    return HttpResponseRedirect(reverse('admin:nucleo_producao_change', args=(id_producao,)))


def mapa_paises(request):
    context = {}

    # obtem os pesquisadores que farão parte do relatório
    id = request.GET.get('id')
    programa = Programa.objects.filter(id=id)
    if not programa.exists():
        messages.error(request, 'Programa %s não encontrado' % id)
        return redirect('/admin')

    queryset = programa.values_list('pesquisadorprograma__pesquisador__nome', flat=True). \
        order_by('pesquisadorprograma__pesquisador__nome')

    # obtem a lista de países
    paises = get_lista_paises()

    # Monta total por país
    totais = Counter()
    for pesq in queryset:
        producoes = Producao.objects.filter(pesquisador__nome__exact=pesq, ano__in=(2017, 2018, 2019, 2020),
                                            pais__isnull=False)
        for producao in producoes:
            totais[producao.pais.upper()] += 1

    # monta os dados do javascript que serão adicionados no template
    points = []
    for item in totais.most_common(50):
        pais = list(filter(lambda rec: rec['iso3'] == item[0], paises))
        # print('%s: %d' % (pais[0]['nome'], item[1]))
        if pais:
            points.append({
                'lat': pais[0]['latitude'],
                'lng': pais[0]['longitude'],
                'pais': pais[0]['nome'],
                'qtd': item[1],
            })

    context['id'] = id
    context['marker'] = points
    context['titulo'] = '2017-2020 %s' % programa[0].descricao
    context['api_key'] = settings.GEO_API

    return render(request, 'mapa_paises.html', {'result': context})


def mapa_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="mapa.csv"'

    # obtem os pesquisadores que farão parte do relatório
    id = request.GET['id']
    programa = Programa.objects.filter(id=id)
    if not programa.exists():
        messages.error(request, 'Programa %d não encontrado' % id)
        return redirect('/admin')

    queryset = programa.values_list('pesquisadorprograma__pesquisador__nome', flat=True). \
        order_by('pesquisadorprograma__pesquisador__nome')

    fieldnames = ['id_lattes', 'tipo', 'titulo', 'doi', 'pais']
    csv_intl = csv.DictWriter(response, fieldnames=fieldnames, delimiter=',', quotechar='"',
                              quoting=csv.QUOTE_MINIMAL)
    csv_intl.writeheader()

    for pesq in queryset:
        for producao in Producao.objects.filter(pesquisador__nome__exact=pesq, ano__in=(2017, 2018, 2019, 2020),
                                                pais__isnull=False):
            csv_intl.writerow(
                {"id_lattes": producao.pesquisador.id_lattes, "tipo": producao.tipo, "titulo": producao.titulo,
                 'doi': producao.doi})
        for producao in Producao.objects.filter(pesquisador__nome__exact=pesq,
                                                ano__in=(2017, 2018, 2019, 2020),
                                                pais__isnull=False):
            csv_intl.writerow({"id_lattes": producao.pesquisador.id_lattes,
                               "tipo": producao.tipo,
                               "titulo": producao.titulo,
                               "doi": producao.doi,
                               "pais": producao.pais})
    return response


def qualis_resumo(request, programa_ids):
    from nucleo.actions import view_resumo_qualis
    programa_ids_clean = list(filter(lambda id: not id == '-' and not id == '', programa_ids.split('-')))

    if programa_ids_clean:
        programas = Programa.objects.filter(pk__in=programa_ids_clean)
        return view_resumo_qualis(None, request, programas)

    messages.error(request, 'A URL informada espera um intervalo de números válido de ID´s. Ex.: 1-11-9')
    return redirect(reverse('admin:index'))


def counter_areas(soup):
    areas_conhecimento = soup.find_all(re.compile('^area-do-conhecimento'))
    contador_areas = Counter()
    for area_conhecimento in areas_conhecimento:
        if area_conhecimento.attrs.get('nome-da-area-do-conhecimento'):
            dado = []
            garea = area_conhecimento.get('nome-grande-area-do-conhecimento', '').replace('_', ' ')
            dado.append(garea)
            dado.append(area_conhecimento.get('nome-da-area-do-conhecimento'))
            if area_conhecimento.get('nome-da-sub-area-do-conhecimento'):
                dado.append(area_conhecimento.get('nome-da-sub-area-do-conhecimento'))
            area = ','.join(dado)
            contador_areas[area] += 1

    areas_ordered = sorted(contador_areas.items(), key=lambda area: area[1], reverse=True)
    return areas_ordered


def lattes_resumo(request, id_lattes_params=None):
    header = {'dicas': ('Dica',), 'areas_conhecimento': ('Nome',), 'artigos_publicados': ('Título',),
              'capitulos_publicados': ('Título',), 'eventos': ('Título',),
              'producao_tecninca': ('Título',)
              }

    context = {'dicas': [], 'processado': False, 'areas_conhecimento': [], 'artigos_publicados': [],
               'header': header, 'capitulos_publicados': [], 'eventos': [], 'producao_tecnica': [],
               'palavras-chave': []
               }

    def normalize_enconding(text: str, encoding='ISO-8859-1'):
        try:
            return text.encode(encoding).decode()
        except UnicodeError:
            return text

    def get_curriculo_proxylattes(id_cnpq):
        response = requests.get('http://proxylattes.irdx.com.br/get/%s' % id_cnpq)
        if response.ok:
            arquivo = response.text.encode().decode()
            soup = BeautifulSoup(arquivo, 'lxml')
            if soup.find('curriculo-vitae'):
                return soup, arquivo
        return None, None

    def processar_xml(arquivo, gravar_xml=True, validar_proxy=True, download_csv=False):
        if not isinstance(arquivo, str):  # caso não seja str decodificar
            arquivo = arquivo.read().decode('ISO-8859-1')

        totais = Counter()
        last_years = [str(now().year - i) for i in range(5)]
        titulos = []
        try:
            soup = BeautifulSoup(arquivo, 'lxml')
            informacoes_curriculo = soup.find('curriculo-vitae')
            id_cnpq = informacoes_curriculo.get('numero-identificador')
            dados_gerais = soup.find('dados-gerais')
            if not dados_gerais:
                raise Exception('Dados gerais não encontrados no XML')
        except:
            raise Exception('Erro ao analisar o currículo, certifique-se que este xml é um currículo lattes válido.')

        id_cnpq = informacoes_curriculo.get('numero-identificador')
        context['identificador'] = id_cnpq

        if validar_proxy:
            curriculo_proxy_lattes, xml_proxy = get_curriculo_proxylattes(id_cnpq)

            if curriculo_proxy_lattes:
                dados_gerais_proxy = curriculo_proxy_lattes.find('dados-gerais')
                informacoes_curriculo_proxy = curriculo_proxy_lattes.find('curriculo-vitae')
                if dados_gerais_proxy.get('nome-completo') == dados_gerais.get('nome-completo'):
                    data_proxy = datetime.datetime.strptime(
                        '%s' % informacoes_curriculo_proxy.get('data-atualizacao'), '%d%m%Y')
                    data_xml = datetime.datetime.strptime('%s' % informacoes_curriculo.get('data-atualizacao'),
                                                          '%d%m%Y')
                    if data_xml <= data_proxy:
                        arquivo = xml_proxy

                else:
                    messages.error(request, 'O nome do pesquisador não está compatível com o currículo Lattes')

        # conteudo
        artigos_academicos = soup.find_all('artigo-publicado')
        capitulos_publicados = soup.find_all('capitulo-de-livro-publicado')
        eventos = soup.find_all('trabalho-em-eventos')
        producao_tecnica = soup.find('producao-tecnica')

        # grava o xml
        if gravar_xml:
            path = os.path.join(settings.MEDIA_ROOT, 'uploads', 'lattes')
            os.makedirs(path, exist_ok=True)
            f = open(os.path.join(path, '%s.xml' % id_cnpq), 'w')
            f.write(arquivo)
            f.close()

        if not dados_gerais.get('orcid-id'):
            context['dicas'].append('Informe o seu ORCID no Lattes. Caso você ainda não tenha, '
                                    'não deixe de criar pois esse código é muito importante para que sistemas e'
                                    ' revistas internacionais associem o seu currículo à sua produção')

        context['pesquisador'] = '<a target="_blank" href="/lattes-resumo/%s">%s</a>' % \
                                 (id_cnpq, dados_gerais.attrs.get('nome-completo'))

        areas_conhecimento = counter_areas(soup)
        for area_str, qtd in areas_conhecimento[:5]:
            areas_splited = area_str.split(',')
            grande_area = GrandeArea.objects.filter(nome__icontains=areas_splited[0]).values_list(
                'nome',
                flat=True).first()
            if grande_area:
                areas_splited[0] = grande_area

            context['areas_conhecimento'].append(' > '.join(areas_splited))

        for artigo in artigos_academicos:
            dados_basicos = artigo.find('dados-basicos-do-artigo')
            if dados_basicos.get('ano-do-artigo') in last_years:
                palavras_chaves = artigo.find('palavras-chave')
                if palavras_chaves and palavras_chaves.attrs:
                    palavras_chaves = list(palavras_chaves.attrs.values())
                    context['palavras-chave'] += palavras_chaves

                titulo = normalize_enconding(dados_basicos.get('titulo-do-artigo'))
                titulos.append(titulo)
                detalhamento = artigo.find('detalhamento-do-artigo')
                descricao = titulo + '. ' + detalhamento.get('titulo-do-periodico-ou-revista',
                                                             '') + '. ' + dados_basicos.get('ano-do-artigo')
                if detalhamento.get('issn'):
                    issn = validate_issn_code(detalhamento.get('issn'))
                    qualis = Periodico.objects.filter(Q(issn=issn) | Q(eissn=issn)). \
                        values_list('qualis', flat=True).first()
                    if not qualis:
                        qualis = 'ND'
                    if qualis == 'ND':
                        qualis = 'Não Determiando'
                    descricao += '. (Qualis %s)' % qualis
                else:
                    descricao += '. (Sem ISSN)'
                    totais['sem_issn'] += 1

                doi = None
                if dados_basicos.get('doi'):
                    doi = '<a href="http://doi.org/%s">%s</a>' % (dados_basicos.get('doi'), descricao)

                context['artigos_publicados'].append(
                    {'ano': dados_basicos.get('ano-do-artigo'), 'descricao': descricao, 'doi': doi}),
                totais['artigos'] += 1

        if totais.get('sem_issn', 0) > 0:
            context['dicas'].append('Existem %d artigos que não tem o ISSN do periódico. '
                                    'Sem o ISSN, o Sucupira não consegue identificar o Qualis da sua publicação.' %
                                    totais['sem_issn'])

        for capitulo in capitulos_publicados:
            dados_basicos = capitulo.find('dados-basicos-do-capitulo')
            if dados_basicos.get('ano') in last_years:
                titulos.append(dados_basicos.get('titulo-do-capitulo-do-livro'))
                context['capitulos_publicados'].append(
                    normalize_enconding(dados_basicos.get('titulo-do-capitulo-do-livro')) + '. ' + dados_basicos.get(
                        'ano'))
                totais['capitulos'] += 1

        for evento in eventos:
            dados_basicos = evento.find('dados-basicos-do-trabalho')
            if dados_basicos.get('titulo-do-trabalho') and dados_basicos.get('ano-do-trabalho') in last_years:
                palavras_chaves = evento.find('palavras-chave')
                if palavras_chaves and palavras_chaves.attrs:
                    palavras_chaves = list(palavras_chaves.attrs.values())
                    context['palavras-chave'] += palavras_chaves

                titulos.append(dados_basicos.get('titulo-do-trabalho'))
                context['eventos'].append(
                    dados_basicos.get('titulo-do-trabalho') + '. ' + dados_basicos.get('ano-do-trabalho'))
                totais['eventos'] += 1

        if producao_tecnica:
            producoes = producao_tecnica.find_all(re.compile('^dados-basicos'))
            palavras_chaves_tag = producao_tecnica.find_all('palavras-chave')
            for palavra_chave in palavras_chaves_tag:
                if palavra_chave and palavra_chave.attrs:
                    palavras_chaves = list(palavra_chave.attrs.values())
                    context['palavras-chave'] += palavras_chaves

            for producao in producoes:
                if producao.get('ano') in last_years:
                    titulo = producao.get('titulo-do-trabalho-tecnico') \
                        if producao.get('titulo-do-trabalho-tecnico') else producao.get('titulo')
                    if titulo:
                        context['producao_tecnica'].append(titulo + '. ' + producao.get('ano'))
                        titulo = titulo.lower()
                        titulo = titulo.replace('parecer', '').replace('avaliador', '').replace('avaliação', ''). \
                            replace('revista', '').replace('artigo', '').replace('científico', '').replace('para', ' ')
                        titulos.append(titulo)

                    totais['tecnicas'] += 1

        if download_csv:
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="producoes_%s.csv"' % id_cnpq
            writer = csv.writer(response, delimiter=';')
            header = ['Tipo', 'Título']
            writer.writerow(header)
            for item in context['artigos_publicados']:
                writer.writerow(['Artigo', item['descricao']])
            for item in context['capitulos_publicados']:
                writer.writerow(['Capítulo de Livro', item])
            for item in context['eventos']:
                writer.writerow(['Evento', item])
            for item in context['producao_tecnica']:
                writer.writerow(['Produção Técnica', item])
            return response

        # Ordena os artigos por ano
        artigos_ordered_by_ano = sorted(context['artigos_publicados'], key=lambda artigo: artigo['ano'])
        context['artigos_publicados'] = artigos_ordered_by_ano

        # Nuvem
        exclude_file = open(os.path.join(settings.BASE_DIR, 'docs', 'exclude.txt'), 'r')
        stopwords = exclude_file.read().lower()
        exclude_file.close()
        stopwords = [exc.strip().lower() for exc in stopwords.split(',')] if stopwords else []

        keywords = context['palavras-chave']
        words = '.'.join(titulos)

        context['nuvem'] = build_wordcloud(words, keywords, stopwords)

        context['processado'] = True

    context['form'] = ImportacaoAnonimaForm()
    if request.POST:
        form = ImportacaoAnonimaForm(request.POST, request.FILES)
        context['form'] = form

        if form.is_valid():
            arquivo = form.cleaned_data.get('xml')
            if arquivo.content_type == 'application/zip':
                file = ZipFile(arquivo.file, 'r')  # unzip
                try:
                    xml = file.open('curriculo.xml')  # open xml
                    processar_xml(xml)
                except KeyError:
                    messages.error(request, 'Arquivo ZIP incompatível. '
                                            'O arquivo XML comprimido deve conter o nome curriculo.xml')
                except Exception as e:
                    messages.error(request, e.__str__)

            elif arquivo.content_type == 'text/xml':
                processar_xml(arquivo.file)

            else:
                messages.error(request, 'O arquivo enviado não é válido, por favor envie um arquivo zip ou xml.')
        else:
            messages.error(request, 'Nenhum arquivo foi enviado para análise')

    elif id_lattes_params:
        path = os.path.join(settings.MEDIA_ROOT, 'uploads', 'lattes')
        file_path = os.path.join(path, id_lattes_params + '.xml')
        if os.path.exists(file_path):
            curriculo = open(file_path, 'r')
            if request.GET.get('download') == 'csv':
                return processar_xml(curriculo.read(), gravar_xml=False, validar_proxy=False, download_csv=True)
            else:
                processar_xml(curriculo.read(), gravar_xml=False, validar_proxy=False)

            curriculo.close()
        else:
            messages.error(request, 'Este currículo ainda não existe em nossa base.')

    return render(request, 'lattes-resumo.html', context)


@login_required
def convite_alunos(request, id_resumo):
    resumo = ResumoAnual.objects.get(id=id_resumo)
    count = 0

    for matricula in Matricula.objects.filter(status=STATUS_ATIVO):
        try:
            relatorio = RelatorioAnual.objects.get(ano=resumo.ano, pesquisador=matricula.pesquisador)
        except RelatorioAnual.DoesNotExist:
            relatorio = RelatorioAnual(ano=resumo.ano, pesquisador=matricula.pesquisador)
            relatorio.save()

        if relatorio.status not in (relatorio.VALIDADO, relatorio.AVALIADO):
            relatorio.send_edit_invite()
            count += 1

    messages.info(request, f'{count} convites enviados')
    return HttpResponseRedirect('/admin/nucleo/resumoanual')


def avaliacao_anual(request, hash):
    """
    Renderiza uma página com a informação do relatório anual, opções de ação conforme os hashs passados na url e
    uma lista de produções do aluno.
    """
    apr = request.GET.get('apr', '')
    context, kwargs = {}, {}

    try:
        if apr == '1':
            kwargs = {'hash_apr': hash}
        else:
            kwargs = {'hash_auth': hash}

        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)

        # Verifica se o aluno é de Doutorado
        matricula = Matricula.objects.filter(pesquisador=relatorio_anual.pesquisador).order_by('-ingresso').first()
        doutorado = matricula.curso.nivel[0] == 'D'

        # Acao contém a lista de botões com as ações possíveis para o usuário
        # Se o indicador tag for True ou not null indica que a ação já foi realizada pelo usuário
        Acao = namedtuple('Acao', ['endereco', 'nome', 'tag'], defaults=[False])

        if apr == '1':
            acoes = [
                Acao(reverse('avaliacao_resumo', args=(hash,)) + f'?apr={apr}', 'Resumo', relatorio_anual.resumo_ok),
                Acao(reverse('avaliacao_cadastro', args=(hash,)) + f'?apr={apr}', 'Dados Cadastrais'),
            ]
            if relatorio_anual.sandwich_orientador:
                acoes.append(Acao(reverse('avaliacao_sandwich', args=(hash,)) + f'?apr={apr}', 'Doutorado Sandwich'))

            acoes.append(Acao(reverse('avaliacao_aprovacao', args=(hash,)), 'Avaliar'))

        else:
            acoes = [
                Acao(reverse('importacao_lattes', args=(hash,)), 'Importação Lattes',
                     relatorio_anual.pesquisador.id_cnpq),
                Acao(reverse('avaliacao_cadastro', args=(hash,)), 'Dados Cadastrais',
                     relatorio_anual.pesquisador.status != 'E'),
                Acao(reverse('avaliacao_resumo', args=(hash,)), 'Resumo da Produção',
                     relatorio_anual.resumo_ok),
            ]

            if doutorado:
                acoes.append(Acao(reverse('avaliacao_sandwich', args=(hash,)), 'Doutorado Sandwich'))

            if relatorio_anual.status not in (RelatorioAnual.VALIDADO, RelatorioAnual.AVALIADO):
                acoes.extend([
                    Acao(reverse('selecionar_nova_producao', args=(hash,)), 'Nova Produção'),
                    Acao(reverse('avaliacao_validacao', args=(hash,)), 'Solicitar Aprovação',
                         relatorio_anual.status == RelatorioAnual.VALIDADO)
                ])

        # Lista de produções do pesquisador no ano do relatório
        qs = Producao.objects.filter(pesquisador=relatorio_anual.pesquisador, ano=relatorio_anual.ano).order_by('pk')

        pagina = request.GET.get(PAGE_VAR, 1)
        paginator = Paginator(qs, 10)

        try:
            producoes = paginator.page(pagina)
        except PageNotAnInteger:
            producoes = paginator.page(1)
        except InvalidPage:
            producoes = paginator.page(paginator.num_pages)

        context.update({
            'title': relatorio_anual.alt_title(), 'hash': hash, 'apr': apr, 'acoes': acoes,
            'page_obj': producoes, 'page_range': paginator.get_elided_page_range()
        })

        response = render(request, 'avaliacao_anual.html', context)
    except Http404:
        response = handler404(request, template='avaliacao_anual_404.html')

    return response


def avaliacao_cadastro(request, hash):
    """
    Renderiza uma página com a informação do relatório anual, opções de ação conforme os hashs passados na url e
    uma lista de produções do aluno.
    """
    apr = request.GET.get('apr', '')
    if apr == '1':
        kwargs = {'hash_apr': hash}
    else:
        kwargs = {'hash_auth': hash}

    readonly = apr == '1'
    try:
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        pesquisador = Pesquisador.objects.get(id=relatorio_anual.pesquisador.id)
        if request.method == 'GET':
            form = RelatorioCadastroForm(instance=pesquisador, disabled=readonly)
        else:
            if readonly:
                return redirect(relatorio_anual.get_approval_url())
            else:
                form = RelatorioCadastroForm(data=request.POST, instance=pesquisador)

                if form.is_valid():
                    form.save()
                    messages.success(request, 'Cadastro salvo com sucesso')
                    return redirect(relatorio_anual.get_absolute_url())

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def avaliacao_resumo(request, hash):
    """Renderiza o form de edição de RelatorioAnual. O form será readonly para hash de aprovação."""
    apr = request.GET.get('apr', '')

    if apr == '1':
        kwargs = {'hash_apr': hash}
    else:
        kwargs = {'hash_auth': hash}

    readonly = apr == '1'

    try:
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)

        if request.method == 'GET':
            form = RelatorioAnualForm(instance=relatorio_anual, disabled=readonly)
        else:
            if readonly:
                return redirect(relatorio_anual.get_approval_url())
            else:
                form = RelatorioAnualForm(data=request.POST, instance=relatorio_anual)

                if form.is_valid():
                    instance = form.save()
                    total = instance.desenvolvimento_total
                    # Verifica se desenvolvimento tem entre 1000 e 2000 palavras
                    if not 1000 <= total <= 2000:
                        messages.warning(
                            request, f'Desenvolvimento da Pesquisa deve ter entre 1000 e 2000 palavras. '
                                     f'Total: {total} palavras.'
                        )

                    messages.success(request, f'{RelatorioAnual._meta.verbose_name} salvo com sucesso')

                    return redirect(instance.get_absolute_url())

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def avaliacao_sandwich(request, hash):
    """Renderiza o form de edição de RelatorioAnual. O form será readonly para hash de aprovação."""
    apr = request.GET.get('apr', '')

    if apr == '1':
        kwargs = {'hash_apr': hash}
    else:
        kwargs = {'hash_auth': hash}

    visao_orientador = apr == '1'

    try:
        record = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        resumo = get_object_or_404(ResumoAnual, ano=record.ano)
        periodo_fechado = resumo.status == ResumoAnual.FECHADO
        if periodo_fechado:
            messages.info(request, 'Período de edição encerrado para {resumo.ano}')

        if request.method == 'GET':
            form = RelatorioSandwichForm(instance=record, disabled=visao_orientador or periodo_fechado)
        else:
            if visao_orientador:
                return redirect(record.get_approval_url())
            else:
                form = RelatorioSandwichForm(data=request.POST, instance=record)

                if form.is_valid():
                    instance = form.save()
                    # Verifica se desenvolvimento tem entre 1000 e 2000 palavras
                    if not instance.sandwich_descricao:
                        messages.warning(
                            request, 'A descrição do desenvolvimento do Estágio Sandwich deve ser preenchido'
                        )

                    messages.success(request, 'Dados salvos com sucesso')

                    return redirect(instance.get_absolute_url())

        return render(request, 'base_form.html', {'form': form, 'title': record.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def avaliacao_validacao(request, hash):
    """
    Realiza a validação do relatório, envia email para o orientador
    e dá mensagem "Obrigado por enviar o seu relatório de produção".
    """
    record = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_auth=hash)
    if record.desenvolvimento_total < 1000:
        messages.error(request, 'Texto do desenvolvimento não preenchido completamente')
    else:
        record.status = RelatorioAnual.VALIDADO
        record.save()
        messages.success(request, 'Obrigado por enviar o seu relatório de produção')
    return redirect(record.get_absolute_url())


def avaliacao_aprovacao(request, hash):
    """Mostra o formulário que permite que o orientador valide o relatório de um aluno"""
    try:
        # Trazer o registro do relatório
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_apr=hash)
        if request.method == 'GET':
            form = RelatorioAprovacaoForm(instance=relatorio_anual)
        else:
            form = RelatorioAprovacaoForm(data=request.POST, instance=relatorio_anual)
            if form.is_valid():
                instance = form.save(commit=False)
                instance.aprovado = '_aprovar' in request.POST
                instance.save()

                messages.success(request, f'{RelatorioAnual._meta.verbose_name} salvo com sucesso')
                return redirect(instance.get_approval_url())

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


@transaction.atomic
def editar_producao(request, hash, hash_producao):
    try:
        disabled = request.GET.get('apr', '') == '1'

        if disabled:
            kwargs = {'hash_apr': hash}
        else:
            kwargs = {'hash_auth': hash}
        # Testar se o pesquisador tem permissão de editar essa produção
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        producao = get_object_or_404(Producao.objects.select_related('pesquisador', 'tipo'), id=hash_producao)
        # Sem tratamento para form_class None nesta versão.
        form_class = get_producao_form(producao.tipo)

        if request.method == 'GET':
            form = form_class(instance=producao, disabled=disabled)
            formsets, inlines = form.get_formsets(request, producao)
        else:
            form = form_class(request.POST, request.FILES, instance=producao)

            form_validated = form.is_valid()

            if form_validated:
                instance = form.save(commit=False)
            else:
                instance = form.instance

            formsets, inlines = form.get_formsets(request, instance)

            if all_valid(formsets) and form_validated:
                instance.save()

                for formset in formsets:
                    formset.save()

                messages.success(request, f'{instance._meta.verbose_name} salva com sucesso')

                return redirect(relatorio_anual.get_absolute_url())

        errors = helpers.AdminErrorList(form, formsets)

        inline_formsets = form.get_formsets_with_inlines(request, formsets, inlines)

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'inlines': inline_formsets,
                       'errors': errors})

    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def selecionar_nova_producao(request, hash_auth):
    """
    View que renderiza uma página para selecionar o tipo de produção e redirecionar para a view de cadastro de uma
    nova produção apontando para o formulário correto
    """
    try:
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_auth=hash_auth)

        if request.method == 'GET':
            form = SelecionaProducaoForm()
        else:
            form = SelecionaProducaoForm(data=request.POST)

            if form.is_valid():
                tipo = form.cleaned_data['tipo']

                if form.cleaned_data['doi']:
                    querystring = '?' + urlencode(form.cleaned_data['doi'].items())
                else:
                    querystring = ''

                return redirect(reverse('nova_producao', args=(hash_auth, tipo.pk)) + querystring)

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'add': True, 'errors': form.errors})

    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


@transaction.atomic
def nova_producao(request, hash_auth, tipo_id):
    try:
        # Testar se o pesquisador tem permissão de editar essa produção
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_auth=hash_auth)
        tipo = get_object_or_404(TipoProducao, pk=tipo_id)

        form_class = get_producao_form(tipo)

        if form_class is None:
            messages.error(request, f'O formulário para o tipo de produção "{tipo}" não foi definido')
            return redirect('selecionar_nova_producao', hash_auth)

        if request.method == 'GET':
            initial = dict(request.GET.items())
            form = form_class(initial=initial)
            form.instance.pesquisador = relatorio_anual.pesquisador
            formsets, inlines = form.get_formsets(request, form.instance)
        else:
            form = form_class(request.POST, request.FILES)

            form_validated = form.is_valid()

            if form_validated:
                instance = form.save(commit=False)
            else:
                instance = form.instance

            formsets, inlines = form.get_formsets(request, instance)

            if all_valid(formsets) and form_validated:
                instance.pesquisador = relatorio_anual.pesquisador
                instance.tipo = tipo
                instance.save()

                for formset in formsets:
                    formset.save()

                messages.success(request, f'{instance._meta.verbose_name} salva com sucesso')

                return redirect(relatorio_anual.get_absolute_url())

        errors = helpers.AdminErrorList(form, formsets)
        inline_formsets = form.get_formsets_with_inlines(request, formsets, inlines)

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'inlines': inline_formsets, 'add': True,
                       'errors': errors})

    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')

#funcao que retorna a chave de determinado value em um dicionario
def find_key_by_value(nested_dict, target_value):
            for sub_dict in nested_dict.values():
                for key, value in sub_dict.items():
                    if isinstance(value, list):
                        if target_value in value:
                            return key
                    elif value == target_value:
                        return key
            return None

dict_livros_e_capitulos = {
    
    'dict_natureza': {
        "O": ["TEXTO_INTEGRAL", "LIVRO", "OBRA_UNICA"],
        "C": "COLECAO",
        "L": "COLETANEA",
        "D": "DICIONARIO",
        "E": "ENCICLOPEDIA",
        None: "NAO_INFORMADO",
    },

    'dict_meio': {
        "I": "IMPRESSO",
        "M": "MAGNETICA",
        "D": ["DIGITAL", "MEIO_DIGITAL", "CD", "DVD", "BLURAY", "USB"],
        "F": "FILME",
        "H": "HIPERTEXTO",
        "O": "OUTRO",
    },

    'dict_tipo': {
        "C": "CAPITULO",
        "V": "VERBETE",
        "A": "APRESENTACAO",
        "I": "INTRODUCAO",
        "P": "PREFACIO",
        "O": "POSFACIO",
        "L": ["LIVRO_ORGANIZADO_OU_EDICAO", "LIVRO_PUBLICADO"],
        "T": "COMPLETO",
        "R": "RESUMO",
        "X": "RESUMOX",
    }
}