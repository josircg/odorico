import csv
import json
import os
import re
import threading
import traceback
from collections import Counter, namedtuple
from datetime import date, datetime
from zipfile import BadZipFile, ZipFile

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.admin.views.main import PAGE_VAR
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import InvalidPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q
from django.db.transaction import commit, set_autocommit
from django.forms import all_valid, formset_factory
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView
from weasyprint import HTML

from chupalattes import get_lista_paises, get_parse_issn
from nucleo import clean_doi_url
from nucleo.apps import (data_por_extenso, generate_hash, generate_qrcode_base64, gerar_tabela_disciplinas,
                         get_doi_metadata, log_object, obtem_dt_cnpq, parse_titulo, validate_24hash, validate_issn_code)
from nucleo.forms import (BuscaOrientadorForm, BuscaProfessorAlunoForm, EditAlunoForm, EditProfessorForm,
                          HomologacaoDefesaForm, IdentificarMembroExternoForm, ImportForm, ImportacaoAnonimaForm,
                          InscricaoDisciplinaForm, MatriculaEventoPesquisadorForm, RelatorioAnualForm,
                          RelatorioAprovacaoForm, RelatorioCadastroForm, RelatorioSandwichForm, SelecionaProducaoForm,
                          SolicitaOrientadorForm, SolicitacaoProrrogacaoForm, SolicitacaoTrancamentoForm,
                          SolicitacaoReativacaoForm,
                          TurmaAvaliacaoItemForm, VincularMembroExternoForm, get_producao_form)
from nucleo.lattes import InvalidXMLException, import_xml, xml_limpo, processar_logs_view
from editais.models import Edital
from nucleo.models import (Aluno, AtaReuniao, Curso, Disciplina, Documento, Inscricao, Matricula, MatriculaEvento,
                           MatriculaEventoPesquisador, Orientacao, Periodo, Pesquisador, PesquisadorInstituicao,
                           PesquisadorPrograma, PesquisadorProjeto, Producao, Professor, ProfessorLinha, Programa,
                           ProjetoPesquisa, RelatorioAnual, ResumoAnual, STATUS_ATIVO, TipoDocumento, TipoNotificacao,
                           TipoOcorrencia, TipoProducao, Turma)
from nucleo.relatorios import view_resumo_qualis
from qualis.models import Assunto, Periodico, Schema
from utils.email import sendmail
from utils.models import TipoProcessamento
from utils.stdlib import get_display_str, is_empty
from utils.text import build_wordcloud


def home(request):
    if settings.DEBUG:
        url = '/periodicos'
    else:
        # força que outros ambientes vejam os periódicos apenas do site raíz
        url = 'https://odorico.ibict.br/periodicos'

    editais = []
    for edital in Edital.objects.filter(status=Edital.Status.ATIVO):
        editais.append({'descricao': edital.descricao, 'id': edital.id })

    return render(request, 'home.html',
                  {'version': settings.VERSION, 'periodicos_url': url, 'editais_abertos': editais })


def render_mensagem(request, titulo: str, mensagem: str):
    return render(request, 'base_mensagem.html', context={'titulo': titulo, 'texto': mensagem})


def handler404(request, *args, **argv):
    template = argv.get('template', '404.html')
    response = render(request, template)
    response.status_code = 404
    return response


def handler500(request, *args, **argv):
    response = render(request, '500.html')
    response.status_code = 500
    return response


def file_upload(request, f):
    save_path = os.path.join(settings.MEDIA_ROOT, 'uploads', f.name)  # cria um path
    path = default_storage.save(save_path, request.FILES['arquivo_zip'])  # salva o arquivo no path
    return default_storage.path(path)  # retorna o path


def importacao_lattes(request, hash_auth=None):
    try:

        if hash_auth:
            relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'),
                                                hash_auth=hash_auth)
            id_cnpq = relatorio_anual.pesquisador.id_cnpq
            link_lattes = f'https://buscatextual.cnpq.br/buscatextual/download.do?metodo=apresentar&idcnpq={id_cnpq}'
        else:
            relatorio_anual = None
            link_lattes = None

        pesquisador = None
        if relatorio_anual:
            pesquisador = relatorio_anual.pesquisador

        if request.method == 'POST':
            form = ImportForm(request.POST, request.FILES, has_hash=relatorio_anual is not None)

            if form.is_valid():
                arquivo_zip = request.FILES.get('arquivo_zip')
                arquivo_xml = request.FILES.get('arquivo_xml')
                pathname = os.path.join(settings.BASE_DIR, 'cache')
                try:
                    resultado = None

                    if arquivo_zip:
                        zipfile = ZipFile(arquivo_zip.file, 'r')
                        zipfile.extractall(pathname)
                        xml_name = zipfile.namelist()[0]
                        xml = xml_limpo(pathname + '/' + xml_name)
                        resultado = import_xml(xml, pesquisador, True)
                    elif arquivo_xml:
                        cache_filename = os.path.join(pathname, f'{pesquisador}.xml')
                        with open(cache_filename, 'wb+') as destination:
                            # Percorremos o ficheiro enviado em pedaços (chunks)
                            for chunk in arquivo_xml.chunks():
                                destination.write(chunk)
                        xml = xml_limpo(cache_filename)
                        resultado = import_xml(xml, pesquisador, True)
                    else:
                        messages.error(request, 'Nenhum arquivo enviado. Tente utilizar outro navegador.')

                    if resultado is not None:
                        processar_logs_view(request, resultado.get('logs', []))
                except BadZipFile:
                    messages.error(request, 'Arquivo ZIP inválido ou danificado')

                except Exception as e:
                    if settings.DEBUG:
                        raise
                    else:
                        message = ''.join(traceback.TracebackException.from_exception(e).format())
                        message = message.replace('\n', '\\n')
                        message = arquivo_xml.name + '\\n' + message
                        sendmail('Erro Importação Lattes', [settings.REPLY_TO_EMAIL], message=message)
                        messages.error(request, 'Houve um erro durante a importação. Já estamos averiguando o problema')

                if relatorio_anual is not None:
                    to = relatorio_anual.get_absolute_url()
                else:
                    to = 'importacao_lattes'

                return redirect(to)
        else:
            form = ImportForm(has_hash=relatorio_anual is not None)

        return render(request, 'import_lattes.html', {'form': form, 'aluno': hash_auth, 'link_lattes': link_lattes})
    except Http404:
        if hash_auth is not None:
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


def local_defesa(matricula):
    ocorrencia = MatriculaEvento.objects.filter(matricula=matricula,
                                                tipo_id__in=(2, 3, 4, 5),
                                                status=MatriculaEvento.Status.APROVACAO_CD).last()
    if ocorrencia:
        return ocorrencia.local
    else:
        return 'IBICT - 4º andar - Sala de Reuniões'


@xframe_options_exempt
def agenda_defesas(request):
    context = {}
    today = date.today()
    dataset = Matricula.objects.filter(dtquali__gte=today).select_related(
        'pesquisador', 'curso__programa__instituicao').only(
        'pesquisador__nome', 'pesquisador__id', 'curso__descricao', 'id', 'dtquali', 'titulo',
        'curso__programa__instituicao__nome'
    ).order_by('dtquali')
    result = []
    for matricula in dataset:
        nome_orientador = matricula.orientador_atual
        result.append({
            'titulo': matricula.titulo,
            'aluno': matricula.pesquisador.nome,
            'tipo': 'Qualificação de %s' % matricula.curso.descricao,
            'orientador': nome_orientador,
            'data': matricula.dtquali,
            'local': local_defesa(matricula),
        })

    defesa = Matricula.objects.filter(dtdefesa__gte=today).select_related(
        'pesquisador', 'curso__programa__instituicao').only(
        'pesquisador__nome', 'pesquisador__id', 'curso__descricao', 'id', 'dtquali', 'titulo',
        'curso__programa__instituicao__nome'
    ).order_by('dtdefesa')
    for matricula in defesa:
        nome_orientador = matricula.orientador_atual
        result.append({
            'titulo': matricula.titulo,
            'aluno': matricula.pesquisador.nome,
            'tipo': 'Defesa de %s' % matricula.curso.descricao,
            'orientador': nome_orientador,
            'data': matricula.dtdefesa,
            'local': local_defesa(matricula),
        })

    result = sorted(result, key=lambda i: i['data'])

    context['valores'] = result
    return render(request, 'agenda_defesas.html', {'result': context})


@xframe_options_exempt
def orientacoes(request):
    context = {}
    programa = request.GET.get('programa', '0')
    kwargs = {'status': STATUS_ATIVO}

    if request.user.is_authenticated:
        pesquisador = Pesquisador.objects.filter(user=request.user).only('id').first()
        if pesquisador:
            kwargs['orientador__pk'] = pesquisador.id
    else:
        id = request.GET.get('id', '0')
        hash_auth = request.GET.get('hash_auth')
        # Redireciona para a página que pede o e-mail do orientador para voltar no relatório com id e hash_auth em caso
        # de sucesso
        if not id or not hash_auth:
            return redirect(f'{reverse("busca_orientador")}?programa={programa}')
        # Renderiza página que informa que o registro é inválido.
        if generate_hash(id) != hash_auth:
            return render_mensagem(request, 'Registro inválido',
                                   'Entre em contato com a secretaria para informar o erro')

        kwargs['orientador__pk'] = id

    dataset = Orientacao.objects.filter(**kwargs).select_related(
        'aluno', 'orientador', 'matricula', 'matricula__curso').only(
        'orientador__nome', 'aluno__nome',
        'matricula__curso__descricao', 'coorientacao',
        'matricula__id', 'matricula__dtprevista').order_by(
        'orientador__nome')
    result = []
    ult_orientador = ''
    for reg in dataset:

        if ult_orientador != reg.orientador.nome:
            ult_orientador = reg.orientador.nome
            current = reg.orientador.nome
        else:
            current = ''

        curso = reg.matricula.curso.descricao
        if reg.coorientacao:
            curso += ' (Coorientação)'

        link = reverse('historico') + f'?matricula={reg.matricula.hash}'

        result.append({
            'orientador': current,
            'aluno': reg.aluno.nome,
            'tipo': curso,
            'link': link,
            'dtmatricula': reg.matricula.dtmatricula,
            'dtquali': reg.matricula.dtquali or '-',
            'dtprevista': reg.matricula.dtprevista
        })

    context['dataset'] = result
    if request.user.is_authenticated:
        return render(request, 'orientacoes_detalhe.html', {'result': context})
    else:
        return render(request, 'orientacoes.html', {'result': context})


@xframe_options_exempt
@csrf_exempt
def defesas_realizadas(request):
    context = {}
    result = []
    ano = int(request.GET.get('ano')) if request.GET.get('ano') else 0
    if ano:
        defesa = Matricula.objects.filter(dtdefesa__year=ano)
        mes = int(request.GET.get('mes')) if request.GET.get('mes') else 0
        if mes:
            defesa = defesa.filter(dtdefesa__month=mes)

        dataset = defesa.select_related('pesquisador', 'curso').only(
            'pesquisador__nome', 'curso__descricao', 'dtdefesa', 'titulo', 'pesquisador__id', 'id')

        for reg in dataset:
            result.append({
                'Título': reg.titulo or 'Não informado',
                'Aluno': reg.pesquisador.nome,
                'Tipo': 'Defesa de %s' % reg.curso.descricao,
                'Orientador(a)': reg.orientador_atual,
                'Data': reg.dtdefesa,
            })

        result = sorted(result, key=lambda i: i['Data'])
        context['valores'] = result
    else:
        context['valores'] = result

    return render(request, 'defesas_realizadas.html', {'result': context})


def producao_projeto(request, id_cnpq):
    context = {}
    result = []
    producoes = []
    context['total'] = 0

    pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq)
    if pesquisador:
        producoes = Producao.objects.filter(pesquisador=pesquisador.get(),
                                            ano__gte=2021).order_by('ano', 'tipo')
        producoes = producoes.values_list('titulo', 'projeto__nome',
                                          'id', 'sem_projeto', 'tipo__descricao', 'ano')
        context['total'] = producoes.count()
        context['titulo'] = 'Produção x Projeto - %s' % pesquisador.get()

    for producao in producoes:
        titulo = producao[0]
        if len(titulo) > 300:
            titulo = producao[0][:300] + '...'
        titulo += f'({producao[4]}) ({producao[5]})'

        if producao[3]:
            result.append({
                'titulo': titulo,
                'projeto': 'Fora do Programa',
                'id': producao[2]
            })
        else:
            result.append({
                'titulo': titulo,
                'projeto': producao[1],
                'id': producao[2]
            })

    context['values'] = result
    context['labels'] = \
        [{'value': 'Título'},
         {'value': 'Projeto', 'style': 'width:150px;'}, ]

    return render(request, 'producao_projeto.html', {'result': context})


def producao_edit(request, id):
    context = {}
    producao = Producao.objects.get(id=id)
    projetos_pesquisador = list(PesquisadorProjeto.objects.filter(
        pesquisador=producao.pesquisador,
        projeto__status='A'))

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
                                            ano__gte=2020,
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
        issn = None
        if producao.doi:
            producao.doi = clean_doi_url(producao.doi)
            issn = get_doi_metadata(producao.doi)
            producao.doi_validado = not is_empty(issn)

        if not producao.periodico:
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
                messages.warning(request, 'ISSN não encontrado. Selecione o periódico manualmente.')

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
    ano = date.today().year
    quadrienio = (ano, ano - 1, ano - 2, ano - 3)
    for pesq in queryset:
        producoes = Producao.objects.filter(pesquisador__nome__exact=pesq, ano__in=quadrienio,
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
    context['titulo'] = '%s (%s a %s)' % (programa[0].descricao, quadrienio[0], quadrienio[3])
    context['api_key'] = settings.GEO_API

    return render(request, 'mapa_paises.html', {'result': context})


def programa_csv_producao(request, programa_id):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="producao.csv"'

    # Monta a lista de todos os campos da produção
    field_names = [f.name for f in Producao._meta.get_fields()]
    for field in ['titulo_original', 'conta_sucupira', 'producaoautor', 'id', 'pesquisador', 'tipo']:
        field_names.remove(field)
    to_be_transformed = []
    for field in Producao._meta.fields:
        if field.choices is not None:
            to_be_transformed.append(field.name)

    related = ['pesquisador__nome', 'tipo__descricao',
               'periodico__nome', 'area_impacto__descricao']
    field_names.insert(0, related[0])
    field_names.insert(1, related[1])
    field_names += related[2:]

    # obtem os pesquisadores do programa
    queryset = Producao.objects.filter(
        pesquisador__pesquisadorprograma__id=programa_id
    ).select_related(*related).order_by('pesquisador__nome', 'tipo__descricao').values(*field_names)

    csv_intl = csv.writer(response, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_intl.writerow(field_names)
    tot_registros = 0
    for producao in queryset:
        record = dict(producao)
        for fieldname in to_be_transformed:
            record[fieldname] = get_display_str(record[fieldname], Producao, fieldname)
        fields = list(record.values())
        csv_intl.writerow(fields)
        tot_registros += 1
    messages.info(request, f'{tot_registros} exportados')
    return response


def qualis_resumo(request, programa_ids):
    programa_ids_clean = list(filter(lambda id: not id == '-' and not id == '', programa_ids.split('-')))

    if programa_ids_clean:
        programas = Programa.objects.filter(pk__in=programa_ids_clean)
        return view_resumo_qualis(None, request, programas)

    messages.error(request, 'A URL informada espera um intervalo de números válido de ID´s. Ex.: 1-11-9')
    return redirect(reverse('admin:index'))


def counter_areas(soup):
    areas_conhecimento = soup.find_all(re.compile('^(?i)area-do-conhecimento'))
    contador_areas = Counter()
    for area_conhecimento in areas_conhecimento:
        dado = []
        garea = area_conhecimento.get('nome-grande-area-do-conhecimento', '').replace('_', ' ')
        dado.append(garea)
        if area_conhecimento.get('nome-da-area-do-conhecimento'):
            dado.append(area_conhecimento.get('nome-da-area-do-conhecimento'))
        if area_conhecimento.get('nome-da-sub-area-do-conhecimento'):
            dado.append(area_conhecimento.get('nome-da-sub-area-do-conhecimento'))
        area = ','.join(dado)
        contador_areas[area] += 1
    # Ordena pela area com maior frequência
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

        grande_area_schema = Schema.objects.get(sigla='CNPQ0').id
        totais = Counter()
        last_years = [str(datetime.now().year - i) for i in range(6)]
        titulos = []
        try:
            soup = BeautifulSoup(arquivo, 'lxml')
            informacoes_curriculo = soup.find('curriculo-vitae')
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
                    data_proxy = datetime.strptime(
                        '%s' % informacoes_curriculo_proxy.get('data-atualizacao'), '%d%m%Y')
                    data_xml = datetime.strptime('%s' % informacoes_curriculo.get('data-atualizacao'),
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
            if len(areas_splited) > 0:
                # Normaliza o texto da grande área
                grande_area = Assunto.objects.filter(schema_id=grande_area_schema,
                                                     descricao__icontains=areas_splited[0]).values_list(
                    'descricao',
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
                        qualis = 'Não Determinado'
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
            with open(file_path, 'r') as curriculo:
                if request.GET.get('download') == 'csv':
                    return processar_xml(curriculo.read(), gravar_xml=False, validar_proxy=False, download_csv=True)
                else:
                    processar_xml(curriculo.read(), gravar_xml=False, validar_proxy=False)

        else:
            messages.error(request, 'Este currículo ainda não existe em nossa base.')

    return render(request, 'lattes-resumo.html', context)


def convite_thread(resumo):
    count = 0
    proc = TipoProcessamento.objects.get(tipo=TipoProcessamento.Tipo.CONVITE_ALUNO)
    set_autocommit(False)
    try:
        for matricula in Matricula.objects.filter(status=STATUS_ATIVO).order_by('id'):
            try:
                relatorio = RelatorioAnual.objects.get(ano=resumo.ano, pesquisador=matricula.pesquisador)
            except RelatorioAnual.DoesNotExist:
                relatorio = RelatorioAnual(ano=resumo.ano, pesquisador=matricula.pesquisador)
                relatorio.save()

            if relatorio.status not in (relatorio.VALIDADO, relatorio.AVALIADO, relatorio.REGISTRADO):
                relatorio.send_invite('Convite para preenchimento do relatório anual', proc, thread=False)
                count += 1
            commit()

        set_autocommit(True)
        log_object(resumo, f'{count} convites enviados')
    except Exception as e:
        log_object(resumo, f'error: {e}')


@login_required
def convite_alunos(request, id_resumo):
    resumo = ResumoAnual.objects.get(id=id_resumo)
    log_object(resumo, 'Envio de Convites agendado')
    t = threading.Thread(target=convite_thread, args=[resumo], daemon=True)
    t.start()
    messages.info(request, 'Envio agendado')

    return HttpResponseRedirect('/admin/nucleo/resumoanual')


@login_required
def convite_individual(request, id_matricula):
    if not id_matricula:
        messages.error(request, 'Matricula não informada')
        return HttpResponseRedirect('/admin/nucleo/matricula/')

    redirect_url = '/admin/nucleo/matricula/%s/change/' % id_matricula
    resumo = ResumoAnual.objects.filter(status=STATUS_ATIVO).first()
    matricula = Matricula.objects.get(id=id_matricula)
    relatorio, found = RelatorioAnual.objects.get_or_create(ano=resumo.ano, pesquisador=matricula.pesquisador)
    if found:
        if relatorio.status in (RelatorioAnual.VALIDADO, RelatorioAnual.AVALIADO):
            messages.warning(request, 'O Relatório para o aluno já foi preenchido')
            return HttpResponseRedirect(redirect_url)
    else:
        relatorio.save()

    proc = TipoProcessamento.objects.get(tipo=TipoProcessamento.Tipo.CONVITE_ALUNO)
    relatorio.send_invite('Relatório Anual', proc)
    messages.info(request, 'Convite Enviado')
    return HttpResponseRedirect(redirect_url)


def periodo_fechado(ano):
    resumo = ResumoAnual.objects.get(ano=ano)
    return resumo.status == ResumoAnual.FECHADO


def avaliacao_anual(request, hash_auth):
    """
    Renderiza uma página com a informação do relatório anual, opções de ação conforme os hashs passados na url e
    uma lista de produções do aluno.
    """
    apr = request.GET.get('apr', '')
    context, kwargs = {}, {}

    try:
        if apr == '1':
            kwargs = {'hash_apr': hash_auth}
        else:
            kwargs = {'hash_auth': hash_auth}

        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        if periodo_fechado(relatorio_anual.ano):
            messages.warning(request, f'Período de edição encerrado para {relatorio_anual.ano}')

        # Verifica se o aluno é de Doutorado
        matricula = Matricula.objects.filter(pesquisador=relatorio_anual.pesquisador).order_by('-ingresso').first()
        if matricula:
            doutorado = matricula.curso.descricao[0] == 'D'
        else:
            doutorado = False
            sendmail('Discente sem matrícula ativa', [settings.REPLY_TO_EMAIL],
                     message=f'Aluno: {relatorio_anual.pesquisador.nome}')
        status_atual = None

        # Acao contém a lista de botões com as ações possíveis para o usuário
        # Se o indicador tag for True ou not null indica que a ação já foi realizada pelo usuário
        Acao = namedtuple('Acao', ['endereco', 'nome', 'tag'], defaults=[False])

        if apr == '1':
            acoes = [
                Acao(reverse('avaliacao_resumo', args=(hash_auth,)) + f'?apr={apr}', 'Resumo',
                     relatorio_anual.resumo_ok),
                Acao(reverse('avaliacao_cadastro', args=(hash_auth,)) + f'?apr={apr}', 'Dados Cadastrais', False),
            ]
            if relatorio_anual.sandwich_orientador:
                acoes.append(Acao(reverse('avaliacao_sandwich', args=(hash_auth,)) + f'?apr={apr}',
                                  'Doutorado Sandwich', relatorio_anual.sandwich_ok))

            acoes.append(Acao(reverse('avaliacao_aprovacao', args=(hash_auth,)), 'Avaliar', False))

        else:
            if relatorio_anual.pesquisador.dtupdate:
                year = relatorio_anual.pesquisador.dtupdate.year
            else:
                year = 0
            acoes = [
                Acao(reverse('importacao_lattes', args=(hash_auth,)), 'Importação Lattes',
                     year >= 2024),
                Acao(reverse('avaliacao_cadastro', args=(hash_auth,)), 'Dados Cadastrais',
                     relatorio_anual.status != RelatorioAnual.NAO_INICIADO),
                Acao(reverse('avaliacao_resumo', args=(hash_auth,)), 'Resumo da Produção',
                     relatorio_anual.resumo_ok),
            ]

            if doutorado:
                acoes.append(Acao(reverse('avaliacao_sandwich', args=(hash_auth,)), 'Doutorado Sandwiche', False))

            if periodo_fechado(relatorio_anual.ano):
                status_atual = f'Período de edição encerrado para {relatorio_anual.ano}'
            if relatorio_anual.status == RelatorioAnual.VALIDADO:
                status_atual = 'Relatório aguardando avaliação do orientador'
            elif relatorio_anual.status == RelatorioAnual.AVALIADO:
                status_atual = 'Relatório aprovado pelo orientador'
            else:
                acoes.extend([
                    Acao(reverse('selecionar_nova_producao', args=(hash_auth,)), 'Nova Produção', False),
                    Acao(reverse('avaliacao_validacao', args=(hash_auth,)), 'Solicitar Aprovação',
                         relatorio_anual.status == RelatorioAnual.VALIDADO)
                ])

        # Lista de produções do pesquisador no ano do relatório
        qs = Producao.objects.filter(pesquisador=relatorio_anual.pesquisador, ano=relatorio_anual.ano).order_by('pk')
        nao_validados = qs.exclude(validacao=Producao.Status.VALIDADO).count()
        if nao_validados > 0:
            status_atual = 'Clique em Editar em cada uma das produções abaixo'

        pagina = request.GET.get(PAGE_VAR, 1)
        paginator = Paginator(qs, 10)

        try:
            producoes = paginator.page(pagina)
        except PageNotAnInteger:
            producoes = paginator.page(1)
        except InvalidPage:
            producoes = paginator.page(paginator.num_pages)

        context.update({
            'title': relatorio_anual.alt_title(), 'hash': hash_auth, 'apr': apr, 'acoes': acoes,
            'status_atual': status_atual,
            'page_obj': producoes, 'page_range': paginator.get_elided_page_range()
        })

        response = render(request, 'avaliacao_anual.html', context)
    except Http404:
        response = handler404(request, template='avaliacao_anual_404.html')

    return response


def avaliacao_cadastro(request, hash_auth):
    """
    Renderiza uma página com a informação do relatório anual, opções de ação conforme os hashs passados na url e
    uma lista de produções do aluno.
    """
    apr = request.GET.get('apr', '')
    if apr == '1':
        kwargs = {'hash_apr': hash_auth}
    else:
        kwargs = {'hash_auth': hash_auth}

    try:
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        readonly = (apr == '1') or relatorio_anual.readonly() or periodo_fechado(relatorio_anual.ano)
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
                    relatorio_anual.status = RelatorioAnual.EM_EDICAO
                    relatorio_anual.save()
                    messages.success(request, 'Cadastro salvo com sucesso')
                    return redirect(relatorio_anual.get_absolute_url())

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def avaliacao_resumo(request, hash_auth):
    """Renderiza o form de edição de RelatorioAnual. O form será readonly para hash de aprovação."""
    apr = request.GET.get('apr', '')

    if apr == '1':
        kwargs = {'hash_apr': hash_auth}
    else:
        kwargs = {'hash_auth': hash_auth}

    try:
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        aprovacao = apr == '1'
        readonly = relatorio_anual.readonly() or periodo_fechado(relatorio_anual.ano)

        if request.method == 'GET':
            form = RelatorioAnualForm(instance=relatorio_anual, disabled=aprovacao or readonly)
        else:
            if aprovacao:
                return redirect(relatorio_anual.get_approval_url())
            else:
                form = RelatorioAnualForm(data=request.POST, instance=relatorio_anual,
                                          disabled=readonly)

                if form.is_valid():
                    instance = form.save()
                    total = instance.desenvolvimento_total
                    # Verifica se desenvolvimento tem entre 1000 e 2000 palavras
                    if not 1000 <= total <= 2000:
                        messages.warning(
                            request, f'Desenvolvimento da Pesquisa deve ter entre 1000 e 2000 palavras. '
                                     f'Total: {total} palavras.'
                        )

                    # Verifica se todas as produções estão validadas
                    tot_abertas = Producao.objects.filter(pesquisador=instance.pesquisador,
                                                          ano=relatorio_anual.ano,
                                                          validacao=Producao.Status.VALIDADO).count()
                    if tot_abertas > 0:
                        messages.warning(request, f'Existem {tot_abertas} produções não validadas')

                    messages.success(request, f'{RelatorioAnual._meta.verbose_name} salvo com sucesso')

                    return redirect(instance.get_absolute_url())

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def avaliacao_sandwich(request, hash_auth):
    """Renderiza o form de edição de RelatorioAnual. O form será readonly para hash de aprovação."""
    apr = request.GET.get('apr', '')

    if apr == '1':
        kwargs = {'hash_apr': hash_auth}
    else:
        kwargs = {'hash_auth': hash_auth}

    visao_orientador = apr == '1'

    try:
        record = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
        readonly = visao_orientador or periodo_fechado(record.ano) or record.readonly()

        if request.method == 'GET':
            form = RelatorioSandwichForm(instance=record, disabled=readonly)
        else:
            if visao_orientador:
                return redirect(record.get_approval_url())
            else:
                form = RelatorioSandwichForm(data=request.POST, instance=record)

                if form.is_valid():
                    instance = form.save()

                    if form.possui_campo_preenchido():
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


def avaliacao_validacao(request, hash_auth):
    """
    Realiza a validação do relatório, envia email para o orientador e dá mensagem
    "Obrigado por enviar o seu relatório de produção".
    Pede confirmação de envio de relatório para registros sem produção cadastrada.
    """
    record = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_auth=hash_auth)
    confirmacao = request.GET.get('confirmacao', 0)

    if not record.pesquisador.dtupdate:
        messages.error(request, f'A importação do arquivo Lattes deve ser realizada')
        return redirect(record.get_absolute_url())

    if record.pesquisador.dtupdate.year < 2024:
        messages.error(request,
                       f'A última atualização do Lattes foi feita antes de 2024. Atualize o seu currículo na plataforma Lattes e tente novamente.')
        return redirect(record.get_absolute_url())

    tot_abertas = Producao.objects.filter(pesquisador=record.pesquisador, ano=record.ano).exclude(
        validacao=Producao.Status.VALIDADO).count()
    if tot_abertas > 0:
        messages.error(request, f'Existem {tot_abertas} produções não validadas. '
                                f'Clique sob as produções importadas para finalizar o preenchimento')
        response = redirect(record.get_absolute_url())

    elif record.desenvolvimento_total < 1000:
        messages.error(request, 'Texto do desenvolvimento não preenchido completamente')
        response = redirect(record.get_absolute_url())

    elif not confirmacao and not Producao.objects.filter(pesquisador=record.pesquisador, ano=record.ano).count():
        response = render(
            request, 'confirma_envio_relatorio_producao.html', {'title': record.alt_title(), 'record': record}
        )
    else:
        record.status = RelatorioAnual.VALIDADO
        record.save()
        record.enviar_convite_aprovacao()
        log_object(record, 'Convite enviado para o Orientador')
        return render_mensagem(request,
                               'Obrigado por enviar o seu relatório de produção',
                               'Você receberá um novo email quando a/o orientador(a) o tiver aprovado')

    return response


def avaliacao_aprovacao(request, hash_auth):
    """Mostra o formulário que permite que o orientador valide o relatório de um aluno"""
    try:
        # Trazer o registro do relatório
        relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), hash_apr=hash_auth)
        if request.method == 'GET':
            form = RelatorioAprovacaoForm(instance=relatorio_anual)
        else:
            form = RelatorioAprovacaoForm(data=request.POST, instance=relatorio_anual)
            if form.is_valid():
                instance = form.save(commit=False)
                if '_aprovar' in request.POST:
                    instance.aprovado = True
                    instance.status = RelatorioAnual.AVALIADO
                    instance.enviar_mensagem_final()
                    log_object(instance, 'Relatório aprovado pelo orientador')

                if '_ajustes' in request.POST:
                    instance.status = RelatorioAnual.REVISADO
                    instance.aprovado = False
                    instance.enviar_convite_correcao()
                    log_object(instance, 'Ajuste solicitado pelo orientador')

                instance.save()

                return render(
                    request, 'base_mensagem.html',
                    {'titulo': 'Obrigado por enviar sua avaliação!',
                     'texto': ''}
                )

        return render(request, 'base_form.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'errors': form.errors})
    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


@transaction.atomic
def editar_producao(request, hash_auth, hash_producao):
    try:
        producao = get_object_or_404(Producao.objects.select_related('pesquisador', 'tipo'), id=hash_producao)

        # Quando não for informada a hash do relatório anual, então a chamada veio do Admin
        if hash_auth is None:
            readonly = False
            relatorio_anual = None
            title = ''
        else:
            visao_orientador = request.GET.get('apr', '') == '1'

            if visao_orientador:
                kwargs = {'hash_apr': hash_auth}
            else:
                kwargs = {'hash_auth': hash_auth}
            # Testar se o pesquisador tem permissão de editar essa produção
            relatorio_anual = get_object_or_404(RelatorioAnual.objects.select_related('pesquisador'), **kwargs)
            readonly = visao_orientador or periodo_fechado(relatorio_anual.ano) or relatorio_anual.readonly()
            title = relatorio_anual.alt_title()

        form_class = get_producao_form(producao.tipo)

        if request.method == 'GET':
            form = form_class(instance=producao, disabled=readonly)
            form.filter_choices()
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

                if relatorio_anual:
                    return redirect(relatorio_anual.get_absolute_url())
                else:
                    return redirect(request.get_full_path())

        errors = helpers.AdminErrorList(form, formsets)

        inline_formsets = form.get_formsets_with_inlines(request, formsets, inlines)

        return render(request, 'producao_change.html',
                      {'form': form, 'title': title, 'inlines': inline_formsets,
                       'errors': errors, 'tipo_producao': producao.tipo})

    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


@staff_member_required
def visualizar_producao(request, hash_producao):
    return editar_producao(request, None, hash_producao)


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

                if form.record:
                    querystring = '?' + urlencode(form.record.items())
                else:
                    querystring = ''

                if form.record.get('ano') and form.record['ano'] != relatorio_anual.ano:
                    messages.warning(request, 'O ano desta produção não condiz com o ano deste relatório')

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
            issn = initial.get('serie', None)
            if issn:
                periodico = Periodico.objects.filter(issn=issn).first()
                if not periodico:
                    periodico = Periodico.objects.filter(eissn=issn).first()
                if periodico:
                    initial['periodico'] = periodico.pk
                    initial['serie'] = ''
            initial['ano'] = relatorio_anual.ano
            form = form_class(initial=initial)
            form.filter_choices()
            form.instance.pesquisador = relatorio_anual.pesquisador

            formsets, inlines = form.get_formsets(request, form.instance)
        else:
            form = form_class(request.POST, request.FILES)
            form.filter_choices()
            form_validated = form.is_valid()

            if form_validated:
                instance = form.save(commit=False)
            else:
                instance = form.instance

            formsets, inlines = form.get_formsets(request, instance)

            if all_valid(formsets) and form_validated:
                instance.pesquisador = relatorio_anual.pesquisador
                instance.tipo = tipo
                instance.ano = instance.ano or relatorio_anual.ano
                instance.save()

                for formset in formsets:
                    formset.save()

                messages.success(request, f'{instance._meta.verbose_name} salva com sucesso')

                return redirect(relatorio_anual.get_absolute_url())

        errors = helpers.AdminErrorList(form, formsets)
        inline_formsets = form.get_formsets_with_inlines(request, formsets, inlines)

        return render(request, 'producao_change.html',
                      {'form': form, 'title': relatorio_anual.alt_title(), 'inlines': inline_formsets, 'add': True,
                       'errors': errors, 'tipo_producao': tipo})

    except Http404:
        return handler404(request, template='avaliacao_anual_404.html')


def deletar_producao(request, hash_auth, hash_producao):
    relatorio_anual = get_object_or_404(RelatorioAnual, hash_auth=hash_auth)
    producao = get_object_or_404(Producao, id=hash_producao)

    if request.method == 'GET':
        response = render(
            request, 'confirma_delete.html',
            context={
                'object': producao, 'title': relatorio_anual.alt_title(),
                'return_url': reverse('editar_producao',
                                      kwargs={'hash_auth': relatorio_anual.hash_auth, 'hash_producao': producao.pk})
            }
        )
    else:
        if periodo_fechado(relatorio_anual.ano) or relatorio_anual.readonly():
            messages.error(request, 'Não é possível excluir esta produção')
        else:
            producao.producaoautor_set.all().delete()
            producao.delete()
            log_object(producao, f'Registro excluído. Relatório Anual {relatorio_anual}.')
            messages.success(request, f'Produção "{producao}", excluída com sucesso!')

        response = redirect('avaliacao_anual', hash_auth=relatorio_anual.hash_auth)

    return response


def busca_orientador(request):
    """
    View utilizada no relatório de orientações para validar o e-mail do orientador e redirecionar para o relatório com
    o hash do id do orientador encontrado.
    """
    if request.method == 'GET':
        programa = request.GET.get('programa', '0')
        response = render(request, 'base_form.html', {'form': BuscaOrientadorForm(initial={'programa': programa})})
    else:
        form = BuscaOrientadorForm(request.POST)

        if form.is_valid():
            querystring = {
                'programa': form.cleaned_data['programa'], 'id': form.professor.pk,
                'hash_auth': generate_hash(str(form.professor.pk))
            }
            link = f'{settings.SITE_URL}{reverse("orientacoes")}?{urlencode(querystring)}'
            sendmail('Conferência de Orientação', [form.cleaned_data['email']],
                     message=f'Por favor clique no link abaixo para conferir '
                             f'a sua lista de orientanda(o)s:\n\n {link}')
            response = render(request, 'base_mensagem.html',
                              {'titulo': 'Solicitação enviada',
                               'texto': 'Por favor, abra o seu email para conferir a lista de orientandos'})
        else:
            response = render(request, 'base_form.html', {'form': form})

    return response


def orientador_autocomplete_view(request):
    curso_id = request.GET.get("curso")
    term = request.GET.get("term", "")  # é o que o usuário digitou
    coorientacao = request.GET.get("coorientacao") == 'true'

    if coorientacao:
        qs = Pesquisador.objects.all()
    else:
        qs = Professor.objects.all()

    if term:
        qs = qs.filter(nome__icontains=term)

    if curso_id and not coorientacao:
        qs = qs.filter(pesquisadorprograma__programa__curso__id=curso_id)

    results = list(map(lambda x: dict(id=x['id'], text=x['nome']), qs.values('id', 'nome')))

    return HttpResponse(json.dumps({'results': results}), content_type='application/json')


def primeiro_acesso(request):
    """
    Envia e-mail com link para finalizar o cadastro do Professor ou Aluno.
    Primeiro tenta processar o e-mail como professor e se não encontrar uma instância de professor,
    processa o e-mail como aluno.
    """

    def redirect_registered_user():
        reset_url = reverse('password_reset')

        messages.warning(
            request,
            mark_safe(
                'Seu cadastro já existe. Caso queira apenas recuperar sua senha, '
                f'<a href="{reset_url}">clique aqui</a>.'
            )
        )
        return redirect('primeiro_acesso')

    def processar_finalizacao_cadastro(obj):
        """Gera o link de finalização de cadastro e envia para o e-mail informado"""
        mensagem = (
            'Seja bem-vindo(a)! Clique no link abaixo para finalizar seu cadastro: '
            f'<a href="{obj.url_finalizacao_cadastro()}">Finalizar Cadastro</a>'
        )
        sendmail('Finalize seu cadastro', [obj.email], message=mensagem)

        messages.success(request, 'Um e-mail foi enviado para você com instruções para finalizar o cadastro.')

        return redirect('primeiro_acesso')

    form = BuscaProfessorAlunoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data.get('email')

        try:
            professor = Professor.objects.get(email=email)

            if professor.user:
                return redirect_registered_user()

            if not professor.cadastro_valido():
                messages.warning(request, f'Seu cadastro necessita de CPF ou ORCID. ({email})'
                                          f'Favor entrar em contato com a secretaria')
                return redirect('primeiro_acesso')

            return processar_finalizacao_cadastro(professor)
        except Professor.MultipleObjectsReturned:
            messages.error(
                request, 'E-mail cadastrado para mais de um professor. Favor entrar em contato com a secretaria.'
            )
            return redirect('primeiro_acesso')
        except Professor.DoesNotExist:
            pass

        try:
            aluno = Aluno.objects.get(email=email)

            if aluno.user:
                return redirect_registered_user()

            if not aluno.cadastro_valido():
                messages.warning(
                    request,
                    'Seu cadastro ainda não está completo. '
                    'Aguarde a data de início de matrícula para acessar o sistema.'
                )
                return redirect('primeiro_acesso')

            return processar_finalizacao_cadastro(aluno)

        except Aluno.DoesNotExist:
            messages.error(request, 'Este e-mail não está cadastrado. Favor entrar em contato com a secretaria.')
        except Aluno.MultipleObjectsReturned:
            messages.error(
                request, 'E-mail cadastrado para mais de um aluno. Favor entrar em contato com a secretaria.'
            )

        return redirect('primeiro_acesso')

    return render(request, 'primeiro_acesso.html', {'form': form})


@login_required
def painel_docente(request):
    try:
        professor = Professor.objects.get(user=request.user)
        turmas = (
            Turma.objects.select_related('disciplina').
            filter(turmaprofessor__professor=professor, periodo__status='A').distinct()
        )

        return render(request, 'painel_docente.html', {'professor': professor, 'turmas': turmas})
    except Professor.DoesNotExist:
        return render(
            request, 'base_mensagem.html',
            {'titulo': 'Acesso Negado',
             'texto': 'Esta função deve ser utilizada apenas para as/os docentes do programa'}
        )


@login_required
def painel_discente(request):
    aluno = Aluno.objects.filter(user_id=request.user.id).first()
    if not aluno or not aluno.matricula_atual:
        return render(request, 'base_mensagem.html',
                      {'titulo': 'Acesso Negado',
                       'texto': 'Esta função deve ser utilizada apenas para as/os discentes do programa'})

    matricula_ativa = aluno.matricula_atual.status in ('A', 'T')
    periodo = Periodo.objects.filter(status=Periodo.Status.ATIVO).order_by('id').last()
    if periodo:
        matriculas_abertas = bool(periodo.dt_fim_matricula and periodo.dt_fim_matricula >= datetime.today().date())
        inscricoes = Inscricao.objects.filter(aluno=aluno, turma__periodo=periodo)
    else:
        matriculas_abertas = False
        inscricoes = Inscricao.objects.none()

    orientacao = aluno.matricula_atual.orientador_atual
    if orientacao:
        orientacao = 'Orientador(a): ' + orientacao
        coorientador = aluno.matricula_atual.coorientador
        if coorientador:
            orientacao += f' Coorientação: {coorientador}'
    else:
        orientacao = 'Ainda sem orientação definida'

    # Configuração de visibilidade dos cards
    visibilidade_cards = {
        'meus_dados': True,
        'historico_escolar': aluno.matricula_atual.curso.historico,
        'boletim': False,
        'requerimentos': matricula_ativa,
        'inscricao_disciplinas': matricula_ativa and matriculas_abertas,
        'disciplinaAtiva': inscricoes.count() > 0,
        'declaracao_matricula': matricula_ativa and aluno.matricula_atual.curso.historico,
        'admin': request.user.is_staff
    }

    disciplinas = [
        {
            'nome': ins.turma.disciplina.titulo,
            'professores': ins.turma.docentes() or 'N/A',  # <- usa o helper
            'carga_horaria': f"{ins.turma.disciplina.creditos} horas",
            'calendario': ins.turma.calendario(),
            'status': ins.get_status_display(),
            'link': getattr(ins.turma, 'link_material', '#'),
        }
        for ins in inscricoes
    ]

    # Renderizando o template com os dados corretos
    return render(request, 'painel_discente.html', {
        'visibilidade_cards': visibilidade_cards,
        'orientacao': orientacao,
        'disciplinas': disciplinas,
        'matricula_numero': aluno.matricula_atual.numero,
        'matricula_id': aluno.matricula_atual.id,  # ✅ necessário pro link
    })

def notificacao_orientador_sem_email(curso: Curso, orientador: Pesquisador):
    sendmail(
        "Atenção: Orientador/Coorientador sem email registrado",
        [ curso.email_secretaria, ],
        message= f'O orientador/coorientador {orientador.nome} está sem o email registrado',
        thread=True,
    )

@login_required
def solicita_orientador_view(request):
    if request.method == "POST":
        try:
            aluno = Aluno.objects.get(user_id=request.user.id)
        except Aluno.DoesNotExist:
            messages.error(request, "Aluno não encontrado.")
            return redirect("painel_discente")
        form = SolicitaOrientadorForm(request.POST, aluno=aluno)
        if form.is_valid():
            try:
                matricula = Matricula.objects.get(pesquisador_id=aluno.id, status=STATUS_ATIVO)
            except Matricula.DoesNotExist:
                messages.error(request, "Nenhuma matricula ativa para a/o discente")
                return redirect("painel_discente")

            email_secretaria = matricula.curso.email_secretaria

            tipo_ocorrencia = TipoOcorrencia.objects.get(id=1)
            orientador = form.cleaned_data["orientador"]
            coorientador = form.cleaned_data.get("coorientador")
            hoje = date.today()

            # Criar o registro de Orientação
            orientacao = Orientacao.objects.create(
                orientador=orientador,
                coorientacao=False,
                aluno=aluno,
                matricula=matricula,
                dt_inicio=hoje,
                status=Orientacao.Status.SOLICITADA
            )
            # Criar logs da orientação
            log_object(aluno, f"Requerimento de Orientação para {orientador}")
            log_object(orientacao, f"Requerimento solicitado via formulário")
            log_object(orientador, f"Nova(o) orientanda(o): {aluno}")

            coorientador_externo = form.cleaned_data.get("nome_completo_externo")
            if coorientador:
                nome_coorientador = coorientador.nome
                email_coorientador = coorientador.email
            else:
                nome_coorientador = coorientador_externo
                email_coorientador = form.cleaned_data.get("email_externo")

            if nome_coorientador:
                coorientador_se_houver = f' e coorientador(a) {nome_coorientador}'
            else:
                coorientador_se_houver = ''

            ocorrencia = MatriculaEvento.objects.create(
                tipo=tipo_ocorrencia,
                matricula=matricula,
                dtevento=hoje,
                status=MatriculaEvento.Status.FINALIZADO,
                obs=form.cleaned_data["comentarios_adicionais"],
            )

            # a criação é feita em 2 etapas pois o evento.id deve ser registrado na descrição
            ocorrencia.descricao = tipo_ocorrencia.template.format(**locals())
            ocorrencia.save()

            # Cria registro de Pesquisador para o Coorientador externo, caso exista
            if not coorientador and coorientador_externo:
                id_cnpq = form.cleaned_data.get("link_lattes")
                lattes_atualizado = False
                if id_cnpq:
                    coorientador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
                    if not coorientador:
                        if obtem_dt_cnpq(id_cnpq):
                            lattes_atualizado = True
                        else:
                            lattes_atualizado = False

                # se não achou o coorientador pelo id_cnpq, tentar pelo ORCID
                orcid = form.cleaned_data.get("orcid")
                if not coorientador and orcid:
                    coorientador = Pesquisador.objects.filter(orcid=orcid).first()

                if coorientador:
                    # atualiza o orcid caso o orientador não tenha ele preenchido
                    if not coorientador.orcid and orcid:
                        coorientador.orcid = orcid
                        coorientador.save()
                else:
                    coorientador = Pesquisador.objects.create(
                        nome=form.cleaned_data.get("nome_completo_externo"),
                        email=form.cleaned_data.get("email_externo"),
                        id_cnpq=id_cnpq,
                        orcid=orcid,
                        atualizado=lattes_atualizado)

                ultimo = (
                    MatriculaEventoPesquisador.objects
                    .filter(evento=ocorrencia)
                    .order_by('-ordem')
                    .first()
                )

                MatriculaEventoPesquisador.objects.create(
                    evento=ocorrencia,
                    pesquisador=coorientador,
                    instituicao=form.cleaned_data.get("instituicao_externa"),
                    externo=True,  # coorientador informado manualmente é externo
                    suplente=False,
                    ordem=(ultimo.ordem if ultimo else 0) + 1,  # Considerando ultimo + 1
                )

            if coorientador:
                coorientacao = Orientacao.objects.create(
                    orientador=coorientador,
                    coorientacao=True,
                    aluno=aluno,
                    matricula=matricula,
                    dt_inicio=hoje,
                    status=Orientacao.Status.SOLICITADA
                )
                log_object(coorientador, f"Nova coorientação: {aluno}")
                log_object(coorientacao, f"Registrado via solicitação da/o discente")
            else:
                coorientacao = None

            # Enviar e-mail para o orientador
            link = f"{settings.SITE_URL}/confirmar_orientacao/{orientacao.id}"
            modelo = TipoNotificacao.objects.get(tipo_ocorrencia=tipo_ocorrencia,
                                                 destinatario=TipoNotificacao.Fluxo.ORIENTADOR)
            mensagem = modelo.texto.format(**locals())
            sendmail(
                subject="Solicitação de Orientação",
                dest_list=[orientador.email],
                message=mensagem
            )
            if coorientador:
                if email_coorientador:
                    link = f"{settings.SITE_URL}/confirmar_orientacao/{coorientacao.id}"
                    mensagem = modelo.texto.format(**locals())
                    sendmail(
                        subject="Solicitação de Coorientação",
                        dest_list=[email_coorientador],
                        message=mensagem
                    )
                else:
                    notificacao_orientador_sem_email( matricula.curso, coorientador )

            if aluno.email:
                modelo = TipoNotificacao.objects.filter(tipo_ocorrencia=tipo_ocorrencia,
                                                        destinatario=TipoNotificacao.Fluxo.CRIACAO)
                if modelo:
                    mensagem = modelo[0].texto.format(**locals())
                    sendmail(
                        subject=tipo_ocorrencia.descricao,
                        dest_list=[aluno.email],
                        message=mensagem
                    )
            else:
                sendmail(
                    subject="Discente sem email registrado",
                    dest_list=[email_secretaria],
                    message=f"A/O discente {aluno.nome} está sem um email registrado. Verifique!"
                )

            # Exibir mensagem de sucesso
            messages.success(request, "O requerimento foi solicitado com sucesso")
            return redirect("painel_discente")

    else:
        # Obtenha o aluno e passe-o para o formulário
        user_id = request.user.id  # ID do aluno fixo para teste (substituir depois)
        try:
            aluno = Aluno.objects.get(user_id=user_id)
            tipo = TipoOcorrencia.objects.get(id=1)
            evento = (
                MatriculaEvento.objects.filter(matricula=aluno.matricula_atual, tipo=tipo).
                exclude(status__in=(MatriculaEvento.Status.APROVACAO_CD, MatriculaEvento.Status.CANCELADO)).first()
            )
            if evento:
                messages.error(request, "Já existe uma solicitação em andamento." +
                               "Entre em contato com a secretaria caso você queira alterar os dados")
                return redirect("painel_discente")

            form = SolicitaOrientadorForm(aluno=aluno)  # Passa o aluno para o formulário
        except Aluno.DoesNotExist:
            messages.error(request, "Erro: Cadastro do aluno não encontrado")
            return redirect("painel_discente")

    return render(request, "solicita_orientador.html", {"form": form})


def confirmar_orientacao(request, orientacao_id):
    orientacao = Orientacao.objects.filter(id=orientacao_id, status=Orientacao.Status.SOLICITADA).first()
    if not orientacao:
        mensagem = 'Solicitação de Orientação não encontrada ou já aprovada'
    else:
        orientacao.status = Orientacao.Status.PENDENTE
        orientacao.save()
        if orientacao.coorientacao:
            mensagem = 'Solicitação aprovada pelo coorientador'
        else:
            mensagem = 'Solicitação aprovada'
        log_object(orientacao, mensagem)
        log_object(orientacao.matricula, mensagem)
        # verifica se ainda orientações pendentes para essa matrícula
        pendentes = Orientacao.objects.filter(matricula=orientacao.matricula,
                                              status=Orientacao.Status.SOLICITADA).count()
        if pendentes == 0:
            tipo_ocorrencia = TipoOcorrencia.objects.get(id=1)
            evento = MatriculaEvento.objects.filter(matricula=orientacao.matricula, tipo=tipo_ocorrencia).first()
            evento.status = MatriculaEvento.Status.APROVACAO_ORIENTADOR
            evento.save()
            log_object(evento, mensagem)

    return render(request, 'base_mensagem.html', context={'texto': mensagem})


@login_required
def requerimentos(request):
    aluno = Aluno.objects.filter(user=request.user).first()
    if aluno and aluno.matricula_atual:
        curso = aluno.matricula_atual.curso
        tipos_ativos = TipoOcorrencia.objects.filter(status=TipoOcorrencia.Status.ATIVO, cursos=curso)
        realizados = MatriculaEvento.objects.filter(
            matricula=aluno.matricula_atual).exclude(
            status=MatriculaEvento.Status.EM_EDICAO)
        return render(request, 'requerimentos.html',
                      {'tipos_ocorrencia': tipos_ativos, 'realizados': realizados})
    else:
        messages.error(request, "Matrícula não encontrada ou incompatível")
        return redirect("painel_discente")


def redirect_authenticated_user(user):
    """Redireciona com base no tipo de usuário"""
    professor = Professor.objects.filter(user=user).exists()
    if professor:
        return redirect('/painel-docente/')

    discente = Aluno.objects.filter(user=user).exists()
    if discente:
        return redirect('/painel-discente/')

    return redirect('/admin/')


def login_custom(request):
    """View para direcionar painel depedendo do usuário"""

    # se o usuário já está logado, já faz o redirect automaticamente
    if request.user.is_authenticated:
        return redirect_authenticated_user(request.user)

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Redireciona com base no tipo de usuário
            storage = get_messages(request)
            list(storage)  # Esvazia o storage ao iterar

            return redirect_authenticated_user(user)
        else:
            messages.error(request, "Usuário ou senha incorretos.")

    else:
        form = AuthenticationForm()

    return render(request, "admin/login.html", {"form": form})


@login_required
def homologacao_defesa(request):
    tipo = request.GET.get("tipo")
    etapa_homologacao = request.GET.get("etapa")

    if not tipo or not etapa_homologacao:
        messages.error(request, "Requerimento inválido")
        return redirect("painel_discente")

    tipo_ocorrencia = TipoOcorrencia.objects.filter(id=tipo).first()
    if not tipo_ocorrencia:
        messages.error(request, "Requerimento inválido")
        return redirect("painel_discente")

    etapa_homologacao = etapa_homologacao.upper()
    if etapa_homologacao not in ("D", "Q"):
        messages.error(request, "Etapa de homologação inválida")
        return redirect("painel_discente")

    titulo_formulario = tipo_ocorrencia.descricao

    # Obter a matrícula do aluno
    aluno = Aluno.objects.get(user_id=request.user.id)
    orientacao = Orientacao.objects.filter(
        aluno=aluno,
        status=Orientacao.Status.ATIVA
    ).first()
    if not orientacao or not orientacao.orientador:
        messages.error(
            request,
            'Para solicitar homologação de defesa ou qualificação, um orientador precisa estar associado à sua matrícula.'
        )
        return redirect('painel_discente')

    # Verifica se o aluno tem matrícula ativa
    if not aluno.matricula_atual or aluno.matricula_atual.status != 'A':  # 'A' = Ativa
        messages.error(request,
                       "Sua matrícula não está ativa. Caso esta informação não esteja correta, entre em contato com a secretaria.")
        return redirect('painel_discente')

    # Verifica se a matrícula ativa corresponde ao tipo de homologação
    curso = aluno.matricula_atual.curso
    if not tipo_ocorrencia.cursos.filter(pk=curso.pk).exists():
        messages.error(request, "Sua matrícula não permite a solicitação demandada")
        return redirect('painel_discente')

    # Verifica se a data da qualificação foi registrada antes da defesa
    if etapa_homologacao == 'D' and not aluno.matricula_atual.dtquali:
        messages.warning(request,
                         "A data da qualificação ainda não está registrada. Por favor procure a secretaria para comprovar a qualificação.")
        return redirect('painel_discente')

    # Buscar MatriculaEvento existente
    matricula_evento = MatriculaEvento.objects.filter(
        matricula=aluno.matricula_atual, status=MatriculaEvento.Status.EM_EDICAO
    ).first()

    necessita_historico = not aluno.matricula_atual.curso.historico

    if request.method == "POST":
        form = HomologacaoDefesaForm(request.POST, request.FILES,
                                     instance=matricula_evento,
                                     matricula=aluno.matricula_atual.id,
                                     tipo_ocorrencia=tipo_ocorrencia.id,
                                     historico=necessita_historico)
        if form.is_valid():
            # Salva o MatriculaEvento e o anexo, se presente
            matricula_evento = form.save()

            # Mensagem de sucesso no modal
            messages.success(request,
                             "Solicitação agendada com sucesso. Agora vamos definir a banca para finalizar o processo")
            return redirect('solicitacao_defesa_membros', id_matricula_evento=matricula_evento.id)

    else:
        # Converte para o formato esperado pelo input HTML (yyyy-MM-dd)
        if matricula_evento and matricula_evento.dtevento:
            matricula_evento.dtevento = matricula_evento.dtevento.strftime('%Y-%m-%d')

        form = HomologacaoDefesaForm(instance=matricula_evento,
                                     matricula=aluno.matricula_atual.id,
                                     tipo_ocorrencia=tipo_ocorrencia,
                                     historico=necessita_historico)

    return render(request, 'homologacao_defesa.html', {
        'form': form,
        'titulo_formulario': titulo_formulario
    })


@login_required
def solicitacao_defesa_membros(request, id_matricula_evento):
    ocorrencia = get_object_or_404(
        MatriculaEvento.objects.select_related(
            'matricula__pesquisador',
            'matricula__curso',
            'tipo',
        ),
        id=id_matricula_evento,
    )
    aluno = ocorrencia.matricula.pesquisador
    if aluno.user != request.user:
        return render_mensagem('Acesso inválido', 'Você não tem permissão para acessar este formulário')

    orientacao = Orientacao.objects.select_related('orientador').filter(
        aluno=aluno,
        status=Orientacao.Status.ATIVA,
        coorientacao=False,
    ).first()
    if not orientacao or not orientacao.orientador:
        messages.error(
            request,
            'Para solicitar homologação de defesa ou qualificação, '
            'um orientador precisa estar cadastrado e aprovado.'
        )
        return redirect('painel_discente')

    tipo_ocorrencia = ocorrencia.tipo
    programa = ocorrencia.matricula.curso.programa_id

    # A chave "obrigatorio" declara se a posição exige preenchimento.
    # Posições de membro externo podem ser opcionais (obrigatorio=False).
    # Mestrado
    if tipo_ocorrencia.id in {3, 4}:
        parametros = [
            {"externo": 'I', "suplente": False, "label": "Interno", "obrigatorio": True},
            {"externo": 'E', "suplente": False, "label": "Externo", "obrigatorio": True},
            {"externo": 'I', "suplente": True, "label": "Suplente Interno", "obrigatorio": True},
            {"externo": 'E', "suplente": True, "label": "Suplente Externo", "obrigatorio": False}
        ]
    # Doutorado
    elif tipo_ocorrencia.id == 2:
        parametros = [
            {"externo": 'I', "suplente": False, "label": "Interno", "obrigatorio": True},
            {"externo": 'I', "suplente": False, "label": "Interno", "obrigatorio": True},
            {"externo": 'E', "suplente": False, "label": "Externo", "obrigatorio": True},
            {"externo": 'E', "suplente": False, "label": "Externo", "obrigatorio": True},
            {"externo": 'I', "suplente": True, "label": "Suplente Interno", "obrigatorio": True},
            {"externo": 'E', "suplente": True, "label": "Suplente Externo", "obrigatorio": True}
        ]
    elif tipo_ocorrencia.id == 5:
        parametros = [
            {"externo": 'I', "suplente": False, "label": "Interno", "obrigatorio": True},
            {"externo": 'E', "suplente": False, "label": "Externo", "obrigatorio": True},
            {"externo": 'A', "suplente": False, "label": "Interno ou Externo", "obrigatorio": True},
            {"externo": 'A', "suplente": False,  "label": "Interno ou Externo (Opcional)", "obrigatorio": False},
            {"externo": 'A', "suplente": True,  "label": "Suplente Interno ou Externo", "obrigatorio": True},
            {"externo": 'A', "suplente": True,  "label": "Suplente Interno ou Externo (Opcional)", "obrigatorio": False}
        ]
    else:
        parametros = []

    if request.method == 'POST':
        forms = [
            MatriculaEventoPesquisadorForm(request.POST, prefix=str(i), programa=programa,
                                           obrigatorio=parametros[i]['obrigatorio'],
                                           initial={"externo": parametros[i]['externo']})
            for i in range(len(parametros))]

        if all(form.is_valid() for form in forms):
            # Considera apenas as posições preenchidas (uma posição opcional pode ficar vazia)
            pesquisadores = [form.cleaned_data.get('pesquisador') for form in forms]
            pesquisadores = [p for p in pesquisadores if p is not None]

            tudo_ok = True
            if orientacao.orientador in pesquisadores:
                messages.error(request,"O orientador não pode ser um dos membros da banca!")
                tudo_ok = False

            coorientacao = Orientacao.objects.filter(
                aluno=aluno, status=Orientacao.Status.ATIVA, coorientacao=True).first()
            if coorientacao and coorientacao.orientador in pesquisadores:
                messages.error(request, "O coorientador não pode ser um dos membros da banca!")
                tudo_ok = False

            # Verifica se há duplicatas entre as posições preenchidas
            if len(pesquisadores) != len(set(pesquisadores)):
                messages.error(request,
                               "Há participantes repetidos na banca. Verifique os nomes e tente novamente.")
                tudo_ok = False

            if tudo_ok:
                inst_por_pesquisador = {}
                pesquisadorinstituicao_queryset = (
                    PesquisadorInstituicao.objects.filter(pesquisador__in=pesquisadores).select_related('instituicao')
                )
                # Armazena em cache o primeiro PesquisadorInstituicao encontrado, usando dict.setdefault.
                # Evita executar PesquisadorInstituicao.objects...first() para cada form
                for pi in pesquisadorinstituicao_queryset:
                    # setdefault mantém apenas o 1º registro de cada pesquisador
                    inst_por_pesquisador.setdefault(pi.pesquisador_id, pi.instituicao)

                for i, form in enumerate(forms):
                    pesquisador = form.cleaned_data.get('pesquisador')
                    # Pula posições opcionais que não foram preenchidas
                    if pesquisador is None:
                        continue
                    instituicao = inst_por_pesquisador.get(pesquisador.id)

                    # Deriva a flag "externo" do vínculo real do pesquisador com o programa.
                    # Posições fixas ('I'/'E') seguem a definição; posições 'A' (interno ou
                    # externo) são resolvidas pela existência de vínculo com o programa, evitando
                    # marcar como externo um docente interno escolhido numa vaga flexível.
                    posicao = parametros[i]['externo']
                    if posicao == 'I':
                        externo = False
                    elif posicao == 'E':
                        externo = True
                    else:
                        externo = not pesquisador.pesquisadorprograma_set.filter(
                            programa_id=programa).exists()

                    MatriculaEventoPesquisador.objects.create(
                        evento=ocorrencia,
                        pesquisador=pesquisador,
                        ordem=i + 2,
                        externo=externo,
                        suplente=parametros[i]['suplente'],
                        instituicao=instituicao,
                        status=MatriculaEventoPesquisador.Status.VALIDADO
                    )

                MatriculaEventoPesquisador.objects.get_or_create(
                    evento=ocorrencia,
                    pesquisador=orientacao.orientador,
                    defaults={'ordem': 0, 'externo': False, 'suplente': False,
                              'status': MatriculaEventoPesquisador.Status.VALIDADO}
                )

                if coorientacao:
                    coorientador_se_houver = f'e coorientado por {coorientacao.orientador.nome}'
                    instituicao = PesquisadorInstituicao.objects.filter(pesquisador=coorientacao.orientador).first()
                    if instituicao:
                        instituicao = instituicao.instituicao
                    MatriculaEventoPesquisador.objects.get_or_create(
                        evento=ocorrencia,
                        pesquisador=coorientacao.orientador,
                        defaults={'ordem': 1, 'externo': False, 'suplente': False,
                                  'instituicao': instituicao,
                                  'status': MatriculaEventoPesquisador.Status.VALIDADO}
                    )

                # Atualiza o status do evento para FINALIZADO após todos os membros serem salvos
                matricula = ocorrencia.matricula
                orientador = orientacao.orientador
                horario = ocorrencia.dtevento.strftime('%d/%m/%Y') + ' às ' + ocorrencia.horario.strftime('%H:%M')
                modalidade = ocorrencia.get_modalidade_display()
                ocorrencia.descricao = tipo_ocorrencia.template.format(**locals())
                ocorrencia.status = MatriculaEvento.Status.FINALIZADO
                ocorrencia.save()

                log_object(ocorrencia, 'Solicitação de banca preenchida com sucesso pela/o discente')

                # envia email para o orientador para que ele aprove a banca
                ocorrencia.solicita_aprovacao_orientador(orientador)

                # Enviar a confirmação para o Aluno
                notificacao = tipo_ocorrencia.tiponotificacao_set.filter(
                    destinatario=TipoNotificacao.Fluxo.CRIACAO).first()
                if notificacao:
                    assunto = tipo_ocorrencia.descricao
                    mensagem = notificacao.texto.format(**locals())
                    sendmail(assunto, [aluno.email], message=mensagem)

                messages.success(request, "Solicitação de Banca realizada com sucesso!")
                return redirect('painel_discente')

    forms = [
        MatriculaEventoPesquisadorForm(
            prefix=str(i),
            programa=programa,
            obrigatorio=parametros[i]['obrigatorio'],
            initial={
                "evento": ocorrencia,
                "externo": parametros[i]['externo'],
                "suplente": parametros[i]['suplente'],
                "ordem": i + 1,
                "status": MatriculaEventoPesquisador.Status.EM_EDICAO.value,
            }
        )
        for i in range(len(parametros))
    ]

    for i, form in enumerate(forms):
        form.fields['pesquisador'].label = 'Membro ' + parametros[i]['label']
        form.css_classes = "stacked-inline-form"
        # Marca cada form como titular ou suplente para segregar na tela.
        form.eh_suplente = parametros[i]['suplente']

    # Segrega os membros titulares dos suplentes, para o discente não confundir
    # quem compõe a banca efetiva e quem é suplente.
    forms_titulares = [form for form in forms if not form.eh_suplente]
    forms_suplentes = [form for form in forms if form.eh_suplente]

    form_novo_membro_externo = VincularMembroExternoForm(initial={'matricula_evento_id': ocorrencia.id})

    return render(request, 'solicitacao_defesa_membros.html', {
        'tipo_ocorrencia': tipo_ocorrencia,
        'matricula_evento': ocorrencia,
        'forms_pesquisadores': forms,
        'forms_titulares': forms_titulares,
        'forms_suplentes': forms_suplentes,
        'form_membro_externo': form_novo_membro_externo,  # Passando para o template
    })


@login_required
@require_POST
def identificar_membro_externo(request):
    """
    Etapa AJAX: identifica/cria o ``Pesquisador`` e devolve seu id em JSON.

    Caminhos mutuamente exclusivos: não estrangeiro usa o ID CNPq (Lattes);
    estrangeiro usa ORCID + Nome. O e-mail é comum aos dois. Os erros são
    devolvidos no formato de ``form.errors.as_json()`` (``{campo: [{message,
    code}]}``) para o cliente exibi-los inline por campo.
    """
    form = IdentificarMembroExternoForm(request.POST)
    if not form.is_valid():
        return JsonResponse(json.loads(form.errors.as_json()), status=400)

    try:
        pesquisador = form.save()
    except ValidationError as e:
        # Atribui o erro ao campo do caminho em uso para exibição inline
        campo = 'orcid' if form.cleaned_data.get('estrangeiro') else 'id_cnpq'
        return JsonResponse(
            {campo: [{'message': m, 'code': 'invalid'} for m in e.messages]},
            status=400
        )
    except (TimeoutError, InvalidXMLException):
        return JsonResponse(
            {'__all__': [{'message': "Não foi possível recuperar o currículo "
                                     "Lattes. Entre em contato com a secretaria.",
                          'code': 'error'}]},
            status=400
        )

    # Pré-seleciona apenas a primeira instituição do pesquisador no combo (Etapa 3)
    vinculo = (PesquisadorInstituicao.objects
               .select_related('instituicao')
               .filter(pesquisador=pesquisador)
               .order_by('instituicao__nome')
               .first())
    instituicao = {'id': vinculo.instituicao_id, 'nome': vinculo.instituicao.nome} if vinculo else None

    return JsonResponse({
        'pesquisador_id': pesquisador.id,
        'nome': pesquisador.nome,
        'instituicao': instituicao,
    })


@login_required
@require_POST
def vincular_membro_externo(request):
    """
    Etapa final (AJAX): vincula o pesquisador já identificado à instituição.

    Não cria o membro externo (o ``Pesquisador`` é criado em
    ``identificar_membro_externo``); apenas grava o vínculo com a instituição
    (criando a ``Instituicao`` se for nova, em ``form.save()``). Retorna JSON para
    não recarregar a página de solicitação de defesa — assim as seleções de banca
    em andamento são preservadas.
    """
    form = VincularMembroExternoForm(request.POST)
    if not form.is_valid():
        return JsonResponse(json.loads(form.errors.as_json()), status=400)

    pesquisador = form.save(user=request.user)

    return JsonResponse({'sucesso': True, 'pesquisador_id': pesquisador.id, 'nome': pesquisador.nome})


def solicitacao_defesa_aprovacao(request, hash_id_matricula_evento):
    matricula_evento_id = None
    for evento in MatriculaEvento.objects.all().only('id').iterator():
        if generate_hash(str(evento.id)) == hash_id_matricula_evento:
            matricula_evento_id = evento.id
            break
    if not matricula_evento_id:
        raise Http404

    matricula_evento = get_object_or_404(MatriculaEvento, id=matricula_evento_id)

    # Busca membros da banca vinculados
    membros_banca = (
        MatriculaEventoPesquisador.objects
        .filter(evento=matricula_evento)
        .select_related('pesquisador', 'evento__matricula')
    )

    # Busca o aluno vinculado
    aluno = matricula_evento.matricula.pesquisador

    # Se a requisição for POST
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "aprovar":
            matricula_evento.status = MatriculaEvento.Status.APROVACAO_ORIENTADOR
            matricula_evento.save()

            log_object(matricula_evento, 'Solicitação de banca aprovada pelo orientador')

            # E-mail de aprovação
            mensagem_aluno = (
                f"Prezado(a) {aluno.nome},\n\n"
                "Sua solicitação de banca foi aprovada pela(o) orientador(a) e será agora avaliada na próxima CD.\n\n"
                "Atenciosamente,\n"
                "Coordenação"
            )
            sendmail(
                "Solicitação de Banca aprovada",
                [aluno.email],
                message=mensagem_aluno
            )

            # Notifica a lista "Destinatários de Agendamento de Bancas".
            matricula_evento.notifica_banca_agendada()

            return render(
                request, 'base_mensagem.html',
                context={'titulo': 'Obrigado!',
                         'texto': 'A banca será agora avaliada na próxima CD.'}
            )

        elif action == "ajustar":
            matricula_evento.status = MatriculaEvento.Status.EM_EDICAO
            matricula_evento.save()

            # E-mail de solicitação de ajustes
            mensagem_aluno = (
                f"Prezada(o) {aluno.nome},\n\n"
                "A sua solicitação de Banca requer ajustes.\n"
                "Entre em contato o seu orientador pois foram encontrados problemas na sua solicitação.\n\n"
                "Atenciosamente,\n"
                "Coordenação"
            )
            sendmail(
                "Solicitação de Banca requer ajustes",
                [aluno.email],
                message=mensagem_aluno
            )
            return render(
                request, 'base_mensagem.html',
                context={'titulo': 'Atenção!',
                         'texto': "Solicitação de ajustes enviada para a coordenação e para a/o discente"}
            )

    # Renderiza a página com os dados
    return render(request, "solicitacao_defesa_aprovacao.html", {
        "titulo": " ".join(matricula_evento.tipo.descricao.split()[-3:]),
        "matricula_evento": matricula_evento,
        "membros_banca": membros_banca
    })


def defesa(request, id_discente, id_evento):
    matricula_evento = get_object_or_404(MatriculaEvento.objects.select_related('matricula__pesquisador'), id=id_evento)

    # Confere se o discente do evento bate com o informado na URL
    if matricula_evento.matricula.pesquisador.pk != id_discente:
        raise Http404

    # Se a ocorrência está cancelada, redireciona para uma ocorrência de banca
    # válida do mesmo discente — a mais recente por data. Uma ocorrência é
    # considerada válida quando é de banca (tipos 2–5) e seu status não é
    # CANCELADO nem NAO_APROVADO. Caso não exista nenhuma, mantém 404.
    if matricula_evento.status == MatriculaEvento.Status.CANCELADO:
        ocorrencia_valida = (
            MatriculaEvento.objects
            .filter(matricula__pesquisador_id=id_discente, tipo__in=(2, 3, 4, 5))
            .exclude(status__in=(MatriculaEvento.Status.CANCELADO,
                                 MatriculaEvento.Status.NAO_APROVADO))
            .order_by('-dtevento')
            .first()
        )
        if not ocorrencia_valida:
            raise Http404
        return redirect('defesa', id_discente=id_discente, id_evento=ocorrencia_valida.id)

    membros_banca = matricula_evento.matriculaeventopesquisador_set.select_related(
        'evento__matricula', 'pesquisador').all()

    return render(request, "defesa.html", {
        "titulo": " ".join(matricula_evento.tipo.descricao.split()[-3:]),
        "matricula_evento": matricula_evento,
        "membros_banca": membros_banca,
    })


@staff_member_required
def ata_ocorrencias_pdf(request, ata_id):
    """Gera um PDF listando as ocorrências (descrição) associadas a uma ata."""
    ata = get_object_or_404(AtaReuniao, id=ata_id)
    ocorrencias = ata.matriculaevento_set.select_related('tipo').order_by('dtevento', 'id')

    html = render_to_string('ata_ocorrencias_pdf.html', {
        'ata': ata,
        'ocorrencias': ocorrencias,
    }, request=request)
    pdf = HTML(string=html, base_url='').write_pdf()

    filename = f'ata_{ata.id}.pdf'
    disposition = 'attachment' if request.GET.get('download') else 'inline'
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    return resp


@login_required
def inscricao_disciplina(request):
    aluno = Aluno.objects.filter(user=request.user).first()
    if not aluno:
        return render_mensagem(request, 'Acesso inválido', 'Este formulário é destinado apenas para discentes')

    hoje = date.today()
    periodo_corrente = Periodo.objects.filter(status=Periodo.Status.ATIVO).last()

    if not periodo_corrente or periodo_corrente.status != Periodo.Status.ATIVO or periodo_corrente.dt_fim_matricula < hoje:
        messages.error(request, 'Fora do período para inscrição')
        return redirect('painel_discente')

    if not aluno.matricula_atual:
        messages.error(request, 'Nenhuma matrícula ativa. Entre em contato com a secretaria')
        return redirect('painel_discente')

    if aluno.matricula_atual.status != 'A':
        messages.error(request, 'Sua matrícula está trancada ou inativa. Verifique com a secretaria')
        return redirect('painel_discente')

    if request.method == 'POST':
        form = InscricaoDisciplinaForm(request.POST, aluno=aluno, periodo_corrente=periodo_corrente)
        if form.is_valid():
            disciplinas_selecionadas = form.cleaned_data['disciplinas']
            disciplinas_inscritas_com_sucesso = []
            for disciplina in disciplinas_selecionadas:
                turma = disciplina.turma_ativa()

                if not turma and disciplina.status == Disciplina.Status.PERMANENTE:
                    turma = Turma.objects.create(
                        disciplina=disciplina,
                        periodo=periodo_corrente,
                        num_alunos_max=100,
                        externa=False,
                    )

                if not turma:
                    messages.error(request, f'Não foi possível encontrar a turma para {disciplina.titulo}.')
                    continue

                ja_inscrito = Inscricao.objects.filter(aluno=aluno, turma=turma).exists()
                if ja_inscrito:
                    messages.warning(request, f'Você já está inscrito em {disciplina.titulo}.')
                else:
                    Inscricao.objects.create(
                        aluno=aluno,
                        matricula=aluno.matricula_atual,
                        turma=turma,
                        status=Inscricao.Status.MATRICULADO,
                    )
                    try:
                        # o ideal é gravar no log do Aluno, caso a inscrição não seja para o aluno, gravar no histórico do pesquisador
                        aluno_proxy = Aluno.objects.get(pk=aluno.pk)
                    except Aluno.DoesNotExist:
                        aluno_proxy = aluno
                    mensagem = f'Inscrição via formulário na turma {turma}'
                    log_object(aluno_proxy, mensagem)
                    log_object(aluno.matricula_atual, mensagem)
                    disciplinas_inscritas_com_sucesso.append(disciplina.titulo)

            # Mensagem única ao final
            if disciplinas_inscritas_com_sucesso:
                nomes = ', '.join(disciplinas_inscritas_com_sucesso)
                messages.success(request, f'Inscrição realizada com sucesso nas disciplinas: {nomes}.')

            return redirect('painel_discente')
        else:
            if 'disciplinas' in form.errors:
                messages.warning(request, 'Selecione ao menos uma disciplina para confirmar a inscrição.')

    else:
        form = InscricaoDisciplinaForm(aluno=aluno, periodo_corrente=periodo_corrente)

    # Agora passamos o queryset de inscrições diretamente
    inscricoes = Inscricao.objects.filter(aluno=aluno, turma__periodo=periodo_corrente)

    disciplinas_inscritas = [
        {
            'id': inscricao.id,
            'nome': inscricao.turma.titulo or inscricao.turma.disciplina.titulo,
            'professor': inscricao.turma.docentes(),
            'carga_horaria': f"{inscricao.turma.disciplina.carga_horaria} horas",
            'calendario': inscricao.turma.calendario(),
            'status': inscricao.get_status_display(),
        }
        for inscricao in inscricoes
    ]

    return render(request, 'inscricao_disciplina.html', {
        'form': form,
        'inscricoes': disciplinas_inscritas,
        'periodo_corrente': periodo_corrente,
        'hoje': timezone.now().date(),
    })


@login_required
def cancelar_inscricao(request, inscricao_id):
    if request.method != 'POST':
        return redirect('inscricao_disciplina')

    inscricao = get_object_or_404(Inscricao, id=inscricao_id)
    # garante que o dono é quem está logado
    if inscricao.aluno_id != request.user.pesquisador.id:
        messages.error(request, 'Operação não permitida.')
        return redirect('inscricao_disciplina')

    periodo = inscricao.turma.periodo
    hoje = timezone.now().date()

    # Só permite se período ativo e dentro do prazo
    if not (periodo.status == Periodo.Status.ATIVO and periodo.dt_fim_matricula and hoje <= periodo.dt_fim_matricula):
        messages.warning(request, 'Cancelamento não permitido neste momento.')
        return redirect('inscricao_disciplina')

    try:
        aluno = Aluno.objects.get(pk=inscricao.aluno.pk)
    except Aluno.DoesNotExist:
        aluno = inscricao.aluno
    mensagem = f'Inscrição cancelada na turma {inscricao.turma}'

    # remove a inscrição
    inscricao.delete()
    log_object(aluno, mensagem)
    if aluno.matricula_atual:
        log_object(aluno.matricula_atual, mensagem)

    messages.success(request, mensagem)
    return redirect('inscricao_disciplina')


@login_required
def historico(request):
    matricula_hash = request.GET.get("matricula") or ""
    matricula_id = matricula_hash.split('-')[0]
    titulo = 'Histórico Escolar'

    if matricula_id:
        matricula = get_object_or_404(Matricula, pk=matricula_id)
        if matricula:
            aluno = matricula.pesquisador
            if matricula.hash != matricula_hash:
                matricula = None
    else:
        aluno = Aluno.objects.filter(user_id=request.user.id).first()
        if not aluno:
            return render_mensagem(request, titulo, "Discente não encontrada/o.")
        matricula = aluno.matricula_atual

    if not matricula:
        return render_mensagem(request, titulo, "Nenhuma matrícula encontrada")

    if not hasattr(aluno, 'alunoregistro'):
        return render_mensagem(
            request, titulo, "Dados gerais da/o discente não encontrados. Provavelmente é um discente antigo."
        )

    if not aluno.CPF and not aluno.orcid:
        return render_mensagem(request, titulo, "CPF ou ORCID ainda não foi registrado. Verifique com a secretaria")

    gerar_pdf = request.GET.get("pdf") == "1"

    validacao = matricula.hash.split('-')[1]
    link_validacao = f"{settings.SITE_URL}/doc/validacao/{validacao}-M{matricula.id}"
    if matricula.dtconclusao:
        dtconclusao = matricula.dtconclusao.strftime("%d/%m/%Y")
    else:
        dtconclusao = ''
    if aluno.alunoregistro.dtnascimento:
        dtnascimento = aluno.alunoregistro.dtnascimento.strftime("%d/%m/%Y")
    else:
        dtnascimento = ''

    context = {
        "id": matricula.id,
        "matricula_hash": matricula_hash,
        "titulo_nivel": aluno.get_situacao_display() if aluno.situacao else "---",
        "data_emissao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "coordenacao": "COEPI",
        "area_conhecimento": "Ciência da Informação",
        "curso": matricula.curso if matricula and matricula.curso else "---",
        "reconhecimento_renovacao": "Portaria 398/2025 de 29/05/2025 D.O.U. 02/06/2025 pág.41",
        "nome": aluno.nome if aluno.nome else "---",
        "cpf": aluno.CPF if aluno.CPF else "---",
        "nascimento": dtnascimento,
        "identidade": aluno.alunoregistro.identidade or "---",
        "titulo_eleitor": aluno.alunoregistro.titulo_eleitor or "---",
        "pai": aluno.alunoregistro.nome_pai or "---",
        "mae": aluno.alunoregistro.nome_mae or "---",
        "naturalidade": aluno.alunoregistro.naturalidade or "---",
        "nacionalidade": aluno.alunoregistro.nacionalidade or "---",
        "certificado_militar": aluno.alunoregistro.certificado_militar or "---",
        "matricula_numero": matricula.numero_readonly(),
        "inicio": matricula.dtmatricula.strftime("%d/%m/%Y") or "---",
        "regime": "Integral",
        "ingresso": matricula.ingresso or "---",
        "termino": dtconclusao,
        "link_validacao": link_validacao,
        "tabela_disciplinas": gerar_tabela_disciplinas(aluno),
        "qr_code": generate_qrcode_base64(link_validacao),
        "static_root": settings.STATIC_ROOT
    }

    if gerar_pdf:
        import logging
        logger = logging.getLogger('weasyprint')
        logger.addHandler(logging.FileHandler('/tmp/weasyprint.log'))

        html_string = render_to_string("historico_pdf.html", context)
        html = HTML(string=html_string, base_url='')
        pdf = html.write_pdf()
        return HttpResponse(pdf, content_type='application/pdf')

    return render(request, 'historico.html', context)


def historico_validacao(request, hash_matricula):
    hash_list = hash_matricula.split('-')
    titulo = 'Link inválido'
    texto = 'Este link não corresponde a um documento válido'
    if len(hash_list) == 2:
        matricula_id = hash_list[1][1:]
        hash_str = generate_hash(f'{matricula_id}-{settings.SECRET_KEY}')
        if hash_str == hash_list[0]:
            matricula = Matricula.objects.filter(id=matricula_id).first()
            if matricula:
                titulo = "Histórico Escolar Válido!"
                texto = f"Discente: {matricula.pesquisador.nome} / Curso: {matricula.curso}"

    return render(request, 'base_mensagem.html', {'titulo': titulo, 'texto': texto})


@login_required
def declaracao_matricula_pdf(request, matricula_id: int):
    # Busca a matrícula solicitada
    matricula = get_object_or_404(
        Matricula.objects.select_related('pesquisador', 'curso', 'curso__programa'),
        pk=matricula_id
    )

    # ---- Autorização ----
    if not request.user.is_staff:
        aluno_logado = Aluno.objects.filter(user_id=request.user.id).first()
        if not aluno_logado or matricula.pesquisador_id != aluno_logado.id:
            return render(request, 'base_mensagem.html', {
                'titulo': 'Acesso negado',
                'texto': 'Você não tem permissão para emitir esta declaração'
            }, status=403)

        # a matrícula precisa estar ativa
        if getattr(matricula, 'status', None) not in ('A', 'T'):
            return render(request, 'base_mensagem.html', {
                'titulo': 'Matrícula inativa',
                'texto': 'Somente matrículas ativas podem emitir a declaração.'
            }, status=403)

    aluno = matricula.pesquisador

    # ---- Dados do documento ----
    curso_legenda = matricula.curso.descricao
    numero = matricula.numero_readonly()
    if not numero or not numero.startswith(str(matricula.ingresso)):
        return render(request, 'base_mensagem.html', {
            'titulo': 'Acesso negado',
            'texto': 'Você não tem permissão para emitir esta declaração'
        }, status=403)

    contexto = {
        "nome_discente": aluno.nome or "",
        "cpf_discente": getattr(aluno, "CPF", "") or "",
        "curso_legenda": curso_legenda,
        "data_inicio": matricula.dtmatricula,
        "previsao_termino": matricula.dtprevista,
        "data_extenso_hoje": data_por_extenso(date.today()),
        "programa_nome": matricula.curso.programa,
        "numero_matricula": numero,
        "endereco_programa": matricula.curso.programa.endereco,
        "assinatura_nome": matricula.curso.programa.coordenacao.nome,
        "assinatura_cargo": "Coordenação do Programa",
        "static_root": settings.STATIC_ROOT
    }

    # Se for o aluno emitindo, incluir QR de validação (substituirá a assinatura no template)
    validacao = f"{matricula.id}-{settings.SECRET_KEY}"
    link_validacao = f"{settings.SITE_URL}/doc/validacao/{generate_hash(validacao)}-M{matricula.id}"
    contexto.update({
        "link_validacao": link_validacao,
        "qr_code": generate_qrcode_base64(link_validacao),
    })

    # Base URL para assets do template (weasyprint)
    base_url = request.build_absolute_uri('/') if getattr(settings, "DEBUG", False) \
        else getattr(settings, "SITE_URL", request.build_absolute_uri('/'))
    if not base_url.endswith('/'):
        base_url += '/'

    # Render/PDF
    html = render_to_string("declaracao_matricula.html", contexto, request=request)
    pdf = HTML(string=html, base_url='').write_pdf()

    filename = f"declaracao_{matricula_id}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    return resp


@login_required
def solicita_prorrogacao(request):
    tipo_id = request.GET.get("tipo")
    if not tipo_id:
        messages.error(request, "Tipo de Requerimento não informado")
        return redirect("painel_discente")

    tipo_ocorrencia = get_object_or_404(TipoOcorrencia, id=tipo_id)

    aluno = (
        Aluno.objects
        .filter(user_id=request.user.id)
        .select_related("matricula_atual", "matricula_atual__curso")
        .first()
    )
    if not aluno or not aluno.matricula_atual:
        messages.error(request, "Matrícula não encontrada ou incompatível com a solicitação.")
        return redirect("painel_discente")

    matricula = aluno.matricula_atual
    curso = matricula.curso

    # Se for prorrogação de defesa, deve-se verificar se o discente já qualificou
    if tipo_ocorrencia.id == 6 and not matricula.dtquali:
        messages.error(request, "Só é possível solicitar prorrogação de defesa após a qualificação.")
        return redirect("painel_discente")

    if tipo_ocorrencia.id == 7 and matricula.dtquali:
        messages.error(request, "Sua qualificação já ocorreu. Verifique com a secretaria.")
        return redirect("painel_discente")

    # ------------------------------------------------------------------
    # Validação: TipoOcorrencia permitido para o curso
    # ------------------------------------------------------------------
    permitido = TipoOcorrencia.objects.filter(
        id=tipo_ocorrencia.id,
        cursos=curso,
        status=TipoOcorrencia.Status.ATIVO,
    ).exists()
    if not permitido:
        messages.error(request, "Requerimento inválido ou não permitido para seu curso.")
        return redirect("requerimentos")

    try:
        tipo_doc_cronograma = TipoDocumento.objects.get(chave="CRONOGRAMA")
        tipo_doc_historico = TipoDocumento.objects.get(chave="HISTORICO")
    except TipoDocumento.DoesNotExist:
        messages.error(request, "Configuração incompleta: tipos de documento não cadastrados.")
        return redirect("requerimentos")

    # ------------------------------------------------------------------
    # Gravação da solicitação
    # ------------------------------------------------------------------
    if request.method == "POST":
        form = SolicitacaoProrrogacaoForm(request.POST, request.FILES)
        if form.is_valid():
            justificativa = form.cleaned_data["justificativa"]
            comentarios = (form.cleaned_data.get("comentarios_adicionais") or "").strip()
            novo_cronograma_file = form.cleaned_data["novo_cronograma"]
            historico_file = form.cleaned_data["historico"]
            nome_orientador = aluno.nome_orientador
            orientador = aluno.orientador
            # O template da ocorrencia referencia {orientador.nome}; sem orientacao
            # ativa, orientador e None e o format quebraria com AttributeError.
            if not orientador:
                messages.error(
                    request,
                    "Nao ha orientador(a) ativo(a) vinculado(a) a sua matricula. "
                    "Procure a secretaria antes de solicitar a prorrogacao."
                )
                return redirect("painel_discente")

            with (transaction.atomic()):
                # ------------------------------------------------------
                # 3.1) Cria o evento de PRORROGAÇÃO
                # ------------------------------------------------------
                evento = MatriculaEvento.objects.create(
                    matricula=matricula,
                    tipo=tipo_ocorrencia,
                    descricao='',
                    dtevento=timezone.now().date(),
                    justificativa=justificativa,
                    obs=comentarios or None,
                    status=MatriculaEvento.Status.AGUARDANDO_CD,  # 'G' - aguardando aprovação da CD
                )

                # Contexto explicito para o template da ocorrencia e os e-mails.
                # Inclui 'ocorrencia' (o evento ja criado, para {ocorrencia.id}) e
                # 'orientador'. Evita o KeyError que ocorria com format(**locals())
                # quando o template referenciava uma chave ausente no escopo.
                contexto_template = {
                    'aluno': aluno,
                    'matricula': matricula,
                    'curso': curso,
                    'tipo_ocorrencia': tipo_ocorrencia,
                    'ocorrencia': evento,
                    'orientador': orientador,
                    'nome_orientador': nome_orientador,
                    'justificativa': justificativa,
                    'comentarios': comentarios,
                }
                evento.descricao = tipo_ocorrencia.template.format(**contexto_template)
                evento.save(update_fields=['descricao'])

                # ------------------------------------------------------
                # 3.2) Documentos (Generic FK)
                # ------------------------------------------------------
                ct = ContentType.objects.get_for_model(MatriculaEvento)

                Documento.objects.create(
                    tipo=tipo_doc_cronograma,
                    content_type=ct,
                    object_id=evento.id,
                    anexo=novo_cronograma_file,
                )

                Documento.objects.create(
                    tipo=tipo_doc_historico,
                    content_type=ct,
                    object_id=evento.id,
                    anexo=historico_file,
                )

                # ------------------------------------------------------
                # 3.3) Envio de e-mails (após commit)
                # ------------------------------------------------------
                def enviar_emails():
                    # Discente
                    notif_discente = TipoNotificacao.objects.filter(
                        tipo_ocorrencia=tipo_ocorrencia,
                        destinatario=TipoNotificacao.Fluxo.CRIACAO,
                    ).first()
                    if notif_discente:
                        msg_discente = notif_discente.texto.format(**contexto_template)
                        if msg_discente and getattr(aluno, "email", None):
                            sendmail(
                                "Solicitação registrada",
                                [aluno.email],
                                message=msg_discente,
                                thread=True,
                            )

                    # Orientador
                    notif_orientador = TipoNotificacao.objects.filter(
                            tipo_ocorrencia=tipo_ocorrencia,
                            destinatario=TipoNotificacao.Fluxo.ORIENTADOR).first()
                    if notif_orientador:
                        if aluno.orientador:
                            if getattr(aluno.orientador, "email", None):
                                msg_orientador = notif_orientador.texto.format(**contexto_template)
                                sendmail(
                                        "Nova solicitação registrada",
                                        [aluno.orientador.email,],
                                        message=msg_orientador,
                                        thread=True,
                                    )
                            else:
                                notificacao_orientador_sem_email(curso, aluno.orientador)

                transaction.on_commit(enviar_emails)

            messages.success(request, "Solicitação registrada com sucesso.")
            return redirect("painel_discente")

        else:
            messages.error(request, "Revise os campos obrigatórios antes de enviar.")
    else:
        form = SolicitacaoProrrogacaoForm()

    # ------------------------------------------------------------------
    # GET — renderização do formulário
    # ------------------------------------------------------------------
    return render(request, "solicita_prorrogacao.html", {
        "form": form,
        "tipo_ocorrencia": tipo_ocorrencia,
        "aluno": aluno,
        "matricula": matricula,
        "curso": curso,
    })


@login_required
def solicita_trancamento(request):
    aluno = (
        Aluno.objects
        .filter(user_id=request.user.id)
        .select_related("matricula_atual", "matricula_atual__curso")
        .first()
    )
    if not aluno or not aluno.matricula_atual:
        messages.error(request, "Matrícula não encontrada ou incompatível com a solicitação.")
        return redirect("painel_discente")

    matricula = aluno.matricula_atual
    curso = matricula.curso

    tipo_ocorrencia = TipoOcorrencia.objects.filter(id=8,status=TipoOcorrencia.Status.ATIVO,cursos=curso).first()
    if not tipo_ocorrencia:
        messages.error(request, "Requerimento de trancamento não configurado para o seu curso.")
        return redirect("painel_discente")

    try:
        tipo_doc_historico = TipoDocumento.objects.get(chave="HISTORICO")
    except TipoDocumento.DoesNotExist:
        messages.error(
            request,
            "Configuração incompleta: tipo de documento HISTORICO não cadastrado."
        )
        return redirect("painel_discente")

    if request.method == "POST":
        form = SolicitacaoTrancamentoForm(request.POST, request.FILES)
        if form.is_valid():
            justificativa = form.cleaned_data["justificativa"]
            comentarios = (form.cleaned_data.get("comentarios_adicionais") or "").strip()
            historico_file = form.cleaned_data["historico"]

            # O template da ocorrencia usa {orientador.nome}; orientador e obrigatorio.
            orientador = aluno.orientador
            if not orientador:
                messages.error(
                    request,
                    "Nao ha orientador(a) ativo(a) vinculado(a) a sua matricula. "
                    "Procure a secretaria antes de solicitar o trancamento."
                )
                return redirect("painel_discente")

            with transaction.atomic():
                evento = MatriculaEvento.objects.create(
                    matricula=matricula,
                    tipo=tipo_ocorrencia,
                    descricao='',
                    dtevento=timezone.now().date(),
                    justificativa=justificativa,
                    obs=comentarios or None,
                    status=MatriculaEvento.Status.AGUARDANDO_CD,
                )

                # Contexto explicito (inclui 'ocorrencia' e 'orientador') para o
                # template e os e-mails; descricao gerada apos criar o evento.
                contexto_template = {
                    'aluno': aluno,
                    'matricula': matricula,
                    'curso': curso,
                    'tipo_ocorrencia': tipo_ocorrencia,
                    'ocorrencia': evento,
                    'orientador': orientador,
                    'justificativa': justificativa,
                    'comentarios': comentarios,
                }
                evento.descricao = tipo_ocorrencia.template.format(**contexto_template)
                evento.save(update_fields=['descricao'])

                ct = ContentType.objects.get_for_model(MatriculaEvento)
                Documento.objects.create(
                    tipo=tipo_doc_historico,
                    content_type=ct,
                    object_id=evento.id,
                    anexo=historico_file,
                )

                def enviar_emails():
                    # Discente
                    notif_discente = TipoNotificacao.objects.filter(
                        tipo_ocorrencia=tipo_ocorrencia,
                        destinatario=TipoNotificacao.Fluxo.CRIACAO,
                    ).first()
                    if notif_discente:
                        msg_discente = notif_discente.texto.format(**contexto_template)
                        if getattr(aluno, "email", None):
                            sendmail(
                                "Solicitação registrada",
                                [aluno.email],
                                message=msg_discente,
                                thread=True,
                            )

                    # Orientador
                    orientador = getattr(aluno, "orientador", None)
                    if orientador:
                        notif_orientador = TipoNotificacao.objects.filter(
                            tipo_ocorrencia=tipo_ocorrencia,
                            destinatario=TipoNotificacao.Fluxo.ORIENTADOR,
                        ).first()
                        if notif_orientador:
                            msg_orientador = notif_orientador.texto.format(**contexto_template)
                            if getattr(orientador, "email", None):
                                sendmail(
                                    f"{tipo_ocorrencia.descricao}",
                                    [orientador.email],
                                    message=msg_orientador,
                                    thread=True,
                                )
                        else:
                            notificacao_orientador_sem_email(curso, aluno.orientador)

                transaction.on_commit(enviar_emails)

            messages.success(request, "Solicitação registrada com sucesso.")
            return redirect("painel_discente")
        else:
            messages.error(request, "Preencha os campos obrigatórios antes de enviar.")
    else:
        form = SolicitacaoTrancamentoForm()

    return render(
        request,
        "solicita_trancamento.html",
        {"form": form, "aluno": aluno, "matricula": matricula, "curso": curso},
    )


@login_required
def solicita_reativacao(request):
    aluno = (
        Aluno.objects
        .filter(user_id=request.user.id)
        .select_related("matricula_atual", "matricula_atual__curso")
        .first()
    )
    if not aluno or not aluno.matricula_atual:
        messages.error(request, "Matrícula não encontrada ou incompatível com a solicitação.")
        return redirect("painel_discente")

    matricula = aluno.matricula_atual
    curso = matricula.curso

    if matricula.status != 'T':
        messages.error(request, "A sua matrícula não está trancada. Dessa forma não necessita de reativação.")
        return redirect("painel_discente")

    tipo_ocorrencia = TipoOcorrencia.objects.filter(id=10,status=TipoOcorrencia.Status.ATIVO,cursos=curso).first()
    if not tipo_ocorrencia:
        messages.error(request, "Requerimento não configurado para o seu curso.")
        return redirect("painel_discente")

    try:
        tipo_doc_historico = TipoDocumento.objects.get(chave="HISTORICO")
    except TipoDocumento.DoesNotExist:
        messages.error(
            request,
            "Configuração incompleta: tipo de documento HISTORICO não cadastrado."
        )
        return redirect("painel_discente")

    if request.method == "POST":
        form = SolicitacaoReativacaoForm(request.POST, request.FILES)
        if form.is_valid():
            comentarios = (form.cleaned_data.get("justificativa") or "").strip()

            # O template da ocorrencia usa {orientador.nome}; orientador e obrigatorio.
            orientador = aluno.orientador
            if not orientador:
                messages.error(
                    request,
                    "Nao ha orientador(a) ativo(a) vinculado(a) a sua matricula. "
                    "Procure a secretaria antes de solicitar a reativacao."
                )
                return redirect("painel_discente")

            with transaction.atomic():
                evento = MatriculaEvento.objects.create(
                    matricula=matricula,
                    tipo=tipo_ocorrencia,
                    descricao='',
                    dtevento=timezone.now().date(),
                    obs=comentarios or None,
                    status=MatriculaEvento.Status.AGUARDANDO_CD,
                )

                # Contexto explicito (inclui 'ocorrencia' e 'orientador') para o
                # template e os e-mails; descricao gerada apos criar o evento.
                contexto_template = {
                    'aluno': aluno,
                    'matricula': matricula,
                    'curso': curso,
                    'tipo_ocorrencia': tipo_ocorrencia,
                    'ocorrencia': evento,
                    'orientador': orientador,
                    'comentarios': comentarios,
                }
                evento.descricao = tipo_ocorrencia.template.format(**contexto_template)
                evento.save(update_fields=['descricao'])

                def enviar_emails():
                    # Discente
                    notif_discente = TipoNotificacao.objects.filter(
                        tipo_ocorrencia=tipo_ocorrencia,
                        destinatario=TipoNotificacao.Fluxo.CRIACAO,
                    ).first()
                    if notif_discente:
                        msg_discente = notif_discente.texto.format(**contexto_template)
                        if getattr(aluno, "email", None):
                            sendmail(
                                "Solicitação registrada",
                                [aluno.email],
                                message=msg_discente,
                                thread=True,
                            )

                    # Orientador
                    orientador = getattr(aluno, "orientador", None)
                    if orientador:
                        notif_orientador = TipoNotificacao.objects.filter(
                            tipo_ocorrencia=tipo_ocorrencia,
                            destinatario=TipoNotificacao.Fluxo.ORIENTADOR,
                        ).first()
                        if notif_orientador:
                            msg_orientador = notif_orientador.texto.format(**contexto_template)
                            if getattr(orientador, "email", None):
                                sendmail(
                                    f"{tipo_ocorrencia.descricao}",
                                    [orientador.email],
                                    message=msg_orientador,
                                    thread=True,
                                )
                        else:
                            notificacao_orientador_sem_email(curso, aluno.orientador)

                transaction.on_commit(enviar_emails)

            messages.success(request, "Solicitação registrada com sucesso.")
            return redirect("painel_discente")
        else:
            messages.error(request, "Preencha os campos obrigatórios antes de enviar.")
    else:
        form = SolicitacaoReativacaoForm()

    return render(
        request,
        "solicita_reativacao.html",
        {"form": form, "aluno": aluno, "matricula": matricula, "curso": curso},
    )


@login_required
def bancas_docente(request):
    # Apenas docentes do programa acessam a lista de bancas; membros externos
    # (pesquisadores sem vínculo de programa) não têm acesso.
    professor = Professor.objects.filter(user=request.user).first()
    if not professor:
        return render(
            request, 'base_mensagem.html',
            {'titulo': 'Acesso Negado',
             'texto': 'Esta função deve ser utilizada apenas para as/os docentes do programa'}
        )

    bancas = []
    for evento in MatriculaEvento.objects.filter(
            tipo__in=(2, 3, 4, 5),
            matriculaeventopesquisador__pesquisador=professor).order_by('dtevento'):
        bancas.append({
            "tipo": evento.tipo.descricao,
            "discente": evento.matricula.pesquisador,
            "dt": evento.dtevento,
        })
    return render(
        request,
        'bancas_docente.html',
        {'bancas': bancas}
    )


NUM_COLUNAS_PRESENCA = 15


@login_required
def diario_de_classe(request, turma_id):
    turma = get_object_or_404(Turma.objects.select_related('periodo', 'disciplina'), pk=turma_id)
    # Um professor só enxerga a pauta das próprias turmas.
    # Staff/admin (secretaria) acessa se tiver permissão de alteração
    # ou visualização de Turma no admin.
    eh_professor_da_turma = turma.turmaprofessor_set.filter(professor__user=request.user).exists()
    tem_acesso_admin = request.user.is_staff and (
            request.user.has_perm('nucleo.change_turma')
            or request.user.has_perm('nucleo.view_turma')
    )
    if not eh_professor_da_turma and not tem_acesso_admin:
        raise PermissionDenied

    # Nome da instituição a partir do primeiro curso associado à turma.
    turmacurso = turma.turmacurso_set.select_related('curso__programa__instituicao').first()
    if turmacurso:
        nome_instituicao = turmacurso.curso.programa.instituicao.nome
    else:
        nome_instituicao = 'Nenhum curso associado à Turma'
    # Todas as inscrições da turma (inclusive trancados/abandono/etc.),
    # ordenadas por nome do aluno. Alunos externos não têm matrícula.
    inscricoes = (
        turma.inscricao_set.exclude(status=Inscricao.Status.DISPENSA)
        .select_related('aluno', 'matricula__curso', 'matricula__pesquisador')
        .order_by('aluno__nome')
        .iterator()
    )

    def gera_linhas():
        for i, insc in enumerate(inscricoes, start=1):
            if insc.matricula:
                curso = insc.matricula.curso.descricao
                numero = insc.matricula.numero_readonly()
            else:
                curso = 'Externo'
                numero = ''

            if insc.status == Inscricao.Status.MATRICULADO:
                nome = insc.aluno.nome
            else:
                nome = f'{insc.aluno.nome} ({insc.get_status_display()})'

            yield {
                'seq': i,
                'curso': curso,
                'numero': numero,
                'nome': nome,
                'email': insc.aluno.email or '',
            }

    periodo = turma.periodo
    periodo_texto = (
        f'{periodo.ident}°. {periodo.get_tipo_periodo_display().lower()}-{periodo.ano}'
    )

    contexto = {
        'nome_instituicao': nome_instituicao,
        'disciplina': (
            f'{turma.disciplina.codigo} - {turma.disciplina.titulo} — {periodo_texto}'
        ),
        'docentes': turma.docentes(),
        'linhas': gera_linhas(),
        'colunas_presenca': range(1, NUM_COLUNAS_PRESENCA + 1),
    }

    html = render_to_string('diario_de_classe.html', contexto, request=request)
    pdf = HTML(string=html, base_url='').write_pdf()

    disposition = 'attachment' if request.GET.get('download') else 'inline'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'{disposition}; filename="diario_de_classe_{turma.id}.pdf"'
    return response


@login_required
def turma_avaliacao(request, turma_id):
    # Acesso restrito ao professor da turma, autenticado. Não há mais acesso por
    # hash nem fluxo de solicitação de links por e-mail.
    turma = get_object_or_404(Turma, id=turma_id)

    eh_professor_da_turma = turma.turmaprofessor_set.filter(professor__user=request.user).exists()
    if not eh_professor_da_turma:
        return render(
            request, 'base_mensagem.html',
            {'titulo': 'Acesso Negado',
             'texto': 'Esta função deve ser utilizada apenas pelos docentes da turma'}
        )

    inscricoes = list(
        Inscricao.objects
        .filter(turma=turma, status__in=(Inscricao.Status.MATRICULADO, Inscricao.Status.APROVADO,
                                         Inscricao.Status.REPROVADO, Inscricao.Status.REP_FALTA))
        .select_related('aluno', 'aluno__matricula_atual', 'aluno__matricula_atual__curso')
        .order_by('aluno__nome', 'id')
    )
    FormSet = formset_factory(TurmaAvaliacaoItemForm, extra=0)
    conceitos_validos = {valor for valor, _ in TurmaAvaliacaoItemForm.CONCEITOS}
    initial = [
        {
            'inscricao_id': inscricao.id,
            'conceito': inscricao.conceito if inscricao.conceito in conceitos_validos else None,
        }
        for inscricao in inscricoes
    ]
    inscricoes_por_id = {inscricao.id: inscricao for inscricao in inscricoes}

    def _get_inscricao_id(form):
        valor = form['inscricao_id'].value()
        try:
            return int(valor) if valor is not None and str(valor).strip() != '' else None
        except (TypeError, ValueError):
            return None

    if request.method == 'POST':
        formset = FormSet(request.POST, initial=initial)
        if formset.is_valid():
            for form in formset:
                inscricao_id = form.cleaned_data['inscricao_id']
                conceito = form.cleaned_data['conceito']
                inscricao = inscricoes_por_id.get(inscricao_id)
                if inscricao:
                    inscricao.conceito = conceito
                    inscricao.save(update_fields=['conceito', 'status'])
                    log_object(inscricao, f'Conceito {conceito} atribuído pelo professor')
            messages.info(request, 'Avaliações salvas com sucesso.')
        items = [
            {'form': form, 'inscricao': inscricoes_por_id.get(_get_inscricao_id(form))}
            for form in formset.forms
        ]
    else:
        formset = FormSet(initial=initial)
        items = [
            {'form': form, 'inscricao': inscricoes_por_id.get(_get_inscricao_id(form))}
            for form in formset.forms
        ]

    return render(
        request,
        'turma_avaliacao.html',
        {
            'turma': turma,
            'formset': formset,
            'items': items,
        }
    )


class EditDadosView(UpdateView):
    """
    View base para editar dados de aluno ou professor.
    As views que são herança desta classe devem declarar:
    model
    form_class
    success_url
    pk_url_kwarg
    hash_url_kwarg
    """
    template_name = 'edit_dados.html'
    is_first_access = True
    hash_url_kwarg = None

    def _get_instancia_autorizada(self, request):
        object_id = self.kwargs.get(self.pk_url_kwarg)
        object_hash = self.kwargs.get(self.hash_url_kwarg)
        # Quando o usuário está logado, o object_id é igual o user.pk do django e
        # retorna a instância com base em user_id.
        if request.user.is_authenticated:
            if request.user.pk == object_id or request.user.is_superuser:
                return get_object_or_404(self.model, user__id=object_id), False
            return None, None

        if validate_24hash(str(object_id), object_hash):
            return get_object_or_404(self.model, pk=object_id), True

        return None, None

    def dispatch(self, request, *args, **kwargs):
        self.object, self.is_first_access = self._get_instancia_autorizada(request)

        if not self.object:
            return redirect('login')

        if not self.object.cadastro_valido():
            messages.warning(
                request,
                'Seu cadastro ainda não está completo. Aguarde a data de início de matrícula para acessar o sistema.'
            )
            return redirect('login')

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['is_first_access'] = self.is_first_access
        return kwargs

    def get_object(self, queryset=...):
        return self.object

    def form_valid(self, form):
        obj = form.save()

        # Se for primeiro acesso, autenticar o usuário
        if form.is_first_access:
            username = obj.get_auth_username()
            senha = form.cleaned_data.get('password')
            user = authenticate(self.request, username=username, password=senha)

            if user is not None:
                login(self.request, user)
                messages.success(self.request, 'Dados cadastrados com sucesso.')
                return redirect(self.get_success_url())
            else:
                # Isto estava na view original, estranho mensagem de erro e depois redirecionar para o painel...
                messages.error(self.request, 'Credenciais inválidas. Tente novamente.')

        messages.success(self.request, 'Dados atualizados com sucesso.')
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, 'Erro ao atualizar os dados. Verifique o formulário.')
        return super().form_invalid(form)


class EditAlunoView(EditDadosView):
    """View para editar dados do aluno"""
    model = Aluno
    form_class = EditAlunoForm
    success_url = 'painel_discente'
    pk_url_kwarg = 'aluno_id'
    hash_url_kwarg = 'aluno_hash'


class EditProfessorView(EditDadosView):
    """View para editar dados do professor"""
    model = Professor
    form_class = EditProfessorForm
    success_url = 'painel_docente'
    pk_url_kwarg = 'professor_id'
    hash_url_kwarg = 'professor_hash'
