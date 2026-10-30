import logging
from http import HTTPStatus

logger = logging.getLogger('moodle')
if not logger.handlers:
    import os as _os
    _log_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'logs')
    _handler = logging.FileHandler(_os.path.join(_log_dir, 'moodle.log'))
    _handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

import requests
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, HTML, Div
from django import forms
from django.conf import settings
from django.core.validators import EMPTY_VALUES
from django.shortcuts import render
from django.urls import reverse
from django.utils.text import normalize_newlines
from django_select2.forms import ModelSelect2Widget
from openpyxl import load_workbook

from nucleo.apps import intdef, log_object

from nucleo.crispy_admin_layout import AdminSubmitRow
from .models import Modulo, Curso, ModuloSessao, ModuloTrilha, ListaInteresse
from .utils import import_pauta_xlsx, import_palestrantes, import_lista
from utils.email import sendmail


class ImportacaoPautaForm(forms.Form):
    TIPOS = (
        ('matriculas', 'Matrículas'),
        ('palestrantes', 'Palestrantes'),
        ('livre', 'Lista Livre'),
        ('presenca', 'Presença'),
    )

    tipo = forms.ChoiceField(choices=TIPOS, label='Tipo')
    curso = forms.ModelChoiceField(
        queryset=Curso.objects.filter(status=Curso.Status.FINALIZADO),
        label='Curso',
        required=False,
        widget=ModelSelect2Widget(
            model=Curso, search_fields=['nome__icontains'], max_results=10,
            attrs={'data-minimum-input-length': 4}
        )
    )
    lista = forms.ModelChoiceField(
        queryset=ListaInteresse.objects.all(),
        label='Lista de Interesse',
        required=False,
        widget=ModelSelect2Widget(
            model=ListaInteresse, search_fields=['titulo__icontains'], max_results=10,
            attrs={'data-minimum-input-length': 4}
        )
    )
    arquivo_xlsx = forms.FileField(
        label='Arquivo XLSX',
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        post_buttons = (
            Div(Submit('submit', 'Importar'), css_class="col"),
            Div(HTML('<a href="%s"class="buttonlink">Voltar</a></div>' %
                     reverse('admin:index')), css_class="col")
        )
        self.helper.layout = Layout(
            'curso',
            'tipo',
            'lista',
            'arquivo_xlsx',
            AdminSubmitRow(*post_buttons)
        )

    def clean_arquivo_xlsx(self):
        file = self.cleaned_data['arquivo_xlsx']
        if file:
            if not file.name.endswith('.xlsx'):
                raise forms.ValidationError(
                    'O arquivo deve estar no formato XLSX.')
        return file

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        if tipo in ('livre', 'participantes'):
            if not cleaned_data.get('lista'):
                raise forms.ValidationError('A lista deve ser informada')

        if tipo != 'livre':
            if not cleaned_data.get('curso'):
                raise forms.ValidationError('O curso deve ser informado')

        if tipo != 'palestrantes':
            if not cleaned_data.get('arquivo_xlsx'):
                raise forms.ValidationError('O arquivo deve ser informado')

        return cleaned_data


def importacao_pauta(request):
    if request.method == 'POST':
        form = ImportacaoPautaForm(request.POST, request.FILES)
        if form.is_valid():
            curso = form.cleaned_data['curso']
            tipo = form.cleaned_data['tipo']
            lista = form.cleaned_data['lista']
            arquivo_xlsx = form.cleaned_data['arquivo_xlsx']
            if tipo == 'palestrantes':
                total_registros, novos_discentes, erros = import_palestrantes(lista, curso)
            elif tipo == 'livre':
                total_registros, novos_discentes, erros = import_lista(lista, arquivo_xlsx)
            else:
                total_registros, novos_discentes, erros = import_pauta_xlsx(curso, tipo, arquivo_xlsx)

            return render(request, 'import_pauta.html', {
                'total_registros': total_registros,
                'novos_discentes': novos_discentes,
                'erros': erros
            })
    else:
        form = ImportacaoPautaForm()

    return render(request, 'import_pauta.html', {'form': form})


class ImportacaoSessoesForm(forms.Form):
    modulo = forms.ModelChoiceField(
        queryset=Modulo.objects.all(),
        label='Evento',
        required=False,
        widget=ModelSelect2Widget(
            model=Modulo, search_fields=['nome__icontains'], max_results=10,
            attrs={'data-minimum-input-length': 4}
        )
    )
    arquivo_xlsx = forms.FileField(
        label='Arquivo XLSX',
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        post_buttons = (
            Div(Submit('submit', 'Importar'), css_class="col"),
            Div(HTML('<a href="%s"class="buttonlink">Voltar</a></div>' %
                     reverse('importacao_sessoes')), css_class="col")
        )
        self.helper.layout = Layout(
            'modulo',
            'arquivo_xlsx',
            AdminSubmitRow(*post_buttons)
        )
        self.fields['modulo'].widget.initial = self.initial.get('modulo', None)

    def clean_arquivo_xlsx(self):
        file = self.cleaned_data['arquivo_xlsx']
        if file:
            if not file.name.endswith('.xlsx'):
                raise forms.ValidationError(
                    'O arquivo deve estar no formato XLSX.')
        return file


# O arquivo deve estar no formato Trilha, Dia, Sessão, Hora Inicial, Hora Final, Trabalhos
def import_xls_sessoes(modulo, arquivo_xlsx):
    tot_lidos = 0
    tot_invalidos = 0
    novas_sessoes = 0
    erros = []
    try:
        wb = load_workbook(arquivo_xlsx)
        ws = wb.active

        for row in ws.iter_rows(min_row=1, values_only=True):
            if len(row) < 1:
                if tot_lidos == 0:
                    erros.append('Arquivo vazio ou com linhas em branco')
                break

            tot_lidos += 1
            trilha = row[0]
            if trilha:
                trilha = ModuloTrilha.objects.filter(modulo=modulo, nome__startswith=trilha).first()
                if not trilha:
                    erros.append(f"Linha {tot_lidos}: Trilha não encontrada")
                    tot_invalidos += 1
                    break
            else:
                break

            titulo = row[1]
            descricao = row[2]
            dia = row[3]
            hora = row[4]
            hora_final = row[5]
            linhas = normalize_newlines(row[6]).splitlines(True)
            trabalhos = '<p>'
            for linha in linhas:
                if intdef(linha[:1]):
                    trabalhos += f'<b>{linha}</b><br/>'
                else:
                    trabalhos += linha.replace('Autorias: ', '') + '<br/>'
            trabalhos += '</p>'

            sessao, nova = ModuloSessao.objects.get_or_create(trilha=trilha, dia=dia, titulo=titulo,
                                                              defaults={'hora_inicial': hora, 'hora_final': hora_final})
            sessao.sessao = descricao
            sessao.trabalhos = trabalhos
            sessao.save()
            if nova:
                novas_sessoes += 1

    except Exception as e:
        erros.append(f'Linha {tot_lidos}: Erro durante o processamento: {str(e)}')

    return tot_lidos, novas_sessoes, erros


def importacao_sessoes(request):
    template_name = 'import_sessoes.html'
    if request.method == 'POST':
        form = ImportacaoSessoesForm(request.POST, request.FILES)
        if form.is_valid():
            modulo = form.cleaned_data['modulo']
            arquivo_xlsx = form.cleaned_data['arquivo_xlsx']
            total_registros, novas_sessoes, erros = import_xls_sessoes(modulo, arquivo_xlsx)

            return render(request, template_name, {
                'total_registros': total_registros,
                'novas_sessoes': novas_sessoes,
                'erros': erros
            })
    else:
        modulo_id = request.GET.get('modulo_id', None)
        form = ImportacaoSessoesForm(initial={'modulo': modulo_id})

    return render(request, template_name, {'form': form})


def busca_usuario_moodle(campo, valor):
    if valor in EMPTY_VALUES:
        return None

    payload = {
        'wstoken': settings.API_MOODLE,
        'wsfunction': 'core_user_get_users',
        'moodlewsrestformat': 'json',
        'criteria[0][key]': campo,
        'criteria[0][value]': valor,
    }

    logger.info('[moodle] busca_usuario_moodle: campo=%s valor=%s', campo, valor)
    response = requests.post(settings.URL_MOODLE, data=payload, timeout=30)
    logger.info('[moodle] busca_usuario_moodle: status=%s body=%s', response.status_code, response.text[:500])

    if response.status_code != HTTPStatus.OK:
        response.raise_for_status()

    try:
        data = response.json()
    except ValueError:
        raise Exception(f'Erro ao converter resposta: {response.text}')

    if 'exception' in data:
        raise Exception(data.get('message'))

    users = data.get('users', [])

    if not users:
        return None

    return users[0].get('id')


def cria_usuario_moodle(discente):
    if discente.cpf in EMPTY_VALUES and discente.email in EMPTY_VALUES:
        return None

    user_id = busca_usuario_moodle('username', discente.cpf)

    if user_id:
        return user_id, False

    user_id = busca_usuario_moodle('email', discente.email)

    if user_id:
        return user_id, False

    last_name = discente.nome.split()[-1]
    first_name = discente.nome.replace(last_name, '').strip()

    user = {
        'username': discente.cpf,
        'password': f'ExtraForte#{discente.id}',
        'firstname': first_name,
        'lastname': last_name,
        'email': discente.email,
    }

    payload = {
        'wstoken': settings.API_MOODLE,
        'wsfunction': 'core_user_create_users',
        'moodlewsrestformat': 'json',
    }

    for campo, valor in user.items():
        payload[f'users[0][{campo}]'] = valor

    logger.info('[moodle] cria_usuario_moodle: discente_id=%s cpf=%s email=%s',
               discente.id, discente.cpf, discente.email)
    response = requests.post(settings.URL_MOODLE, data=payload, timeout=30)
    logger.info('[moodle] cria_usuario_moodle: status=%s body=%s', response.status_code, response.text[:500])

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError:
        raise Exception(f'Erro ao converter resposta: {response.text}')

    if 'exception' in data:
        raise Exception(data.get('message'))

    return data[0].get('id'), True


def cria_inscricao_curso_moodle(user_id, course_id):
    # Papel no curso (estudante)
    role_id = 5

    payload = {
        'wstoken': settings.API_MOODLE,
        'wsfunction': 'enrol_manual_enrol_users',
        'moodlewsrestformat': 'json',
        'enrolments[0][roleid]': role_id,
        'enrolments[0][userid]': user_id,
        'enrolments[0][courseid]': course_id,
    }

    logger.info('[moodle] cria_inscricao_curso_moodle: user_id=%s course_id=%s', user_id, course_id)
    response = requests.post(settings.URL_MOODLE, data=payload, timeout=30)
    logger.info('[moodle] cria_inscricao_curso_moodle: status=%s body=%s', response.status_code, response.text[:500])

    response.raise_for_status()

    try:
        data = response.json()
        # A API do moodle tem o comportamento peculiar de não retornar dados após uma inscrição com sucesso e a
        # requisição pode ser executada várias vezes para o mesmo user_id e course_id que o retorno é o mesmo.
        # Caso dê erro, a resposta vem com conteúdo
        if data and 'exception' in data:
            raise Exception(data.get('message'))
    except ValueError:
        raise Exception(f'Erro ao converter resposta: {response.text}')


def registro_moodle(inscricao):
    if not inscricao.discente.moodle_id:
        id_usuario, created = cria_usuario_moodle(inscricao.discente)
        inscricao.discente.moodle_id = id_usuario
        inscricao.discente.save()
    else:
        id_usuario = inscricao.discente.moodle_id
        created = False

    cria_inscricao_curso_moodle(id_usuario, inscricao.curso.moodle_id)
    inscricao.inscrito_curso_moodle = True
    inscricao.save()
    log_object(inscricao, 'Inscrição Moodle criada')

    if created:
        mensagem = f'<p>O username é o seu CPF e a senha temporária é ExtraForte#{inscricao.discente.id}</p>'
    else:
        mensagem = f'<p>Lembre de utilizar o seu CPF como login e a senha que você já tinha no sistema</p>'

    ead_domain = '/'.join(settings.URL_MOODLE.split('/')[0:3])

    sendmail('EAD/Moodle', [inscricao.discente.email],
             message=f'<html><body>'
                     f'<p>Acesse <a href="{ead_domain}">EAD</a></p>{mensagem}'
                     f'</body></html>', thread=True)

