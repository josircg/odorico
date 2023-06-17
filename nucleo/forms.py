import json

from bs4 import BeautifulSoup
from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV3
from crispy_forms.bootstrap import InlineField
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Row, HTML, Div
from django import forms
from django.conf import settings
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.template.defaultfilters import capfirst
from django.urls import reverse
from django.utils.translation import ugettext as _
from django_select2 import forms as s2forms

from . import similaridade
from .apps import normalize_name, get_doi_record, doi_record_to_producao, clean_id_cnpq
from .crispy_admin_layout import AdminFieldset, AdminSubmitRow, AdminField
from .models import ProjetoPesquisa, RelatorioAnual, Pesquisador, Producao, ProducaoAutor


class PeriodicoWidget(s2forms.ModelSelect2Widget):
    search_fields = ['nome__icontains', 'issn__icontains']

    def build_attrs(self, base_attrs, extra_attrs=None):
        extra_attrs = {'data-minimum-input-length': 5, 'data-placeholder': 'Preencha ao menos 5 caracteres ou o ISSN'}
        return super().build_attrs(base_attrs, extra_attrs)


def converter_texto(texto):
    uploaded_file = texto
    str_text = ''
    for line in uploaded_file:
        try:
            str_text = str_text + line.decode()  # "str_text" will be of `str` type
        except:
            str_text = str_text + line.decode('iso-8859-1')  # "str_text" will be of `str` type
    # do something
    return str_text


def test_html_lattes(html):
    soup = BeautifulSoup(html, 'html.parser')
    if not soup.find('h2', attrs={'class': "nome"}):
        raise forms.ValidationError("Nenhum HTML encontrado")
    return True


def test_xml_lattes(html):
    soup = BeautifulSoup(html, 'lxml',
                         from_encoding='ISO-8859-1')
    if not soup.find('xml', attrs={'class': "nome"}):
        raise forms.ValidationError("Nenhum HTML encontrado")
    return True


class ImportForm(forms.Form):
    arquivo_zip = forms.FileField(label='Arquivo ZIP', widget=forms.ClearableFileInput(attrs={'accept': '.zip'}),
                                  required=False)
    arquivo_xml = forms.FileField(label='Arquivo XML', widget=forms.ClearableFileInput(attrs={'accept': '.xml'}),
                                  required=False)

    def __init__(self, *args, **kwargs):
        has_hash = kwargs.pop('has_hash', False)

        super().__init__(*args, **kwargs)
        self.helper = FormHelper()

        if has_hash:
            post_buttons = (Submit('submit', 'Importar'),)
        else:
            post_buttons = (
                Div(Submit('submit', 'Importar'), css_class="col"),
                Div(HTML('<a href="%s"class="buttonlink">Voltar</a></div>' % reverse('admin:index')), css_class="col")
            )

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('arquivo_zip')),
                Row(AdminField('arquivo_xml')),
            ),
            AdminSubmitRow(*post_buttons)
        )

    def clean_arquivo_xml(self):
        if self.cleaned_data['arquivo_xml']:
            arquivo = self.files['arquivo_xml']
            texto = converter_texto(arquivo)  # converte em str
            # test_xml_lattes(texto)
            return texto


class ProjetoPesquisaForm(forms.ModelForm):
    class Meta:
        model = ProjetoPesquisa
        fields = '__all__'

    def clean_nome(self):
        nome = normalize_name(self.cleaned_data.get('nome').strip())
        return nome

    def clean(self):
        # busca os projetos do proponente e verifica se existe algum projeto com nome similar ao que ele está criando
        if not self.instance.id:
            nome = self.cleaned_data.get('nome')
            proponente = self.cleaned_data.get('proponente')
            for projeto in ProjetoPesquisa.objects.filter(proponente_id=proponente.id):
                if similaridade(projeto.nome, nome):
                    raise forms.ValidationError('O projeto %s já foi cadastrado para esse proponente. Verifique!' %
                                                (nome, proponente))

        return super(ProjetoPesquisaForm, self).clean()


class ImportacaoAnonimaForm(forms.Form):
    xml = forms.FileField(label='Arquivo XML:', widget=forms.ClearableFileInput(attrs={'accept': '.zip,.xml'}))
    captcha = ReCaptchaField('', widget=ReCaptchaV3(attrs={'required_score': 0.85, }))

    def __init__(self, *args, **kwargs):
        super(ImportacaoAnonimaForm, self).__init__(*args, **kwargs)
        if not settings.USE_CAPTCHA:
            self.fields.pop('captcha')


class BaseModelFormOdorico(forms.ModelForm):
    """
    ModelForm com feature de marcação de campos readonly (disabled) e criação de formsets.
    Utilizado em views fora do admin.
    """
    readonly_fields = []
    inlines = []

    def __init__(self, *args, **kwargs):
        # Indica que TODOS os campos do form serão desabilitados
        self.disabled = kwargs.pop('disabled', False)

        super().__init__(*args, **kwargs)

        for f in self.get_readonly_fields():
            self.fields[f].widget.attrs['readonly'] = True

        self.opts = self.Meta.model._meta
        self.helper = FormHelper()
        self.helper.form_tag = False

    def get_readonly_fields(self):
        if self.disabled:
            fields = self.fields
        else:
            fields = self.readonly_fields

        return fields

    def clean(self):
        cleaned_data = super().clean()
        # Hack: Remove os campos não editáveis de cleaned_data, para não alterar o conteúdo original, caso alguém
        # tenha hackeado o POST e alterado o conteúdo.
        for f in self.get_readonly_fields():
            if f in self.changed_data:
                cleaned_data.pop(f, None)

        return cleaned_data

    def get_inline_instances(self):
        for inline in self.inlines:
            yield inline()

    def get_formsets(self, request, obj):
        formsets = []
        inline_instances = []

        for inline in self.get_inline_instances():
            can_delete = inline.can_delete and not self.disabled
            extra = inline.extra if not self.disabled else 0
            max_num = inline.max_num if not self.disabled else 0

            formset_cls = inlineformset_factory(self.Meta.model, inline.model, form=inline.form, formset=inline.formset,
                                                extra=extra, max_num=max_num, fields=inline.fields,
                                                can_delete=can_delete)

            formset_params = {
                'instance': obj,
                'queryset': inline.get_queryset(request),
                'form_kwargs': {'disabled': self.disabled},
                'prefix': inline.prefix
            }

            if request.method == 'POST':
                formset_params.update({
                    'data': request.POST.copy(),
                    'files': request.FILES,
                })

            formsets.append(formset_cls(**formset_params))
            inline_instances.append(inline)

        return formsets, inline_instances

    def get_formsets_with_inlines(self, request, formsets, inline_instances):
        return zip(formsets, inline_instances)


class InlineOdorico:
    """Classe para configurar os formsets"""
    model = None
    form = BaseModelFormOdorico
    can_delete = True
    extra = 0
    max_num = 999
    formset = BaseInlineFormSet
    fields = None
    order = []
    verbose_name = None
    verbose_name_plural = None
    template = 'partials/table_inline_formset.html'

    def __init__(self):
        if self.model is None:
            self.model = self.form.Meta.model

        self.opts = self.model._meta

        self.prefix = self.__class__.__name__.lower()

        if self.verbose_name is None:
            self.verbose_name = self.model._meta.verbose_name

        if self.verbose_name_plural is None:
            self.verbose_name_plural = self.model._meta.verbose_name_plural

    def inline_formset_data(self):
        verbose_name = self.opts.verbose_name

        return json.dumps({
            'name': '#%s' % self.prefix,
            'options': {
                'prefix': self.prefix,
                'addText': _('Add another %(verbose_name)s') % {
                    'verbose_name': capfirst(verbose_name),
                },
                'deleteText': _('Remove'),
            }
        })

    def get_ordering(self, request):
        return self.order

    def get_queryset(self, request):
        qs = self.model._default_manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class RelatorioAnualForm(BaseModelFormOdorico):
    """Form que utiliza a lib crispy-forms com as classes de css do admin do django"""

    class Meta:
        model = RelatorioAnual
        fields = (
            'tipo_bolsa', 'descr_bolsa', 'desenvolvimento', 'disciplinas', 'grupo_estudo', 'grupo_pesquisa',
            'part_pesquisa', 'part_extensao', 'part_outras', 'part_discente', 'part_movimento', 'seminarios',
            'premios', 'outras_atividades'
        )
        widgets = {
            'desenvolvimento': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 1000}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.disabled:
            post_button = Submit('_retornar', 'Retornar')
        else:
            post_button = Submit('submit', 'Gravar')

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('desenvolvimento')),
                Row(AdminField('disciplinas')),
                Row(AdminField('tipo_bolsa'), AdminField('descr_bolsa')),
                Row(AdminField('grupo_estudo'), AdminField('grupo_pesquisa')),
                Row(AdminField('part_pesquisa'), AdminField('part_extensao')),
                Row(AdminField('part_outras'), AdminField('part_discente')),
                Row(AdminField('part_movimento'), AdminField('seminarios')),
                Row(AdminField('premios'), AdminField('outras_atividades')),
            ),
            AdminSubmitRow(post_button),
        )


class RelatorioSandwichForm(BaseModelFormOdorico):
    """Form que utiliza a lib crispy-forms com as classes de css do admin do django"""

    class Meta:
        model = RelatorioAnual
        fields = (
            'sandwich_universidade', 'sandwich_periodo', 'sandwich_bolsa', 'sandwich_descricao',
        )
        widgets = {
            'sandwich_descricao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 1000}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.disabled:
            post_buttons = AdminSubmitRow(Submit('_retornar', 'Retornar'))
        else:
            post_buttons = AdminSubmitRow(Submit('submit', 'Gravar'), Submit('_retornar', 'Retornar'))

        self.helper.layout = Layout(
            AdminFieldset(
                'Doutorado Sandwich',
                Row(AdminField('sandwich_universidade')),
                Row(AdminField('sandwich_periodo')),
                Row(AdminField('sandwich_bolsa')),
                Row(AdminField('sandwich_descricao'))
            ),
            post_buttons,
        )


class RelatorioCadastroForm(BaseModelFormOdorico):
    """Form que utiliza a lib crispy-forms com as classes de css do admin do django"""
    readonly_fields = ('nome', 'CPF', 'email')

    class Meta:
        model = Pesquisador
        fields = ('nome', 'CPF', 'email', 'email_alternativo', 'sexo', 'orcid')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.disabled:
            post_button = Submit('_retornar', 'Retornar')
        else:
            post_button = Submit('submit', 'Gravar')

        if self.instance.orcid is None:
            self.fields['orcid'].help_text = (
                '<a href="https://info.orcid.org/pt/documentation/features/orcid-registry/" target="_blank">'
                'Como cadastrar o seu ORCID</a></div>'
            )

        self.helper.layout = Layout(
            AdminFieldset(
                'Dados Gerais',
                Row(AdminField('nome'), AdminField('CPF'), AdminField('email')),
                Row(AdminField('email_alternativo'), AdminField('sexo'), AdminField('orcid', )),
            ),
            AdminSubmitRow(post_button),
        )


class RelatorioAprovacaoForm(BaseModelFormOdorico):
    class Meta:
        model = RelatorioAnual
        fields = ('comentario_orientador',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Aprovação do Relatório',
                Row(AdminField('comentario_orientador')),
            ),
            AdminSubmitRow(
                Submit('_aprovar', 'Aprovar'),
                Submit('_ajustes', 'Solicitar Ajustes')
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        comentario_orientador = cleaned_data.get('comentario_orientador')

        if '_ajustes' in self.data and not comentario_orientador:
            self.add_error(
                'comentario_orientador', self.fields['comentario_orientador'].default_error_messages['required']
            )

        return cleaned_data


class ProducaoAutorForm(BaseModelFormOdorico):
    class Meta:
        model = ProducaoAutor
        fields = ('autor', 'nome', 'ordem')
        widgets = {
            'autor': s2forms.ModelSelect2Widget(model=Pesquisador, search_fields=['nome__icontains'],
                                                attrs={'data-minimum-input-length': 5})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['autor'].help_text = 'Preencha ao menos 5 caracteres ou o ISSN'


class ProducaoAutorFormSet(BaseInlineFormSet):

    def __init__(self, data=None, files=None, instance=None, save_as_new=False, prefix=None, queryset=None, **kwargs):
        # Inicializa o inline com uma linha com o pesquisador como autor
        add_initial = instance is not None and not instance.pk and instance.pesquisador_id

        if add_initial:
            kwargs.update({'initial': [{'autor': instance.pesquisador_id, 'ordem': 0}]})
            self.extra = 1

        super().__init__(data, files, instance, save_as_new, prefix, queryset, **kwargs)


class ProducaoAutorInline(InlineOdorico):
    order = ['ordem']
    form = ProducaoAutorForm
    formset = ProducaoAutorFormSet
    verbose_name = 'Autor da Produção'
    verbose_name_plural = 'Autores da Produção'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('autor', 'producao')


class LivroForm(BaseModelFormOdorico):
    inlines = [ProducaoAutorInline]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'doi', 'isbn', 'tipo_obra', 'ano',
            'natureza_obra', 'meio', 'organizacao', 'serie', 'editora', 'cidade', 'pais',
            'idioma', 'sem_projeto', 'projeto', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200}),
            'organizacao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        submit_row = AdminSubmitRow(Submit('_retornar', 'Retornar'))

        if not self.disabled:
            submit_row.fields.insert(0, Submit('submit', 'Gravar'))

        self.helper.layout = Layout(
            AdminFieldset(
                'Edição de livro ou capítulo de livro',
                Row(AdminField('titulo')),
                Row(AdminField('doi'), AdminField('isbn'), AdminField('ano'), ),
                Row(AdminField('natureza_obra'), AdminField('meio'), AdminField('tipo_obra')),
                Row(AdminField('organizacao'), ),
                Row(AdminField('editora'), AdminField('cidade'), AdminField('pais')),
                Row(AdminField('serie'), AdminField('idioma')),
                # Hack para deixar o checkbox parecido com o admin (input dentro do label) e ao lado do próximo
                # controle
                Row(InlineField('sem_projeto', wrapper_class='fieldBox'), AdminField('projeto')),
                Row(AdminField('comprovante'), )
            ),
        )

        self.submit_helper = FormHelper()
        self.submit_helper.form_tag = False
        self.submit_helper.layout = Layout(submit_row)


class ArtigoForm(BaseModelFormOdorico):
    inlines = [ProducaoAutorInline]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'doi', 'ano',
            'periodico', 'volume', 'serie', 'pais',
            'natureza_obra', 'meio',
            'idioma', 'sem_projeto', 'projeto', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200}),
            'periodico': PeriodicoWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        submit_row = AdminSubmitRow(Submit('_retornar', 'Retornar'))

        if not self.disabled:
            submit_row.fields.insert(0, Submit('submit', 'Gravar'))

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('titulo')),
                Row(AdminField('doi'), AdminField('ano'), ),
                Row(AdminField('periodico'), AdminField('volume'), AdminField('serie'), ),
                Row(AdminField('idioma'), AdminField('pais')),
                Row(AdminField('natureza_obra'), AdminField('meio'), ),
                Row(InlineField('sem_projeto', wrapper_class='fieldBox'), AdminField('projeto')),
                Row(AdminField('comprovante'), )
            ),
        )

        self.submit_helper = FormHelper()
        self.submit_helper.layout = Layout(submit_row)


class ProducaoGenericaForm(BaseModelFormOdorico):
    inlines = [ProducaoAutorInline]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'doi', 'ano',
            'natureza_obra', 'meio', 'idioma',
            'editora', 'cidade', 'pais',
            'sem_projeto', 'projeto', 'comprovante',
            'periodico'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200}),
            'periodico': PeriodicoWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        submit_row = AdminSubmitRow(Submit('_retornar', 'Retornar'))

        if not self.disabled:
            submit_row.fields.insert(0, Submit('submit', 'Gravar'))

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('titulo')),
                Row(AdminField('doi'), AdminField('ano'), ),
                Row(AdminField('natureza_obra'), AdminField('meio'), AdminField('idioma')),
                Row(AdminField('editora'), AdminField('cidade'), AdminField('pais')),
                Row(AdminField('projeto'), InlineField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('periodico')),
                Row(AdminField('comprovante'))
            )
        )

        self.submit_helper = FormHelper()
        self.submit_helper.layout = Layout(submit_row)


class SelecionaProducaoForm(BaseModelFormOdorico):
    """Form para selecionar o tipo de produção que será registrada"""

    class Meta:
        model = Producao
        fields = ('tipo', 'doi')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['tipo'].help_text = 'Selecione o tipo de produção'

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('tipo'), AdminField('doi'))
            ),
            AdminSubmitRow(Submit('submit', 'Adicionar Produção'))
        )

    def clean_doi(self):
        data = self.cleaned_data['doi']

        if data is not None:
            dct = get_doi_record(data)

            if not dct:
                raise forms.ValidationError('DOI inválido')
            else:
                dct = doi_record_to_producao(data, dct)
        else:
            dct = {}

        return dct


def get_producao_form(tipo):
    """Retorna o formulário de acordo com o cod_externo do tipo de produção"""
    chave = tipo.cod_externo.lower()

    if chave in ('livroscapitulos', 'capituloslivrospublicados'):
        form_class = LivroForm
    elif chave == 'artigo':
        form_class = ArtigoForm
    else:
        form_class = ProducaoGenericaForm

    return form_class


class PesquisadorForm(forms.ModelForm):
    """Form utilizado no admin"""

    def clean_nome(self):
        """Utilizada a função clean_id_cnpq, que remove os espaços entre o nome"""
        return clean_id_cnpq(self.cleaned_data.get('nome'))

    def clean_id_cnpq(self):
        return clean_id_cnpq(self.cleaned_data.get('id_cnpq'))


class PesquisadorProgramaForm(forms.ModelForm):

    def clean(self):
        cleaned_data = super().clean()

        pesquisador = cleaned_data.get('pesquisador')
        programa = cleaned_data.get('programa')

        if programa.pesquisadorprograma_set.filter(pesquisador__nome=pesquisador.nome). \
                exclude(pesquisador__pk=pesquisador.pk).exists():
            raise forms.ValidationError(
                f'Outro pesquisador com nome {pesquisador.nome} está associado ao programa {programa}'
            )

        return cleaned_data


class ProfessorLinhaForm(forms.ModelForm):

    def clean(self):
        cleaned_data = super().clean()

        professor = cleaned_data.get('professor')
        linha = cleaned_data.get('linha')

        if linha.professorlinha_set.filter(professor__nome=professor.nome). \
                exclude(professor__pk=professor.pk).exists():
            raise forms.ValidationError(
                f'Outro professor com nome {professor.nome} está associado à esta linha de pesquisa'
            )

        return cleaned_data
