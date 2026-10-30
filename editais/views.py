import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from nucleo.apps import generate_hash, log_object
from nucleo.lattes import obtem_lattes
from nucleo.models import Documento, Pesquisador, PesquisadorFormacao
from nucleo.views import render_mensagem

from utils.email import sendmail
from utils.models import TipoProcessamento

from .forms import DocumentoUploadForm, InscricaoEditalForm, InscricaoInicialEditalForm, PesquisadorFormacaoForm
from .models import Edital, EditalTipoDocumento, Inscricao


def import_dados_lattes(id_cnpq):
    resultado = obtem_lattes(id_cnpq, True)
    objeto = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
    if not objeto:
        objeto = TipoProcessamento.objects.get(tipo=TipoProcessamento.Status.EDITAL_AVISO)
    if objeto:
        if resultado.get('sucesso'):
            log_object(objeto, 'Lattes importado via inscrição em edital')
        else:
            log_object(objeto, f'Erro ao importar o Currículo Lattes via edital ({id_cnpq})')


def nova_inscricao_edital(request, id_edital):
    edital = get_object_or_404(Edital, id=id_edital)

    hoje = timezone.now()
    if edital.status != Edital.Status.ATIVO or (edital.dt_inicio < hoje > edital.dt_fim):
        messages.error(request, "Este edital não está ativo para novas inscrições.")
        return redirect('home')

    if request.method == 'POST':
        form = InscricaoInicialEditalForm(request.POST, edital=edital, request=request)
        if form.is_valid():
            inscricao = form.save(commit=False)

            pesquisador = form.pesquisador
            email_final = form.cleaned_data.get("email")
            if pesquisador:
                if not pesquisador.CPF and inscricao.CPF:
                    pesquisador.CPF = inscricao.CPF
                    pesquisador.save(update_fields=["CPF"])
                    log_object(pesquisador, 'CPF atualizado pela rotina de editais')

                # Se o pesquisador ainda não tem e-mail, usar o informado no form
                if pesquisador.email:
                    email_final = pesquisador.email
                    log_object(inscricao, 'Email preferencial selecionado')

            else:
                if form.nome_pesquisador:
                    pesquisador = Pesquisador.objects.create(
                        CPF=inscricao.CPF,
                        id_cnpq=inscricao.id_cnpq,
                        nome=inscricao.nome,
                        email=inscricao.email)

            inscricao.candidato = pesquisador
            inscricao.save()

            if not pesquisador:
                log_object(inscricao, 'Pesquisador não encontrado')
            else:
                # atualiza os dados do pesquisador
                t = threading.Thread(target=import_dados_lattes, args=[inscricao.id_cnpq,], daemon=True)
                t.start()

            link = settings.SITE_URL+reverse('inscricao_edital',
                           kwargs={'id_inscricao': inscricao.id,
                                   'hash': generate_hash(str(inscricao.id)),})

            # se já existia uma cadastro para o pesquisador, o candidato deve confirmar o seu email
            # para garantir que ele tem permissão de acessar os dados a partir do email
            processo = TipoProcessamento.objects.filter(tipo=TipoProcessamento.Tipo.EDITAL_AVISO).first()
            mensagem = processo.template_email.format(**locals())
            sendmail('Confirme seu email', [email_final,], message=mensagem)
            return render_mensagem(request,'Valide agora o seu email',
        f'Para continuar a inscrição, verifique a sua caixa postal em <b>{email_final}</b>.'
                f'<br/>Caso você não tenha mais acesso a esse e-mail, atualize o seu cadastro na área '
                f'de Meus Dados ou entre em contato com a secretaria.')

        # Se o formulário de erro de inscrição duplicada
        cpf_errors = form.errors.get('CPF')
        if cpf_errors:
            cpf = form.data.get("CPF")
            inscricao = Inscricao.objects.filter(edital=edital, CPF=cpf).first()
            if inscricao and inscricao.email:
                link = settings.SITE_URL + reverse('inscricao_edital',
                                                   kwargs={'id_inscricao': inscricao.id,
                                                           'hash': generate_hash(str(inscricao.id)), })
                processo = TipoProcessamento.objects.filter(tipo=TipoProcessamento.Tipo.EDITAL_AVISO).first()
                mensagem = processo.template_email.format(**locals())
                sendmail('Inscrição já existente', [inscricao.email], message=mensagem)

    else:
        form = InscricaoInicialEditalForm(edital=edital, request=request)

    return render(request,
                  'editais/nova_inscricao_edital.html',
                  {'edital': edital, 'form': form})


@transaction.atomic
def inscricao_edital(request, id_inscricao, hash):
    inscricao = get_object_or_404(Inscricao, id=id_inscricao)

    if generate_hash(str(inscricao.id)) != hash:
        messages.error(request, "Inscrição inexistente. Entre em contato com a secretaria.")
        return redirect('home')

    edital = get_object_or_404(Edital, id=inscricao.edital.id)
    tipo_vaga = inscricao.tipo_vaga

    hoje = timezone.now()
    if (edital.dt_inicio < hoje > edital.dt_fim) and inscricao.status == Inscricao.Status.EM_EDICAO:
        messages.error(request, "Este edital não está ativo para novas inscrições.")
        return redirect('home')

    mostrar_formulario_readonly = (edital.status != Edital.Status.ATIVO or
                                   hoje > edital.dt_fim or
                                   inscricao.status != Inscricao.Status.EM_EDICAO)

    documento_upload_form = None
    formacao_form = None

    # Sempre carrega documentos existentes (GET e POST)
    documentos_existentes = Documento.objects.filter(
        content_type=ContentType.objects.get_for_model(Inscricao),
        object_id=inscricao.id
    )
    existentes_tipo_ids = set(documentos_existentes.values_list('tipo_id', flat=True))

    if request.method == 'POST' and not mostrar_formulario_readonly:
        form = InscricaoEditalForm(request.POST, instance=inscricao, edital=edital, request=request)

        documento_upload_form = DocumentoUploadForm(
            request.POST,
            request.FILES,
            edital=edital,
            tipo_vaga=tipo_vaga,
            documentos_existentes_tipo_ids=existentes_tipo_ids
        )

        if form.is_valid() and documento_upload_form.is_valid():
            documentos = documento_upload_form.cleaned_data

            # Documentos obrigatórios aplicáveis (gerais + específicos da vaga)
            required_docs = EditalTipoDocumento.objects.filter(edital=edital, obrigatorio=True).filter(
                Q(tipo_vaga__isnull=True) | Q(tipo_vaga=tipo_vaga)
            )

            faltando = []
            for doc in required_docs:
                field_name = f'documento_{doc.id}'
                uploaded_file = documentos.get(field_name)

                # Cumpre se enviou agora OU se já existe salvo antes com o mesmo tipo_id
                if not uploaded_file and (doc.tipo_id not in existentes_tipo_ids):
                    faltando.append(doc.descricao)

            if faltando:
                messages.error(
                    request,
                    "Faltam os seguintes documentos obrigatórios: " + ", ".join(faltando)
                )
            else:
                # Salva inscrição
                inscricao = form.save(commit=False)
                inscricao.status = Inscricao.Status.SUBMETIDA
                inscricao.save()

                # Salva documentos (somente os enviados agora)
                for field_name in documentos.keys():
                    if field_name.startswith("documento_"):
                        uploaded_file = documentos[field_name]
                        if uploaded_file:
                            tipo_id = documento_upload_form.tipo_documento_por_field[field_name]
                            Documento.objects.update_or_create(
                                content_type=ContentType.objects.get_for_model(Inscricao),
                                object_id=inscricao.id,
                                tipo_id=tipo_id,
                                defaults={"anexo": uploaded_file}
                            )

                log_object(inscricao, 'Inscrição Efetivada')

                tipo_proc = TipoProcessamento.objects.filter(
                    tipo=TipoProcessamento.Tipo.EDITAL_CONFIRMACAO).first()
                mensagem = tipo_proc.template_email.format(**locals())
                sendmail('Inscrição realizada com sucesso', [inscricao.email], message=mensagem)

                return render_mensagem(request,
                        'Inscrição enviada!',
                    'Aguarde o resultado da homologação da sua inscrição conforme o calendário do edital.')
        else:
            messages.error(request, "Corrija os erros abaixo para continuar.")

    else:
        form = InscricaoEditalForm(instance=inscricao, edital=edital, request=request)

        #if inscricao.candidato:
        #    formacao = PesquisadorFormacao.objects.filter(pesquisador=inscricao.candidato).first()
        #    formacao_form = PesquisadorFormacaoForm(instance=formacao) if formacao else PesquisadorFormacaoForm()

        documento_upload_form = DocumentoUploadForm(
            edital=edital,
            tipo_vaga=tipo_vaga,
            documentos_existentes_tipo_ids=existentes_tipo_ids
        )

    if mostrar_formulario_readonly:
        for field in form.fields.values():
            field.disabled = True
        # for field in formacao_form.fields.values():
        #    field.disabled = True
        for field in documento_upload_form.fields.values():
            field.disabled = True

    return render(request, 'editais/inscricao_edital.html', {
        'form': form,
        'documento_upload_form': documento_upload_form,
        'inscricao': inscricao,
        'edital': edital,
        'readonly': mostrar_formulario_readonly,
        'documentos_existentes': documentos_existentes
    })


@login_required
def edital_lattes(request, id_inscricao: int):
    inscricao = get_object_or_404(Inscricao, pk=id_inscricao)
    try:
        erro = False
        resultado = obtem_lattes(inscricao.id_cnpq, com_producao=True)
        if resultado.get('sucesso'):
            if not inscricao.candidato:
                inscricao.candidato = Pesquisador.objects.get(id_cnpq=inscricao.id_cnpq)
            inscricao.status_cnpq = Inscricao.StatusCNPQ.VALIDADO
            inscricao.save()
            messages.info(request, 'Currículo Lattes atualizado')
        else:
            messages.error(request, 'ID CNPQ inválido')
            erro = True
    except Exception as e:
        messages.error(request, f'{e}')
        erro = True

    if erro:
        inscricao.status_cnpq = Inscricao.StatusCNPQ.ERRO
        inscricao.save()

    return HttpResponseRedirect(reverse('admin:editais_inscricao_change', args=(id_inscricao,)))