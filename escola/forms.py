import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.template import engines
from django.utils.datetime_safe import date
from django.utils.safestring import mark_safe

from nucleo.crispy_admin_layout import AdminSubmitRow
from utils.email import sendmail
from utils.fields import validate_orcid
from .models import (Curso, Docente, Discente, ORIGEM_OPTIONS, FORMACAO_CHOICES, ContatoAgenda, Modulo, Contato,
                     ListaInteresse)


class DocenteAddForm(forms.ModelForm):
    def clean_orcid(self):
        orcid = self.cleaned_data.get('orcid')
        if orcid:
            name = self.cleaned_data.get('nome')

            is_valid, message = validate_orcid(orcid, name)
            if not is_valid:
                raise forms.ValidationError(message)

        return orcid

    class Meta:
        model = Docente
        fields = ("orcid", "nome",)


class InscreverForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        readonly_fields = kwargs.pop('readonly_fields', [])
        super(InscreverForm, self).__init__(*args, **kwargs)
        for field_name in readonly_fields:
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs['readonly'] = True

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        post_buttons = (
            Div(Submit('inscrever', 'Confirmar Inscrição')),
        )
        self.helper.layout = Layout(
            'nome',
            'sexo',
            'id_cnpq',
            'orcid',
            'email',
            AdminSubmitRow(*post_buttons)
        )

    class Meta:
        model = Discente
        fields = ['nome', 'sexo', 'id_cnpq', 'orcid', 'email']
        widgets = {
            'email': forms.HiddenInput()
        }


class FormConsentimento(forms.Form):
    origem = forms.CharField(
        label='Como você ficou sabendo deste evento/curso?',
        widget=forms.TextInput(attrs={
            'list': 'origem-options',
            'class': 'form-control',
        }),
        help_text='Escolha uma das opções ou digite outra opção'
    )
    concorda_termos = forms.BooleanField(
        label=mark_safe(
            ''' <small>Ao se inscrever neste evento, você está ciente de que há a possibilidade de seu registro
             audiovisual e eventual reprodução nos canais oficiais do IBICT, inclusive em redes sociais.
            Ao clicar na opção abaixo, você concorda com a cessão gratuita de seu nome, imagem e/ou voz,
            conforme aplicável à sua participação, para os fins de divulgação deste evento nos canais supracitados.
            Para mais informações sobre nossa política de dados pessoais, por favor acesse nossa
            <span class="simples">
            <a href="https://www.gov.br/ibict/pt-br/acesso-a-informacao/protecao-de-dados-pessoais" target="_blank">
            Política de proteção de dados</a></span></small>'''
        ),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'origem',
            'concorda_termos'
        )


class VerificarEmailForm(forms.Form):
    email = forms.EmailField(
        label='Email',
        widget=forms.TextInput(attrs={
            'class': 'form-control', "style": "width:40em"
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'email',
        )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        # Validação adicional do email
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise ValidationError('O endereço de email fornecido é inválido.')
        return email


# Função para renderizar o datalist no template
def render_origem_options():
    options_html = ''.join(f'<option value="{option}"></option>' for option in ORIGEM_OPTIONS)
    return f'<datalist id="origem-options">{options_html}</datalist>'


class DiscenteForm(forms.ModelForm):
    nome = forms.CharField(
        label='Nome Completo',
        widget=forms.TextInput(attrs={
            'placeholder': 'Preencha o seu nome completo pois será este que sairá no seu certificado',
            'class': 'form-control',
        }),
    )
    orcid = forms.CharField(
        label='ORCID (Opcional)',
        required=False,
        max_length=19,
        widget=forms.TextInput(attrs={
            'placeholder': '0000-0000-0000-0000',
            'class': 'form-control',
            'oninput': (
                "let value = this.value.replace(/[^0-9Xx]/g, '');"
                "if (value.length > 4) value = value.slice(0, 4) + '-' + value.slice(4);"
                "if (value.length > 9) value = value.slice(0, 9) + '-' + value.slice(9);"
                "if (value.length > 14) value = value.slice(0, 14) + '-' + value.slice(14);"
                "this.value = value;"
            )
        }),
    )
    formacao = forms.ChoiceField(
        label='Formação',
        choices=FORMACAO_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control',
        }),
    )
    telefone = forms.CharField(
        label='Telefone',
        max_length=15,
        widget=forms.TextInput(attrs={
            'placeholder': '(XX) XXXXX-XXXX',
            'class': 'form-control',
            'oninput': "this.value = this.value.replace(/\\D/g, '').replace(/(\\d{2})(\\d)/, '($1) $2').replace(/(\\d{5})(\\d{1,4})$/, '$1-$2');"
        }),
        required=False,
        error_messages={'invalid': 'Digite um número de telefone válido.'}
    )
    cep = forms.CharField(
        label='CEP',
        max_length=9,
        widget=forms.TextInput(attrs={
            'placeholder': 'XXXXX-XXX',
            'class': 'form-control',
            'oninput': "this.value = this.value.replace(/\\D/g, '').replace(/(\\d{5})(\\d{1,3})$/, '$1-$2');"
        }),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['cpf'].required = True

        if self.instance and self.instance.pk:
            self.initial['telefone'] = self.format_telefone(self.instance.telefone)
            self.initial['cep'] = self.format_cep(self.instance.cep)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        post_buttons = (
            Submit('submit', 'Enviar', css_class="mt3"),
        )
        self.helper.layout = Layout(
            "nome", "cpf", "telefone", "cep", "formacao", "instituicao", "orcid",
            AdminSubmitRow(*post_buttons)
        )

    def format_telefone(self, telefone):
        if telefone:
            telefone = re.sub(r'\D', '', telefone)
            if len(telefone) == 11:
                return '({}) {}-{}'.format(telefone[:2], telefone[2:7], telefone[7:])
            elif len(telefone) == 10:
                return '({}) {}-{}'.format(telefone[:2], telefone[2:6], telefone[6:])
        return telefone

    def format_cep(self, cep):
        if cep:
            cep = re.sub(r'\D', '', cep)
            return '{}-{}'.format(cep[:5], cep[5:])
        return cep

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            discente = Discente.objects.filter(email=email).exclude(pk=self.instance.pk)
            if discente.exists():
                raise forms.ValidationError('Já existe um(a) outra(o) discente com este email.')
        return email

    def clean_telefone(self):
        telefone = self.cleaned_data.get('telefone')
        if telefone:
            telefone = re.sub(r'\D', '', telefone)
            if len(telefone) not in [10, 11]:
                raise forms.ValidationError('O telefone deve conter 10 ou 11 dígitos.')
        return telefone

    def clean_cep(self):
        cep = self.cleaned_data.get('cep')
        if cep:
            cep = re.sub(r'\D', '', cep)
            if len(cep) != 8:
                raise forms.ValidationError('O CEP deve conter 8 dígitos.')
        return cep

    def clean_nome(self):
        nome = ' '.join(self.cleaned_data.get('nome').split())
        if len(nome.split()) < 2:
            raise forms.ValidationError('Preencha o seu nome e sobrenome')
        return nome

    def clean(self):
        cleaned_data = super().clean()

        orcid = self.cleaned_data.get('orcid')
        nome = self.cleaned_data.get('nome')

        if orcid and nome and {'orcid', 'nome'} & set(self.changed_data):
            is_valid, error_message = validate_orcid(orcid, nome)

            if not is_valid:
                self.add_error('orcid', error_message)

        return cleaned_data

    class Meta:
        model = Discente
        fields = ("nome", "cpf", "telefone", "cep", "instituicao", "formacao", "orcid")
        error_messages = {
            'cpf': {
                'unique': (
                    'Já existe um discente com este CPF. '
                    'Caso você tenha utilizado um outro email para se registrar, '
                    'clique no botão Voltar do navegador'
                )
            },
            'orcid': {
                'unique': 'Já existe um discente com este ORCID'
            }
        }


class ConfirmaPresencaForm(forms.Form):
    email = forms.EmailField(
        label='Email',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        }),
        required=False
    )
    nome = forms.CharField(
        label='Nome',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'email',
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Validação adicional do email
        if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise ValidationError('O endereço de email fornecido é inválido.')
        return email

    def clean(self):
        email = self.cleaned_data.get('email')
        nome = self.cleaned_data.get('nome')
        if not email and not nome:
            raise ValidationError('Preencha o nome ou o email.')
        return super(ConfirmaPresencaForm, self).clean()


class InscricaoCursoForm(forms.Form):
    cursos = forms.ModelMultipleChoiceField(
        queryset=Curso.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label='Cursos Disponíveis para Inscrição',
        help_text='Selecione os cursos que deseja se inscrever',
        required=True
    )

    def __init__(self, *args, **kwargs):
        cursos_relacionados = kwargs.pop('cursos_relacionados', None)
        cursos_marcados = kwargs.pop('cursos_marcados', [])
        super().__init__(*args, **kwargs)

        self.fields[
            'cursos'].queryset = cursos_relacionados if cursos_relacionados is not None else Curso.objects.none()
        self.initial['cursos'] = Curso.objects.filter(id__in=cursos_marcados)


class SessaoSearchForm(forms.Form):
    dia = forms.ChoiceField(required=False)
    trilha__pk = forms.ChoiceField(required=False)
    sessao_trabalho = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        modulo = kwargs.pop('modulo', None)

        super().__init__(*args, **kwargs)

        if modulo:
            self.fields['dia'].choices = modulo.modulotrilha_set.sessao_dias()
            self.fields['trilha__pk'].choices = modulo.modulotrilha_set.trilhas()

    def clean_dia(self):
        valor = self.cleaned_data['dia']

        try:
            return date.fromisoformat(valor)
        except ValueError:
            raise forms.ValidationError("Data inválida.")


class AgendaForm(forms.Form):
    """
    Form utilizado para validar as informações de entrada e salvar o contato nas marcações feitas na sessão com base
    no cookie do usuário.
    """
    email = forms.EmailField(required=True)
    cookie = forms.CharField(max_length=64)
    modulo = forms.IntegerField()

    def clean(self):
        """Valida as informações de entrada e adiciona os erros no campo e-mail, que é o único visível no frontend."""
        cleaned_data = super().clean()

        email = cleaned_data.get('email')
        cookie = cleaned_data.get('cookie')
        modulo = cleaned_data.get('modulo')

        if not cookie:
            self.add_error(
                'email',
                'Sua sessão expirou ou não pôde ser identificada. '
                'Tente recarregar a página e adicionar um item à agenda novamente.'
            )

        if email and cookie and modulo:
            if not ContatoAgenda.objects.filter(cookie=cookie, sessao__trilha__modulo__pk=modulo).exists():
                self.add_error('email', 'Você precisa adicionar pelo menos um item à sua agenda antes de salvá-la')

        return cleaned_data

    def save(self):
        """
        Atualiza o contato nos itens de ContatoAgenda do cookie do usuário e o módulo indicado.
        Envia e-mail com o link da agenda.
        """
        email = self.cleaned_data.get('email')
        cookie = self.cleaned_data.get('cookie')
        modulo = self.cleaned_data.get('modulo')

        contato = Contato.objects.filter(email=email).first()

        if contato is None:
            contato = Contato.objects.create(email=email)

        ContatoAgenda.objects.filter(cookie=cookie, sessao__trilha__modulo__pk=modulo).update(contato=contato)

        modulo = Modulo.objects.get(pk=modulo)

        engine = engines['django']
        template = engine.from_string(
            '<html>'
            '<head></head>'
            '<body>'
            '<p>Clique aqui para acessar a sua agenda personalizada!</p><br/>'
            '<a href="{{ domain }}{% url \'sessions_with_token\' slug token %}">Sua agenda</a>'
            '</body>'
            '</html>'
        )
        context = {'domain': settings.SITE_URL, 'slug': modulo.slug, 'token': cookie}

        sendmail(f'Sua agenda personalizada para {modulo}', [email], message=template.render(context))

class ListaInteresseForm(forms.ModelForm):
    emails = forms.CharField(
        label='Adicionar contatos',
        required=False,
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text=('Cole emails separados por vírgula. Ex.: nome@email.com, Meu Nome meunome@email.com'),
    )

    class Meta:
        model = ListaInteresse
        fields = '__all__'
