import base64
import json
import logging
import secrets
import smtplib
import threading
import time
from http import HTTPStatus
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.mail import get_connection, EmailMultiAlternatives
from django.db.models import Count
from django.db.models import F
from django.http import HttpResponse, HttpResponseRedirect, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from qrcode.constants import *
from qrcode.main import QRCode

from nucleo.apps import log_object, generate_hash

# Log separado das falhas de integracao com o Moodle, para reprocessamento.
# Registra a URL de confirmacao original e os dados do discente afetado.
moodle_falhas_logger = logging.getLogger('moodle_falhas')
if not moodle_falhas_logger.handlers:
    import os as _os
    _log_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'logs')
    _fh = logging.FileHandler(_os.path.join(_log_dir, 'moodle_falhas.log'))
    _fh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    moodle_falhas_logger.addHandler(_fh)
    moodle_falhas_logger.setLevel(logging.INFO)
from nucleo.models import Pesquisador
from nucleo.models import STATUS_ATIVO
from utils.email import sendmail
from utils.stdlib import get_display_str
from .forms import (InscricaoCursoForm, VerificarEmailForm, FormConsentimento, render_origem_options, DiscenteForm,
                    ConfirmaPresencaForm, SessaoSearchForm, AgendaForm)
from .models import (Modulo, Curso, CursoFormal, Inscricao, Contato, Discente, CursoDocente, Comunicado, Docente,
                     PalavraChave, ListaInteresse, ModuloSessao, TipoCurso)

from .interfaces import registro_moodle


def api_modulos(request):
    modulos = []
    for modulo in Modulo.objects.exclude(slug__isnull=True):
        if modulo.imagem:
            imagem_url = settings.SITE_URL + modulo.imagem.url
        else:
            imagem_url = ''
        modulos.append({'nome': modulo.nome, 'id': modulo.id,
                        'url': f'/modulo/{modulo.slug}',
                        'image': imagem_url
                        }
                       )
    return HttpResponse(json.dumps(modulos), content_type='application/json')


# source: False retorna um dicionário / True: retorna um JSON
def api_curso(request, curso_id, source=False):
    curso = get_object_or_404(Curso, pk=curso_id)
    curso_record = {
        'id': curso.id,
        'nome': curso.nome,
        'meta': curso.tipo.meta,
        'modulo': curso.modulo.id if curso.modulo else None,
        'modulo_nome': curso.modulo.nome if curso.modulo else None,
        'docentes': curso.lista_docentes(),
        'dt_inicio': curso.dt_inicio.strftime('%d/%m' if source else "%Y-%m-%d"),
        'imagem': curso.imagem_url(),
        'banner': curso.banner_url(),
        'ementa': curso.ementa,
        'programacao': curso.programacao,
        'status': curso.status,
        'status_matricula': curso.status_matricula(),
        'categorias': curso.categorias(),
        'header': curso.header,
        'periodo': curso.periodo,
        'url_inscricao': curso.external_url(),
    }
    if source:
        return curso_record
    else:
        return HttpResponse(json.dumps(curso_record), content_type='application/json')


def docentes_ativos(request, source=False):
    docentes = []
    for docente in Docente.objects.filter(pesquisadorinstituicao__status=STATUS_ATIVO).order_by('nome'):
        docentes.append({
            'id': docente.id,
            'nome': docente.nome,
            'url_foto': docente.fotografia_url(),
            'mini_bio': docente.mini_bio
        })

    if source:
        return docentes
    else:
        return HttpResponse(json.dumps(docentes), content_type='application/json')


def docente(request, docente_id):
    registro = Docente.objects.filter(id=docente_id)[0]
    if not registro:
        result = {}
    else:
        lista_cursos = []
        for curso in registro.cursodocente_set.all():
            lista_cursos.append(curso.curso.nome)

        result = {
            'id': registro.id,
            'nome': registro.nome,
            'url_foto': registro.fotografia_url(),
            'id_cnpq': registro.id_cnpq,
            'mini_bio': registro.mini_bio,
            'cursos': lista_cursos
        }

    return HttpResponse(json.dumps(result), content_type='application/json')


def curso_dict(curso):
    return {'nome': curso.nome, 'id': curso.id,
            'docentes': curso.lista_docentes(),
            'dt_inicio': curso.dt_inicio.strftime("%Y-%m-%d"),
            'imagem': curso.imagem_url(),
            'imagem_url': curso.imagem_url(),
            'banner_url': curso.banner_url(),
            'url': curso.external_url(),
            'categorias': curso.categorias()}


def api_cursos_fechados(request):
    cursos = []
    for curso in CursoFormal.objects.filter(status=Curso.Status.FINALIZADO,
                                            tipo__publico=True, tipo__evento=False).order_by('-dt_inicio'):
        cursos.append(curso_dict(curso))
    return HttpResponse(json.dumps(cursos), content_type='application/json')


def api_cursos_abertos(request, source=False):
    cursos = []
    for curso in Curso.objects.filter(status=Curso.Status.ATIVO,
                                      tipo__publico=True, tipo__evento=False, tipo__meta=False).order_by('-dt_inicio'):
        cursos.append(curso_dict(curso))
    if source:
        return cursos
    else:
        return HttpResponse(json.dumps(cursos), content_type='application/json')


def cursos(request):
    cursos = api_cursos_abertos(request, source=True)
    if len(cursos) > 0:
        mensagem = 'Cursos com matrículas abertas'
        historico = None
    else:
        mensagem = 'Nenhum curso com matrículas abertas'
        historico = '/cursos_historico'
    return render(request, 'cursos.html', {'cursos': cursos,
                                           'titulo': mensagem,
                                           'historico': historico})


def eventos(request):
    cursos = []
    for curso in Curso.objects.filter(tipo__publico=True,
                                      tipo__evento=True,
                                      tipo__meta=False).exclude(status=Curso.Status.EM_EDICAO).order_by('-dt_inicio'):
        cursos.append(curso_dict(curso))
    return render(request, 'cursos.html', {'cursos': cursos, 'titulo': 'Eventos atuais'})


def cursos_historico(request):
    cursos = []
    for curso in CursoFormal.objects.filter(status=Curso.Status.FINALIZADO, tipo__publico=True, tipo__meta=False,
                                            tipo__evento=False).order_by('-dt_inicio'):
        cursos.append(curso_dict(curso))
    return render(request, 'cursos.html', {'cursos': cursos, 'titulo': 'Histórico de Cursos Realizados'})


def curso(request, curso_id):
    curso = api_curso(request, curso_id, True)
    if curso['meta']:
        modulo = Modulo.objects.get(id=curso['modulo'])
        return evento(request, modulo.slug)

    if curso['status'] == 'A':
        link = f'/inscricao/{curso_id}'
    else:
        link = None
    docentes = []
    for record in CursoDocente.objects.filter(curso=curso_id):
        docentes.append({'nome': record.docente.nome, 'mini_bio': record.docente.mini_bio})
    return render(request, 'curso.html',
                  {'curso': curso,
                   'docentes': docentes,
                   'link': link})


def modulo(request, slug):
    template_name = 'modulo.html'
    cursos = []
    modulo = Modulo.objects.filter(slug=slug).first()

    utm_source = request.COOKIES.get('utm_source')
    if request.method == 'GET' and not utm_source:
        utm_source = request.GET.get('utm_source')

    if not modulo:
        return render(request, 'base_escola.html',
                      {'titulo': f"Módulo não encontrado",
                       'mensagem': "Verifique se a URL digitada está correta!"})

    for curso in Curso.objects.filter(status__in=(Curso.Status.ATIVO, Curso.Status.FINALIZADO), modulo=modulo).order_by(
            'cod_externo'):
        cursos.append({'nome': curso.nome, 'cod_externo': curso.cod_externo, 'docentes': curso.lista_docentes(),
                       'status_matricula': curso.status_matricula,
                       'url': curso.external_url()
                       })

    response = render(request, template_name, {'modulo': modulo, 'cursos': cursos})
    if utm_source:
        response.set_cookie('utm_source', utm_source, max_age=15 * 60)
    return response


def evento(request, slug):
    curso = Curso.objects.filter(slug=slug).first()
    if not curso or not curso.modulo:
        return render(request, 'base_escola.html',
                      {'titulo': f"Evento não encontrado",
                       'mensagem': "Verifique se a URL digitada está correta!"})

    if curso.slug and curso.modulo.url_tema:
        template_name = f'{curso.slug}/index.html'
    else:
        return modulo(request, slug)

    utm_source = request.COOKIES.get('utm_source')
    if request.method == 'GET' and not utm_source:
        utm_source = request.GET.get('utm_source')

    link = f'/inscricao/{curso.id}'
    if curso.status == Curso.Status.FINALIZADO:
        mensagem_inscricao = 'Evento Finalizado'
        link = None
    elif curso.tot_alunos() >= curso.num_max_alunos:
        mensagem_inscricao = 'O evento já está com lotação máxima! Mas você ainda pode se inscrever na lista de espera!'
    elif curso.inscricao_set.all().count() > curso.num_max_alunos:
        mensagem_inscricao = 'Últimas vagas!'
    else:
        mensagem_inscricao = None

    docentes = []
    for record in CursoDocente.objects.filter(curso_id=curso.id).order_by('ordem', 'docente__nome'):
        if record.docente.fotografia:
            foto = record.docente.fotografia.url
        else:
            foto = None
        docentes.append({'nome': record.docente.nome,
                         'foto': foto,
                         'mini_bio': record.docente.mini_bio})

    response = render(request, template_name,
                      {'curso': curso,
                       'docentes': docentes,
                       'mensagem_inscricao': mensagem_inscricao,
                       'link': link})

    if utm_source:
        response.set_cookie('utm_source', utm_source, max_age=15 * 60)

    return response


def sessions(request, slug, token=None):
    obj = Modulo.objects.filter(slug=slug).first()
    if not obj:
        return render(request, 'base_escola.html',
                      {'titulo': f"Evento não encontrado",
                       'mensagem': "Verifique se a URL digitada está correta!"})

    template_name = f'{obj.slug}/index.html'

    cookie = token

    if not cookie:
        cookie = request.COOKIES.get('cookie', secrets.token_hex(32))

    form = SessaoSearchForm(modulo=obj, data=request.GET)
    form.is_valid()

    search_kwargs = {
        'trilha__modulo__pk': obj.pk,
        'contatoagenda__cookie': token,
        **form.cleaned_data
    }

    qs = ModuloSessao.objects.select_related('trilha__modulo').annotate_agenda(cookie).busca(**search_kwargs)

    response = render(
        request, template_name, {'modulo': obj, 'sessoes': qs, 'form': form,
                                 'busca': form.cleaned_data['sessao_trabalho'].lower(),
                                 'current_cookie_value': cookie}
    )

    if cookie:
        response.set_cookie('cookie', cookie, max_age=15 * 60)

    return response


def agenda_certificado(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    if curso.status == Curso.Status.FINALIZADO:
        curso.envio_certificado = 'A'
        curso.save()
        log_object(curso, 'Emissão dos certificados agendada')
        messages.info(request, 'A emissão do certificado foi agendada com sucesso')
    else:
        messages.error(request, 'O curso deve estar finalizado')
    return HttpResponseRedirect(reverse('admin:escola_curso_change', args=(curso_id,)))


def agenda_certificado_lista(request, lista_id):
    lista = get_object_or_404(ListaInteresse, id=lista_id)
    lista.status_envio = 'A'
    lista.save()
    log_object(lista, 'Emissão dos certificados agendada')
    messages.info(request, 'A emissão do certificado foi agendada com sucesso')
    return HttpResponseRedirect(reverse('admin:escola_listainteresse_change', args=(lista_id,)))


def obtem_discente(email):
    discente = Discente.objects.filter(email=email).first()
    pesquisador = Pesquisador.objects.filter(email=email).first()
    if pesquisador and not discente:
        discente = Discente(email=pesquisador.email, nome=pesquisador.nome,
                            sexo=pesquisador.sexo, orcid=pesquisador.orcid, id_cnpq=pesquisador.id_cnpq,
                            validado=True)
        discente.save()
        contato = Contato(discente=discente, origem='PPGCI', email=email)
        contato.save()
    return discente


def get_template_name(curso: Curso, template_base: str = 'base_escola.html') -> str:
    result = None
    if curso and curso.slug:
        try:
            template_name = f'{curso.slug}/{template_base}'
            get_template(template_name)
            return template_name
        except TemplateDoesNotExist:
            result = None

    if not result:
        return template_base


def teste_template(request, curso_id):
    curso = get_object_or_404(Curso, id=curso_id)
    template_name = get_template_name(curso)
    return render(request,
                  template_name,
                  {'titulo': "Titulo",
                   'mensagem': 'Teste da Mensagem'})


def confirmar_email(request, curso, discente):
    inscricao, mensagem = Inscricao.inscrever(curso, discente)
    if not mensagem:
        mensagem = "Para que você possa confirmar a sua identidade, acesse o seu email e clique no link enviado"
        inscricao.send_email_verificacao()

    template_name = get_template_name(curso)

    return render(request,
                  template_name,
                  {'titulo': "Acesse o seu email para continuar a inscrição", 'mensagem': mensagem})


def inicia_inscricao(request, curso_id):
    curso = Curso.objects.filter(pk=curso_id).first()
    if not curso:
        return render(request, 'base_escola.html',
                      {'titulo': f"Evento/Curso Inexistente",
                       'mensagem': "Retorne a tela de cursos para realizar nova escolha"})

    template_name = get_template_name(curso)

    if curso.status != 'A':
        if curso.status == 'E':
            mensagem = 'As inscrições ainda não estão habilitadas'
        else:
            mensagem = 'Infelizmente as inscrições já se encerraram!'

        return render(request, template_name,
                      {'titulo': curso.nome,
                       'mensagem': mensagem})

    if curso.num_max_alunos > 0 and curso.tot_alunos() >= curso.num_max_alunos:
        mensagem_extra = 'O evento/curso já está lotado. Você está se inscrevendo na lista de espera.'
    else:
        mensagem_extra = None

    cookie_ativo = request.COOKIES.get('CONFIRMED')
    if cookie_ativo:
        id_str = cookie_ativo.split('-')[0]
        # recupera a inscrição que gerou o cookie para obter os dados do discente
        inscricao_anterior = Inscricao.objects.filter(id=id_str).first()
        # se o cookie for válido, tentar realizar a inscrição
        if inscricao_anterior and cookie_ativo == inscricao_anterior.hash_confirmacao():
            inscricao, mensagem = Inscricao.inscrever(curso, inscricao_anterior.discente, True)
            if not mensagem:
                inscricao.email_confirmacao()
            response = render(request, 'base_escola.html',
                              {'titulo': f"{curso.nome}", 'mensagem': mensagem })
            # renova o cookie em +10 minutos
            response.set_cookie('CONFIRMED', cookie_ativo, max_age=10 * 60)
            return response

    template_name = get_template_name(curso, 'verifica_email_inscricao.html')
    form_verificar_email = VerificarEmailForm(request.POST or None)

    utm_source = request.COOKIES.get('utm_source')
    if not utm_source and request.method == 'GET':
        utm_source = request.GET.get('utm_source')

    if request.method == 'POST':
        if not form_verificar_email.is_valid():
            return render(request, template_name,
                          {'form_verificar_email': form_verificar_email,
                           'titulo': curso.nome,
                           'descricao': 'Email inválido'})

        email = form_verificar_email.cleaned_data['email']

        discente = obtem_discente(email)
        if discente and (discente.cpf or discente.orcid):
            return confirmar_email(request, curso, discente)
        else:
            if discente:
                contato = discente.contato
            else:
                contato = None

            if not contato:
                contato = Contato(email=email, utm_source=utm_source, curso_origem=curso)
                contato.save()
                if discente:
                    discente.contato = contato
                    discente.save()

            return redirect('tela_consentimento', curso_id, contato.id)

    response = render(request, template_name,
                      {'form_verificar_email': form_verificar_email,
                       'titulo': curso.nome,
                       'curso': curso,
                       'mensagem_extra': mensagem_extra})
    if utm_source:
        response.set_cookie('utm_source', utm_source, max_age=15 * 60)

    return response


def tela_consentimento(request, contato_id, curso_id):
    curso = Curso.objects.filter(pk=curso_id).first()
    contato = Contato.objects.filter(pk=contato_id).first()

    if not curso:
        return render(request, 'base_escola.html',
                      {'titulo': f"Evento/Curso Inexistente",
                       'mensagem': "Retorne a tela de cursos para realizar nova escolha"})

    template_name = get_template_name(curso)

    if curso.status != 'A':
        return render(request, template_name,
                      {'titulo': f"{curso.nome}",
                       'mensagem': "Infelizmente as inscrições já se encerraram!"})

    if not contato:
        return render(request, template_name,
                      {'titulo': f"Contato não encontrado",
                       'mensagem': "Retorne a tela de cursos para reiniciar o processo"})

    form = FormConsentimento(request.POST or None)
    template_name = get_template_name(curso, 'verifica_email_inscricao.html')

    if request.method == 'POST':
        if not form.is_valid():
            return render(request, template_name,
                          {'form_verificar_email': form, 'curso': curso})
        origem = form.cleaned_data['origem']
        contato.origem = contato.origem or origem
        contato.utm_source = contato.utm_source or request.COOKIES.get('utm_source')
        contato.save()
        log_object(contato,'Consentimento ')
        return redirect(reverse('cadastra_discente', args=(contato.hash_key(), curso_id)))

    return render(request, template_name,
                  {'form_verificar_email': form,
                   'curso': curso,
                   'render_datalist': render_origem_options})


def default_buttons(contato):
    buttons = [{'url': '/discente/' + contato.hash_key(), 'caption': 'Atualizar Cadastro'},
               {'url': '/inscricao_logout/', 'caption': 'Finalizar'}, ]
    return buttons


def cadastra_discente(request, hash_auth, curso_id=None):
    try:
        id_str = hash_auth.split('-')[0]
        contato = get_object_or_404(Contato, id=id_str)
        if contato.hash_key() != hash_auth:
            raise Http404
    except Http404:
        titulo = 'Erro no processamento'
        mensagem = 'Autenticação inválida'
        return render(request, 'base_escola.html', {'titulo': titulo, 'mensagem': mensagem})

    if curso_id:
        curso = Curso.objects.filter(id=curso_id, tipo__meta=False).select_related('tipo').first()
        if not curso:
            return render(request, 'base_escola.html',
                          {'titulo': 'Curso não encontrado',
                           'mensagem': 'Algo deu errado, retorne a escolha dos cursos para realizar nova seleção'})
    else:
        curso = None

    mensagem = None
    template_name = get_template_name(curso, 'inscricao.html')

    discente = Discente.objects.filter(contato=contato).first()
    if not discente:
        discente = Discente.objects.filter(email=contato.email).first()
        if not discente:
            discente = Discente(email=contato.email, contato=contato)

    form_inscricao = DiscenteForm(instance=discente)
    if request.method == 'POST':
        form_inscricao = DiscenteForm(request.POST, instance=discente)

        if form_inscricao.is_valid():
            discente = form_inscricao.save()
            # Atualiza qualquer informação adicional, se necessário
            discente.save()
            contato.nome = discente.nome
            contato.save()
            if curso_id:
                # Inscrição no Evento
                titulo = curso.nome
                if curso.modulo and curso.modulo.curso_set.filter(tipo__meta=True).exists():
                    inscricao, mensagem = Inscricao.inscrever(curso, discente)
                    return redirect(reverse('confirma_inscricao', args=(inscricao.hash_confirmacao(),)))
                else:
                    inscricao, mensagem = Inscricao.inscrever(curso, discente, True)
                    if not mensagem:
                        return redirect(reverse('confirma_inscricao', args=(inscricao.hash_confirmacao(),)))

            else:
                titulo = f"Obrigado {discente.nome}"
                mensagem = 'Seu cadastro foi atualizado com sucesso'

            buttons = default_buttons(contato)
            return render(request, get_template_name(curso),
                          {'titulo': titulo,
                           'mensagem': mensagem,
                           'buttons': buttons})

    return render(request, template_name, {
        'form_inscricao': form_inscricao,
        'curso': curso,
    })


def efetiva_inscricao(inscricao, envia_email=True):
    if inscricao.curso.tot_alunos() < inscricao.curso.num_max_alunos:
        inscricao.status = Inscricao.Status.ATIVA
        inscricao.save()
        if envia_email:
            inscricao.email_confirmacao()
        titulo = f'{inscricao.curso.nome} - Inscrição confirmada!'
        if inscricao.curso.moodle_id:
            try:
                registro_moodle(inscricao)
                mensagem = ('Para acessar o curso, clique no botão abaixo (a senha foi enviada para o seu'
                            ' email caso seja o seu primeiro acesso).')
            except Exception as e:
                # A inscricao no Odorico ja esta confirmada (status ATIVA salvo acima);
                # apenas o provisionamento no EAD/Moodle falhou. Nao quebra o fluxo do
                # discente e registra a falha em log separado para reprocessamento.
                url_confirmacao = f'{settings.SITE_URL}/confirma_inscricao/{inscricao.hash_confirmacao()}/'
                moodle_falhas_logger.info(
                    'FALHA MOODLE inscricao_id=%s discente_id=%s cpf=%s email=%s '
                    'curso_id=%s moodle_course_id=%s url=%s erro=%s',
                    inscricao.id, inscricao.discente_id, inscricao.discente.cpf,
                    inscricao.discente.email, inscricao.curso_id, inscricao.curso.moodle_id,
                    url_confirmacao, repr(e),
                )
                mensagem = ('Sua inscrição foi confirmada! O acesso ao ambiente EAD será liberado '
                            'em breve. Caso não receba o e-mail de acesso, entre em contato com a secretaria.')
        else:
            mensagem = "Aproveite para atualizar o seu cadastro, clicando no botão abaixo"
        tipo = 'sucesso'
    else:
        inscricao.status = Inscricao.Status.LISTA_ESPERA
        inscricao.save()
        titulo = f'{inscricao.curso.nome} - Lotado!'
        mensagem = ("Infelizmente não há mais vagas. Incluímos seu nome em uma lista "
                    "de espera e caso haja alguma desistência, iremos enviar uma nova confirmação.")
        tipo = 'erro'

    return {'titulo': titulo, 'mensagem': mensagem, 'tipo': tipo}


def confirma_inscricao(request, hash_auth):
    id_str = hash_auth.split('-')[0]
    if id_str.isdigit():
        inscricao = Inscricao.objects.filter(id=id_str).first()
    else:
        inscricao = None
    if not inscricao or hash_auth != inscricao.hash_confirmacao():
        titulo = 'Inscrição não encontrada'
        mensagem = 'Link de confirmação inválido'
        return render(request, 'base_escola.html', {'titulo': titulo, 'mensagem': mensagem})

    # atualiza o status do discente e valida o contato
    if not inscricao.discente.validado:
        inscricao.discente.validado = True
        inscricao.discente.save()
        log_object(inscricao.discente, 'Validado via inscrição', True)

    if not inscricao.discente.contato:
        contato = Contato(nome=inscricao.discente.nome, email=inscricao.discente.email,
                          curso_origem=inscricao.curso, origem='Odorico', email_invalido=False)
        contato.save()
        inscricao.discente.contato = contato
        inscricao.discente.save()

    avisos_list = []
    curso = inscricao.curso
    if curso.modulo and curso.modulo.curso_set.filter(tipo__meta=True).exists():
        dtset = Curso.objects.filter(modulo=curso.modulo, status=Curso.Status.ATIVO).exclude(id=curso.id)
    else:
        dtset = None

    # se houver trilhas ou cursos associados, permitir a seleção
    if dtset:
        # marca a inscrição do evento como confirmada
        inscricao.status = Inscricao.Status.ATIVA
        inscricao.save()
        # habilita a seleção das trilhas do evento
        inscricoes_relacionadas = Inscricao.objects.filter(curso__in=dtset, discente=inscricao.discente)
        cursos_ja_marcados = inscricoes_relacionadas.values_list('curso', flat=True).distinct()
        form = InscricaoCursoForm(request.POST or None, cursos_relacionados=dtset,
                                  cursos_marcados=cursos_ja_marcados)
        if request.POST:
            cursos_atuais = {}
            for curso_marcado in cursos_ja_marcados:
                cursos_atuais[str(curso_marcado)] = 1
            cursos_selecionados = request.POST.getlist('cursos')
            for curso_id in cursos_selecionados:
                curso_adicional = Curso.objects.filter(id=curso_id).first()
                if curso_adicional:

                    if cursos_atuais.get(curso_id):
                        del cursos_atuais[curso_id]

                    inscricao, mensagem = Inscricao.inscrever(curso_adicional, inscricao.discente, True)
                    avisos = efetiva_inscricao(inscricao, False)
                    if avisos and avisos.get("tipo") == "sucesso":
                        avisos_list.append({"titulo": avisos["titulo"], "mensagem": "", "tipo": avisos["tipo"]})
                    else:
                        avisos_list.append(avisos)

            for curso_id in cursos_atuais.keys():
                curso_a_remover = Curso.objects.get(id=curso_id)
                Inscricao.objects.filter(discente=inscricao.discente, curso=curso_a_remover).delete()
                log_object(inscricao.discente, f'Desistiu do curso {curso.nome}')

            # para mostrar a msg de atualização do cadastro, se houver alguma inscrição com sucesso
            if any(a.get("tipo") == "sucesso" for a in avisos_list):
                avisos_list.append({
                    "titulo": "",
                    "mensagem": "Aproveite para atualizar o seu cadastro, clicando no botão abaixo",
                    "tipo": "sucesso"
                })
        else:
            return render(request, get_template_name(curso, 'inscrever_cursos_modulo.html'),
                          {'inscricao': inscricao, 'cursos': dtset, 'form': form})
    else:
        avisos_list.append(efetiva_inscricao(inscricao))

    link_cursos = '/cursos'
    buttons = default_buttons(inscricao.discente.contato)
    if not dtset and curso.modulo:
        buttons.insert(0,{'url': curso.modulo.url(), 'caption': 'Nova inscrição'})
    elif curso.moodle_id:
        ead_domain = '/'.join(settings.URL_MOODLE.split('/')[0:3])
        buttons.insert(0, {'url': ead_domain, 'caption': 'Acesso o curso'})

    response = render(request, get_template_name(curso),
                      {'titulo': curso.nome, 'avisos_range': avisos_list, 'buttons': buttons})
    response.set_cookie('CONFIRMED', inscricao.hash_confirmacao(), max_age=10 * 60)
    return response


# Permite que o aluno registre a sua presença
def confirma_presenca(request, hash_auth):
    curso_id, _ = hash_auth.split('-')
    curso = Curso.objects.filter(id=curso_id).first()
    titulo = 'Registro de Presença'
    if not curso or hash_auth != curso.hash_confirmacao():
        return render(request, './base_escola.html',
                      {'titulo': titulo, 'mensagem': 'Curso/evento inexistente'})

    agora = timezone.now()
    if curso.tipo.meta:
        curso_base = Curso.objects.filter(modulo=curso.modulo, tipo__evento=True).first()
    else:
        curso_base = curso

    template_name = get_template_name(curso_base, 'confirma_presenca.html')

    if agora > curso.dt_limite_presenca or curso.status != 'A':
        return render(request, template_name,
                      {'titulo': titulo,
                       'mensagem': f'A presença estava disponível até {curso.dt_limite_presenca}'})

    resultado = None

    confirma_presenca_form = ConfirmaPresencaForm(request.POST or None)

    # se o id da inscrição foi passado como parâmetro, então é um checkin automático
    if request.method == 'GET' and request.GET.get('id'):
        inscricao_id = request.GET.get('id')
        inscricao = Inscricao.objects.filter(id=inscricao_id).first()
        if inscricao:
            inscricao.presenca = True
            inscricao.save()
            resultado = ['<h3>Presença anotada</h3>', ]

    if request.method == 'POST' and confirma_presenca_form.is_valid():
        email = confirma_presenca_form.cleaned_data['email']
        nome = confirma_presenca_form.cleaned_data['nome']
        if email:
            inscricoes = Inscricao.objects.filter(curso=curso, discente__email=email, status=Inscricao.Status.ATIVA)
        else:
            inscricoes = Inscricao.objects.filter(curso=curso, discente__nome__icontains=nome,
                                                  status=Inscricao.Status.ATIVA)

        resultado = []
        for inscricao in inscricoes.order_by('discente__nome'):
            resultado.append(
                f'<a href="/confirma_presenca/{hash_auth}/?id={inscricao.id}">{inscricao.discente.nome}</a>')

        if len(resultado) == 0:
            campo = 'e-mail' if email else 'nome'
            resultado.append(f'<h3>Nenhuma inscrição encontrada para esse {campo}</h3>')
        else:
            resultado.insert(0, '<p>Clique no nome do participante para confirmar a presença:</p>')

    return render(request, template_name, {'confirma_presenca_form': confirma_presenca_form,
                                           'curso': curso,
                                           'titulo': titulo,
                                           'resultado': resultado})


# Permite que o usuário indique se irá realmente comparecer ao curso/evento
def checkin(request, slug):
    PalavraChave.objects.filter(termo=slug).update(contador=F("contador") + 1)
    return render(request, 'base_escola.html',
                  {'titulo': 'Confirmação',
                   'mensagem': 'Obrigado por confirmar sua presença!'})


def inscricao_logout(request):
    response = redirect('/cursos')
    response.delete_cookie('CONFIRMED')
    return response


def meuscursos(request):
    if request.method == 'POST':
        form = ConfirmaPresencaForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                discente = Discente.objects.get(email=email)

                inscricoes_confirmadas = Inscricao.objects.filter(discente=discente, status=Inscricao.Status.ATIVA,
                                                                  curso__tipo__meta=False)
                inscricoes_nao_confirmadas = Inscricao.objects.filter(discente=discente, status=Inscricao.Status.ABERTO)

                curso_lista_confirmados = "".join(
                    [f'<li>{inscricao.curso.nome}</li>' for inscricao in inscricoes_confirmadas])

                if inscricoes_nao_confirmadas:
                    curso_lista_nao_confirmados = ""
                    for inscricao in inscricoes_nao_confirmadas:
                        link_confirmacao = f'{settings.SITE_URL}/confirma_inscricao/{inscricao.hash_confirmacao()}'
                        curso_lista_nao_confirmados += f'<li>{inscricao.curso.nome} - <a href="{link_confirmacao}">Confirmar Matrícula</a></li>'

                    mensagem_nao_confirmados = f'''
                                        <h3>IMPORTANTE: Você ainda não confirmou sua matrícula nos seguintes cursos. Clique nos links abaixo para confirmar cada uma das matrículas:</h3>
                                        <ul>{curso_lista_nao_confirmados}</ul>
                                    '''
                else:
                    mensagem_nao_confirmados = '<p>Todos os seus cursos estão confirmados!</p>'

                email_body = f'''
                                    <html>
                                        <body>
                                            <div>
                                                <p>Olá {discente.nome},</p>
                                                <p>Aqui está a lista dos cursos nos quais você está matriculado:</p>
                                                <ul>{curso_lista_confirmados}</ul>
                                            </div>

                                            <div>
                                                {mensagem_nao_confirmados}
                                            </div>
                                        </body>
                                    </html>
                                '''
                sendmail(
                    subject='Listagem dos cursos registrados',
                    dest_list=[email],
                    message=email_body,
                )

                return render(request, 'base_escola.html',
                              {'titulo': 'Lista de Cursos', 'mensagem': 'Lista enviada com sucesso para o email!'})
            except Discente.DoesNotExist:
                return render(request, 'base_escola.html',
                              {'titulo': 'Lista de Cursos', 'mensagem': 'E-mail não encontrado.'})
    else:
        form = ConfirmaPresencaForm()
    return render(request, 'meus_cursos.html', {'form': form})


@staff_member_required
def curso_qrcode_view(request, curso_id):
    curso = Curso.objects.filter(id=curso_id).first()
    if not curso:
        return render(request, 'base_escola.html',
                      {'titulo': 'Curso Inexistente ', 'mensagem': 'O curso indicado não existe'})

    link_presenca = request.build_absolute_uri(reverse('confirma_presenca', args=[curso.hash_confirmacao()]))

    qr = QRCode(
        version=1,
        error_correction=ERROR_CORRECT_L,
        box_size=7,
        border=4,
    )
    qr.add_data(link_presenca)
    qr.make(fit=True)

    img = qr.make_image(fill='black', back_color='white')

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return render(request, 'curso_qrcode.html', {'curso': curso, 'link_presenca': link_presenca, 'qr_code': img_str})


def envia_comunicado(conn, email, titulo, texto):
    headers = {'Reply-To': settings.REPLY_TO_EMAIL, }
    msg = EmailMultiAlternatives(titulo, texto, settings.DEFAULT_FROM_EMAIL,
                                 connection=conn,
                                 to=[email],
                                 headers=headers)
    msg.attach_alternative(texto, 'text/html; charset=UTF-8')
    msg.send()


def comunicado_thread(comunicado):
    conn = get_connection()
    if not conn:
        raise ValueError('SMTP connection failed')

    texto = f'<html><body>{comunicado.texto}</body></html>'
    tot_lidos = 0
    tot_enviados = 0
    try:
        if comunicado.tipo == 'T':
            envia_comunicado(conn, comunicado.email_teste, comunicado.titulo, texto)
            comunicado.status = 'F'
            comunicado.save()
            log_object(comunicado, 'Email de teste enviado')
            return

        if comunicado.tipo == 'L':
            dataset = Contato.objects.filter(listacontato__lista=comunicado.lista,email_invalido=False)
        else:
            dataset = Discente.objects.filter(validado=True).order_by('email')
            if comunicado.tipo == 'M':
                dataset = dataset.filter(inscricao__curso__modulo=comunicado.modulo,
                                         email__isnull=False).values('email').distinct()
            elif comunicado.tipo == 'C':
                dataset = dataset.filter(
                    inscricao__curso=comunicado.curso).exclude(
                    inscricao__status=Inscricao.Status.CANCELADA).values('email')

        for contato in dataset:
            tot_lidos += 1
            if comunicado.cont_erro and tot_lidos < comunicado.cont_erro:
                continue
            if contato.email:
                try:
                    envia_comunicado(conn, contato.email, comunicado.titulo, texto)
                    tot_enviados += 1
                    if tot_enviados % 30 == 0:
                        conn.close()
                        time.sleep(15)
                        conn = get_connection()
                except smtplib.SMTPException as e:
                    time.sleep(15)

        comunicado.cont_erro = None
        comunicado.status = 'F'
        comunicado.save()
        log_object(comunicado, f'{tot_enviados} emails enviados')
    except Exception as e:
        log_object(comunicado, f'Enviados: {tot_enviados}. Erro: {type(e).__qualname__} ')
        comunicado.cont_erro = tot_lidos
        comunicado.status = 'E'
        comunicado.save()


@staff_member_required
def agenda_comunicado(request, comunicado_id):
    comunicado = Comunicado.objects.get(id=comunicado_id)
    comunicado.status = 'P'
    comunicado.save()
    log_object(comunicado, 'Envio agendado')
    t = threading.Thread(target=comunicado_thread, args=[comunicado], daemon=True)
    t.start()
    messages.info(request, 'Envio agendado')
    return HttpResponseRedirect(f'/admin/escola/comunicado/{comunicado_id}/change/')


# Lista apenas os maiores itens de uma lista e colocar os restantes dos itens no último elemento da lista
def somente_os_maiores(dataset, key_field, value_field, num_maximo=10):
    dataset = sorted(dataset, key=lambda d: d[value_field], reverse=True)
    grouped_queryset = dataset[:num_maximo]
    restante = sum(item[value_field] for item in dataset[num_maximo + 1:]) or 0
    grouped_queryset.append({key_field: 'Outros', value_field: restante})
    return grouped_queryset


# dataset deve ser uma lista de dicionários
def transform_dataset_display(dataset, model_class, field_names):
    for record in dataset:
        for field_name in field_names:
            field_value = record[field_name]
            new_value = get_display_str(field_value, model_class, field_name)
            if new_value:
                record[field_name] = new_value
    return dataset


@staff_member_required
def presenca_evento(request, id_curso):
    curso = get_object_or_404(Curso, id=id_curso)
    inscricoes = Inscricao.objects.none()

    if request.POST:
        inscricoes = Inscricao.objects.filter(id__in=list(map(lambda x: int(x), request.POST.getlist('inscricoes'))))
        row_updated = inscricoes.update(presenca=True)
        if row_updated:
            messages.success(request, "Presença marcada com sucesso")
        else:
            messages.warning(request, 'Nenhuma presença foi confirmada')
    else:
        participante = request.GET.get('participante')
        if participante:
            ordering = request.GET.get('order_by', 'discente__nome')

            if '@' in participante:
                inscricoes = Inscricao.objects.filter(
                    discente__email=participante,
                    curso=curso
                )
            else:
                inscricoes = Inscricao.objects.filter(
                    curso=curso,
                    discente__nome__icontains=participante
                )

            inscricoes = inscricoes.order_by(ordering)

    return render(request, 'evento_presenca.html', {'curso': curso, 'inscricoes': inscricoes})


@require_POST
def save_session(request, session_id, token):
    """
    API Simples (sem DRF) para controle de agenda (Add/Remove).
    A função utiliza o get_or_create/delete para realizar a ação em uma única chamada.
    Mapeamento de Status HTTP para a ação:
    - 201 CREATED (HTTPStatus.CREATED): Item adicionado à agenda.
    - 200 OK (HTTPStatus.OK): Item removido da agenda.
    """
    sessao = get_object_or_404(ModuloSessao, pk=session_id)
    agenda, created = sessao.contatoagenda_set.get_or_create(cookie=token)

    if created:
        http_status = HTTPStatus.CREATED
    else:
        agenda.delete()
        http_status = HTTPStatus.OK

    return JsonResponse({'session_id': session_id, 'token': token, 'agenda_id': agenda.pk}, status=http_status)


@require_POST
def save_schedule(request, slug):
    """
    API Simples (sem DRF) para atualização do contato da Agenda e envio de e-mail com link da agenda personalizada.
    Usa Django Forms para validação e evita o DRF para manter a simplicidade.
    O retorno de erro 400 é padronizado (JSON com a chave 'error') para integrar de forma nativa com a lógica de
    tratamento de erro do cliente (fetch/AJAX).
    """
    obj = get_object_or_404(Modulo, slug=slug)
    token = request.COOKIES.get('cookie')

    data = {'modulo': obj.pk, 'cookie': token, **request.POST.dict()}
    form = AgendaForm(data)

    if form.is_valid():
        form.save()
        return JsonResponse({'modulo_id': obj.pk})
    else:
        if 'email' in form.errors:
            error_message = form.errors['email'][0]
        else:
            error_message = 'Erro de validação desconhecido.'

        return JsonResponse({'error': error_message}, status=HTTPStatus.BAD_REQUEST)


