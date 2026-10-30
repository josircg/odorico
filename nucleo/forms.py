import json

from bs4 import BeautifulSoup
# from captcha.fields import ReCaptchaField
# from captcha.widgets import ReCaptchaV3
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Div, Field, HTML, Layout, Row, Submit
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.validators import EMPTY_VALUES
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.template.defaultfilters import capfirst
from django.utils.translation import ugettext as _
from django_select2 import forms as s2forms

from utils.fields import validate_orcid
from . import clean_doi_url, similaridade
from .apps import (clean_orcid, clean_texto, doi_record_to_producao, get_doi_record, normalize_name, save_doi,
                   validate_id_cnpq)
from .crispy_admin_layout import AdminField, AdminFieldset, AdminSubmitRow
from .models import *

TRUE_FALSE_CHOICES = (
    (None, '-'),
    (True, 'Sim'),
    (False, 'Não')
)


class PeriodicoWidget(s2forms.ModelSelect2Widget):
    search_fields = ['nome__icontains', 'issn__icontains']

    def build_attrs(self, base_attrs, extra_attrs=None):
        extra_attrs = {'data-minimum-input-length': 5,
                       'data-placeholder': 'Preencha ao menos 5 caracteres ou o ISSN'}
        return super().build_attrs(base_attrs, extra_attrs)


def converter_texto(texto):
    uploaded_file = texto
    str_text = ''
    for line in uploaded_file:
        try:
            str_text = str_text + line.decode()  # "str_text" will be of `str` type
        except:
            # "str_text" will be of `str` type
            str_text = str_text + line.decode('iso-8859-1')
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
                Div(HTML('<a href="%s"class="buttonlink">Voltar</a></div>' %
                         reverse('admin:index')), css_class="col")
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
            if proponente:
                for projeto in ProjetoPesquisa.objects.filter(proponente_id=proponente.id):
                    if similaridade(projeto.nome, nome):
                        raise forms.ValidationError(
                            f'O projeto {nome} já foi cadastrado para esse proponente. Verifique!')

        return super(ProjetoPesquisaForm, self).clean()


class ImportacaoAnonimaForm(forms.Form):
    xml = forms.FileField(label='Arquivo XML ou ZIP', widget=forms.ClearableFileInput(
        attrs={'accept': '.zip,.xml'}))

    # captcha = ReCaptchaField('', widget=ReCaptchaV3(attrs={'required_score': 0.85, }))

    def __init__(self, *args, **kwargs):
        super(ImportacaoAnonimaForm, self).__init__(*args, **kwargs)
        # if not settings.USE_CAPTCHA:
        #     self.fields.pop('captcha')


class BaseModelFormOdorico(forms.ModelForm):
    """
    ModelForm com feature de marcação de campos readonly (disabled) e criação de formsets.
    Utilizado em views fora do admin.
    """
    readonly_fields = []
    inlines = []
    # Indicar os campos que não são obrigatórios por default. Evita redefinir os campos no form.
    required = []

    def __init__(self, *args, **kwargs):
        # Indica que TODOS os campos do form serão desabilitados
        self.disabled = kwargs.pop('disabled', False)

        super().__init__(*args, **kwargs)

        for f in self.required:
            self.fields[f].required = True

        for f in self.get_readonly_fields():
            # Campos que são do tipo Select ou SelectMultiple, retorna apenas as escolhas selecionadaa pelo usuário,
            # pois o atributo readonly não funciona com input do tipo Select
            if isinstance(self.fields[f].widget, (forms.Select, forms.SelectMultiple)):
                if self.instance.pk:
                    # Retorna o campo do model e testa o tipo dele para definir as choices ou queryset
                    field = self.instance._meta.get_field(f)
                    # Retorna o valor atual do campo
                    value = getattr(self.instance, f)

                    if isinstance(field, (models.ForeignKey, models.ManyToManyRel)):
                        if value is not None:
                            if isinstance(field, models.ForeignKey):
                                self.fields[f].queryset = value.__class__.objects.filter(
                                    pk=value.pk)
                            else:
                                self.fields[f].queryset = value.all()
                        else:
                            self.fields[f].queryset = field.remote_field.model._default_manager.none()
                    else:
                        self.fields[f].widget.choices = [
                            (value, dict(self.fields[f].widget.choices).get(value, ''))]

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
            'premios', 'outras_atividades', 'curso_anterior', 'impacto_pp', 'impacto_gestao',
            'impacto_educacao', 'impacto_projetos', 'impacto_empresarial',
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
                Row(AdminField('disciplinas'), AdminField(
                    'curso_anterior', wrapper_class='vLargeFieldBox')),
                Row(AdminField('tipo_bolsa'), AdminField('descr_bolsa')),
                Row(AdminField('grupo_estudo'), AdminField(
                    'grupo_pesquisa', wrapper_class='vLargeFieldBox')),
                Row(
                    AdminField('part_pesquisa',
                               wrapper_class='vLargeFieldBox'),
                    AdminField('part_extensao', wrapper_class='vLargeFieldBox')
                ),
                Row(
                    AdminField('part_outras', wrapper_class='vLargeFieldBox'),
                    AdminField('part_discente', wrapper_class='vLargeFieldBox')
                ),
                Row(AdminField('part_movimento',
                               wrapper_class='vLargeFieldBox'), AdminField('seminarios')),
            ),
            AdminFieldset(
                'Impacto Social',
                Row(
                    AdminField('impacto_pp', wrapper_class='vLargeFieldBox'),
                    AdminField('impacto_gestao', wrapper_class='vLargeFieldBox')
                ),
                Row(AdminField('impacto_educacao'),
                    AdminField('impacto_projetos', wrapper_class='vLargeFieldBox')),
                Row(AdminField('impacto_empresarial', wrapper_class='vLargeFieldBox')),
                Row(AdminField('premios'),
                    AdminField('outras_atividades', wrapper_class='vLargeFieldBox')),
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
            post_buttons = AdminSubmitRow(
                Submit('submit', 'Gravar'), Submit('_retornar', 'Retornar'))

        self.helper.layout = Layout(
            AdminFieldset(
                'Só preencha caso você tenha realizado Doutorado Sandwiche',
                Row(AdminField('sandwich_universidade')),
                Row(AdminField('sandwich_periodo')),
                Row(AdminField('sandwich_bolsa')),
                Row(AdminField('sandwich_descricao'))
            ),
            post_buttons,
        )

    def possui_campo_preenchido(self):
        """Retorna True para qualquer campo preenchido"""
        return any(self.cleaned_data[f] not in EMPTY_VALUES for f in self.cleaned_data)


class RelatorioCadastroForm(BaseModelFormOdorico):
    """Form que utiliza a lib crispy-forms com as classes de css do admin do django"""
    readonly_fields = ('nome', 'email',)
    required = ('orcid',)

    class Meta:
        model = Pesquisador
        fields = ('nome', 'email',
                  'email_alternativo', 'sexo', 'orcid',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.disabled:
            post_button = Submit('_retornar', 'Retornar')
        else:
            post_button = Submit('submit', 'Gravar')

        if self.instance.orcid is None:
            self.fields['orcid'].help_text = (
                '<a href="https://www.ufmg.br/prpq/wp-content/uploads/2018/02/CriarperfilnoORCID_2017_05_26.pdf" target="_blank">'
                'Como cadastrar o seu ORCID</a></div>'
            )

        self.helper.layout = Layout(
            AdminFieldset(
                'Dados Gerais',
                Row(AdminField('nome'), AdminField('email')),
                Row(AdminField('email_alternativo'),
                    AdminField('sexo'), AdminField('orcid', )),
            ),
            AdminSubmitRow(post_button),
        )

    def clean_orcid(self):
        orcid = self.cleaned_data.get('orcid').split('/')[-1]
        return orcid

    def clean(self):
        cleaned_data = super().clean()

        orcid = self.cleaned_data.get('orcid')
        nome = self.cleaned_data.get('nome')

        if orcid and nome and {'orcid', 'nome'} & set(self.changed_data):
            is_valid, error_message = validate_orcid(orcid, nome)

            if not is_valid:
                self.add_error('orcid', error_message)

        return cleaned_data


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
            kwargs.update(
                {'initial': [{'autor': instance.pesquisador_id, 'ordem': 0}]})
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


class BaseProducaoForm(BaseModelFormOdorico):
    inlines = [ProducaoAutorInline]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        submit_row = AdminSubmitRow()

        if not self.disabled:
            submit_row.fields.insert(0, Submit('submit', 'Gravar'))

            if self.instance.pk and not self.disabled:
                try:
                    relatorio = RelatorioAnual.objects.get(
                        pesquisador=self.instance.pesquisador_id, ano=self.instance.ano
                    )
                    delete_url = reverse('deletar_producao',
                                         kwargs={'hash_auth': relatorio.hash_auth, 'hash_producao': self.instance.pk})
                    submit_row.append(
                        HTML(f'<p class="deletelink-box"><a href="{delete_url}" class="deletelink">Apagar</a></p>')
                    )
                except RelatorioAnual.DoesNotExist:
                    pass

        self.submit_helper = FormHelper()
        self.submit_helper.form_tag = False
        self.submit_helper.layout = Layout(submit_row)

    def filter_choices(self, *args, **kwargs):
        return

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.validacao = Producao.Status.VALIDADO
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class MidiaImpressaForm(BaseProducaoForm):
    required = ['editora', 'titulo', 'dt_publicacao',
                'natureza_conteudo', 'meio', 'idioma',
                'nivel_impacto', 'tipo_impacto', 'complexidade', 'abrangencia', 'area_impacto',
                'tipo_financiamento', 'relacao_tese',
                'cidade', 'comprovante']

    class Meta:
        model = Producao
        fields = (
            'editora', 'titulo', 'dt_publicacao', 'pagina_inicial', 'pagina_final',
            'cidade', 'pais',
            'meio', 'natureza_conteudo', 'nivel_impacto', 'tipo_impacto', 'area_impacto', 'complexidade',
            'abrangencia', 'setor',
            'tipo_financiamento',
            'idioma', 'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Artigos em Jornais e Revistas',
                Row(AdminField('editora')),
                Row(AdminField('titulo')),
                Row(AdminField('dt_publicacao'), AdminField('pagina_inicial'), AdminField('pagina_final'), ),
                Row(AdminField('natureza_conteudo'), AdminField('meio'), ),
                Row(AdminField('idioma'), AdminField('cidade'), AdminField('pais')),
                Row(AdminField('nivel_impacto'), AdminField('tipo_impacto'), AdminField('complexidade'),
                    AdminField('area_impacto'), AdminField('abrangencia'), ),
                Row(AdminField('setor'), ),
                Row(AdminField('tipo_financiamento', )),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_conteudo'].choices:
            if item[0] not in (Producao.NaturezaConteudo.ESPECIALIZACAO,
                               Producao.NaturezaConteudo.APERFEICOAMENTO,
                               Producao.NaturezaConteudo.EXTENSAO):
                filtered.append(item)
        self.fields['natureza_conteudo'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['editora'].label = 'Nome do Jornal ou Revista'
        self.fields['editora'].widget.attrs["style"] = "width:40em"


class CapituloForm(BaseProducaoForm):
    required = ['titulo_colecao', 'titulo', 'tipo_obra',
                'natureza_conteudo', 'meio', 'serie', 'idioma',
                'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto',
                'num_paginas', 'tipo_financiamento',
                'editora', 'cidade', 'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo_colecao', 'titulo', 'isbn', 'doi', 'tipo_obra',
            'natureza_conteudo', 'meio', 'organizacao', 'serie', 'editora', 'cidade', 'pais',
            'tipo_financiamento', 'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto', 'num_paginas',
            'idioma',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'titulo_colecao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'organizacao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Edição de Capítulo de livro',
                Row(AdminField('titulo_colecao')),
                Row(AdminField('titulo')),
                Row(AdminField('isbn'), AdminField('doi'), ),
                Row(AdminField('natureza_conteudo'), AdminField('tipo_obra'), AdminField('meio')),
                Row(AdminField('serie'), AdminField('num_paginas'), AdminField('idioma')),
                Row(AdminField('organizacao'), ),
                Row(AdminField('editora'), AdminField('tipo_financiamento')),
                Row(AdminField('cidade'), AdminField('pais')),
                Row(AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('abrangencia'), AdminField('area_impacto')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['tipo_obra'].choices:
            if item[0] not in (Producao.TipoObra.COMPLETO, '1', '2', '3', '4', '6', '7', 'D'):
                filtered.append(item)
        self.fields['tipo_obra'].choices = sorted(filtered, key=lambda k: k[1])

        filtered = []
        for item in self.fields['natureza_conteudo'].choices:
            if item[0] not in (Producao.NaturezaConteudo.ESPECIALIZACAO,
                               Producao.NaturezaConteudo.APERFEICOAMENTO,
                               Producao.NaturezaConteudo.EXTENSAO):
                filtered.append(item)
        self.fields['natureza_conteudo'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['titulo'].label = 'Título do Capítulo'


class LivroForm(BaseProducaoForm):
    required = ['titulo', 'natureza_texto', 'natureza_obra', 'natureza_conteudo', 'tipo_financiamento',
                'meio', 'idioma', 'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto',
                'tipo_editora', 'editora', 'conselho_editorial',
                'natureza_texto', 'leitor_preferencial', 'origem_grupo',
                'cidade', 'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo', 'doi', 'isbn',
            'tipo_editora', 'editora',
            'natureza_texto', 'natureza_obra', 'natureza_conteudo', 'meio', 'cidade', 'pais',
            'tipo_financiamento', 'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto', 'num_paginas',
            'conselho_editorial', 'reedicao', 'reimpressao',
            'info_autores', 'revisao_pares', 'indice_remissivo', 'traducao',
            'premiacao', 'natureza_texto', 'natureza_texto_obs', 'leitor_preferencial', 'leitor_preferencial_obs',
            'origem_grupo', 'tipo_obra',
            'idioma', 'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'organizacao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'natureza_texto_obs': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'leitor_preferencial_obs': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Edição de Livro',
                Row(AdminField('titulo')),
                Row(AdminField('doi'), AdminField('isbn'), ),
                Row(AdminField('natureza_obra'), AdminField('natureza_conteudo')),
                Row(AdminField('num_paginas'),
                    AdminField('reedicao', wrapper_class='fieldBox'),
                    AdminField('reimpressao', wrapper_class='fieldBox'), ),
                Row(AdminField('tipo_editora'), AdminField('editora'), AdminField('conselho_editorial')),
                Row(AdminField('idioma'), AdminField('cidade'), AdminField('pais')),
                Row(AdminField('meio'), AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('abrangencia'), AdminField('area_impacto')),
                Row(AdminField('info_autores', wrapper_class='fieldBox')),
                Row(AdminField('revisao_pares', wrapper_class='fieldBox')),
                Row(AdminField('indice_remissivo', wrapper_class='fieldBox')),
                Row(AdminField('traducao', wrapper_class='fieldBox')),
                Row(AdminField('premiacao')),
                Row(AdminField('natureza_texto')),
                Row(AdminField('natureza_texto_obs')),
                Row(AdminField('leitor_preferencial')),
                Row(AdminField('leitor_preferencial_obs')),
                Row(AdminField('origem_grupo')),
                Row(AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', 'O', 'C', 'L', 'N', 'D', 'E'):
                filtered.append(item)
        self.fields['natureza_obra'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['tipo_obra'].initial = Producao.TipoObra.COMPLETO


class TraducaoForm(BaseProducaoForm):
    required = [
        'titulo', 'ano', 'natureza_obra',
        'titulo_colecao', 'organizacao', 'serie', 'idioma', 'num_paginas',
        'editora', 'cidade', 'pais',
        'meio', 'nivel_impacto', 'tipo_impacto', 'complexidade', 'setor', 'tipo_financiamento',
        'comprovante'
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'ano', 'natureza_obra',
            'titulo_colecao', 'organizacao', 'serie', 'idioma', 'num_paginas',
            'editora', 'cidade', 'pais',
            'meio', 'nivel_impacto', 'tipo_impacto', 'complexidade', 'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'doi', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'titulo_colecao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'organizacao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Tradução',
                Row(AdminField('titulo')),
                Row(AdminField('titulo_colecao')),  # título original
                Row(AdminField('organizacao'), ),  # autor original
                Row(AdminField('natureza_obra'), AdminField('ano'),
                    AdminField('serie'), AdminField('idioma'), AdminField('num_paginas')),
                Row(AdminField('editora'), AdminField('cidade'), AdminField('pais'), ),
                Row(AdminField('meio'), AdminField('nivel_impacto'),
                    AdminField('tipo_impacto'), AdminField('complexidade')),
                Row(AdminField('setor')),
                Row(AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese'), ),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('doi'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', Producao.NaturezaObra.ARTIGO, Producao.NaturezaObra.LIVRO, Producao.NaturezaObra.OUTRA):
                filtered.append(item)
        self.fields['natureza_obra'].choices = sorted(filtered, key=lambda k: k[1])

        self.fields['organizacao'].label = 'Autor traduzido'
        self.fields['idioma'].label = 'Idioma da tradução'
        self.fields['serie'].label = 'Idioma original da obra'
        self.fields['titulo_colecao'].label = 'Título Original'
        self.fields['editora'].label = 'Editora da Tradução'
        self.fields['cidade'].label = 'Cidade da Editora'


class AnaisForm(BaseProducaoForm):
    required = [
        'titulo', 'natureza_obra', 'serie', 'organizacao', 'titulo_colecao',
        'volume', 'cidade', 'idioma', 'meio',
        'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo', 'natureza_obra', 'serie', 'organizacao', 'doi', 'isbn', 'pais', 'titulo_colecao',
            'volume', 'pagina_inicial', 'pagina_final', 'cidade', 'idioma', 'meio',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Edição de Trabalho em Anais/Congressos',
                Row(AdminField('titulo')),
                Row(AdminField('natureza_obra'),
                    AdminField('serie')),  # edição/número
                Row(AdminField('organizacao'), ),  # nome do evento
                Row(AdminField('doi'), AdminField('isbn')),
                Row(AdminField('pais'), ),
                Row(AdminField('titulo_colecao')),
                Row(AdminField('volume'), AdminField('pagina_inicial'), AdminField('pagina_final')),
                Row(AdminField('cidade'), AdminField('idioma'), ),
                Row(AdminField('meio')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', 'A', 'R', 'X'):
                filtered.append(item)
        self.fields['natureza_obra'].choices = filtered
        self.fields['natureza_obra'].label = 'Natureza'
        self.fields['serie'].label = 'Edição / Número'
        self.fields['organizacao'].label = 'Nome do Evento'
        self.fields['isbn'].label = 'ISBN/ISSN'
        self.fields['titulo_colecao'].label = 'Título dos Anais'
        self.fields['volume'].label = 'Volume/Fascículo/Série'


class ApresentacaoForm(BaseProducaoForm):
    required = [
        'titulo', 'natureza_obra', 'ano',
        'titulo_colecao', 'organizacao', 'cidade',
        'nivel_impacto', 'tipo_impacto', 'complexidade', 'setor', 'tipo_financiamento',
        'comprovante'
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'natureza_obra', 'ano',
            'titulo_colecao', 'organizacao', 'cidade', 'pais', 'idioma',
            'nivel_impacto', 'tipo_impacto', 'complexidade',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'titulo_colecao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Apresentação de Trabalho em Anais/Congressos',
                Row(AdminField('titulo')),
                Row(AdminField('natureza_obra'), AdminField('ano')),  # edição/número
                Row(AdminField('titulo_colecao'), ),  # nome do evento
                Row(AdminField('organizacao'),  # local do evento
                    AdminField('cidade'), AdminField('pais'), AdminField('idioma'), ),
                Row(AdminField('nivel_impacto'), AdminField('tipo_impacto'), AdminField('complexidade')),
                Row(AdminField('setor'), AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese'), ),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre')),
                Row(AdminField('url')),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', Producao.NaturezaObra.COMUNICACAO,
                           Producao.NaturezaObra.CONFERENCIA, Producao.NaturezaObra.OUTRA,
                           Producao.NaturezaObra.SEMINARIO, Producao.NaturezaObra.CONGRESSO):
                filtered.append(item)
        self.fields['natureza_obra'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['titulo_colecao'].label = 'Nome do Evento'


class OrgEventoForm(BaseProducaoForm):
    required = [
        'titulo', 'natureza_obra', 'tipo_obra', 'ano',
        'num_paginas',
        'editora', 'organizacao', 'cidade', 'idioma',
        'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
        'setor', 'tipo_financiamento',
        'comprovante'
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'natureza_obra', 'tipo_obra', 'ano',
            'num_paginas', 'reedicao', 'indice_remissivo',
            'editora', 'organizacao', 'cidade', 'idioma',
            'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto',
            'complexidade', 'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'organizacao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 100, 'rows': 1}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Organização de Evento',
                Row(AdminField('titulo')),
                Row(AdminField('tipo_obra'), AdminField('natureza_obra'), AdminField('editora'), AdminField('ano'), ),
                Row(AdminField('organizacao'), AdminField('cidade'), AdminField('idioma'), ),
                Row(AdminField('num_paginas'), ),
                Row(AdminField('reedicao', wrapper_class='fieldBox')),
                Row(AdminField('indice_remissivo', wrapper_class='fieldBox')),
                Row(AdminField('abrangencia'), AdminField('area_impacto'),
                    AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('complexidade')),
                Row(AdminField('setor'), AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', Producao.NaturezaObra.CONCERTO, Producao.NaturezaObra.OUTRA,
                           Producao.NaturezaObra.CONCURSO, Producao.NaturezaObra.EXPOSICAO,
                           Producao.NaturezaObra.FESTIVAL, Producao.NaturezaObra.CONGRESSO):
                filtered.append(item)
        self.fields['natureza_obra'].choices = sorted(filtered, key=lambda k: k[1])

        filtered = []
        for item in self.fields['tipo_obra'].choices:
            if item[0] in ('', '1', '2', '3', '4', '5'):
                filtered.append(item)
        self.fields['tipo_obra'].choices = sorted(filtered, key=lambda k: k[1])

        self.fields['titulo'].label = 'Nome do Evento'
        self.fields['natureza_obra'].label = 'Tipo do Evento'
        self.fields['tipo_obra'].label = 'Natureza (Função)'
        self.fields['editora'].label = 'Instituição Promotora'
        self.fields['organizacao'].label = 'Local'
        self.fields['num_paginas'].label = 'Duração (em Dias)'
        self.fields['reedicao'].label = 'Itinerante'
        self.fields['indice_remissivo'].label = 'Catálogo'


class DidaticoForm(BaseProducaoForm):
    required = ['titulo', 'descricao',
                'meio', 'idioma', 'abrangencia',
                'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
                'setor', 'tipo_financiamento',
                'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo', 'descricao',
            'meio', 'pais', 'idioma',
            'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'doi', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'descricao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Desenvolvimento de Material Didático',
                Row(AdminField('titulo')),
                Row(AdminField('descricao'), ),
                Row(AdminField('pais'), AdminField('idioma'), AdminField('abrangencia'), AdminField('meio'), ),
                Row(AdminField('area_impacto'), AdminField('nivel_impacto'),
                    AdminField('tipo_impacto'), AdminField('complexidade'), ),
                Row(AdminField('setor'), AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('doi'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        self.fields['descricao'].label = 'Natureza'


class CursoCurtoForm(BaseProducaoForm):
    required = [
        'titulo', 'descricao', 'natureza_conteudo', 'tipo_obra',
        'num_paginas', 'editora',
        'organizacao', 'cidade',
        'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
        'setor', 'tipo_financiamento',
        'comprovante'
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'descricao', 'natureza_conteudo', 'tipo_obra',
            'num_paginas', 'editora',
            'organizacao', 'cidade', 'pais', 'idioma',
            'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'doi', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'descricao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Curso de Curta Duração',
                Row(AdminField('titulo')),
                Row(AdminField('descricao'), ),
                Row(AdminField('natureza_conteudo'), AdminField('tipo_obra'), ),
                Row(AdminField('num_paginas'), AdminField('editora'), ),
                Row(AdminField('organizacao'), AdminField('cidade'), AdminField('pais'), AdminField('idioma')),
                Row(AdminField('abrangencia'), AdminField('area_impacto'),
                    AdminField('nivel_impacto'), AdminField('tipo_impacto'), AdminField('complexidade'), ),
                Row(AdminField('setor'), AdminField('tipo_financiamento')),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('doi'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_conteudo'].choices:
            if item[0] in ('',
                           Producao.NaturezaConteudo.ESPECIALIZACAO,
                           Producao.NaturezaConteudo.APERFEICOAMENTO,
                           Producao.NaturezaConteudo.EXTENSAO,
                           Producao.NaturezaConteudo.OUTRA):
                filtered.append(item)
        self.fields['natureza_conteudo'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['natureza_conteudo'].label = 'Nível'

        filtered = []
        for item in self.fields['tipo_obra'].choices:
            if item[0] in ('', Producao.TipoObra.DOCENTE, Producao.TipoObra.ORGANIZACAO, Producao.TipoObra.OUTRA):
                filtered.append(item)
        self.fields['tipo_obra'].choices = sorted(filtered, key=lambda k: k[1])
        self.fields['tipo_obra'].label = 'Participação dos Autores'
        self.fields['descricao'].label = 'Natureza'
        self.fields['editora'].label = 'Instituição Promotora'
        self.fields['organizacao'].label = 'Local'
        self.fields['num_paginas'].label = 'Duração'


class EditoriaForm(BaseProducaoForm):
    required = [
        'titulo', 'tipo_obra', 'natureza_obra',
        'idioma', 'num_paginas', 'editora',
        'meio', 'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
        'setor', 'tipo_financiamento',
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'tipo_obra', 'natureza_obra',
            'editora', 'num_paginas',
            'cidade', 'pais', 'idioma',
            'meio', 'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'doi', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Editoria',
                Row(AdminField('titulo')),
                Row(AdminField('tipo_obra'), AdminField('natureza_obra'), ),
                Row(AdminField('editora'), AdminField('idioma'), AdminField('num_paginas'), ),
                Row(AdminField('cidade'), AdminField('pais'), ),
                Row(AdminField('meio'), AdminField('abrangencia'),
                    AdminField('area_impacto'), AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('complexidade'), ),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('doi'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', Producao.NaturezaObra.ANAIS, Producao.NaturezaObra.CATALOGO,
                           Producao.NaturezaObra.COLETANEA, Producao.NaturezaObra.OUTRA,
                           Producao.NaturezaObra.LIVRO, Producao.NaturezaObra.PERIODICO,
                           Producao.NaturezaObra.ENCICLOPEDIA):
                filtered.append(item)
        self.fields['natureza_obra'].choices = sorted(filtered, key=lambda k: k[1])

        filtered = []
        for item in self.fields['tipo_obra'].choices:
            if item[0] in ('', '5', '6', '7',):
                filtered.append(item)
        self.fields['tipo_obra'].choices = sorted(filtered, key=lambda k: k[1])


class ArtigoForm(BaseProducaoForm):
    required = ['periodico', 'volume', 'tipo_obra', 'meio', 'idioma',
                'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto',
                'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo', 'doi', 'ano',
            'periodico', 'volume', 'serie', 'pais',
            'tipo_obra', 'meio',
            'nivel_impacto', 'abrangencia', 'area_impacto', 'tipo_impacto',
            'idioma', 'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante',
            'pagina_inicial', 'pagina_final',
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 3}),
            'periodico': PeriodicoWidget,
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('titulo')),
                Row(AdminField('doi'), AdminField('ano'), ),
                Row(AdminField('periodico'), AdminField('volume'), AdminField('serie'), ),
                Row(AdminField('pagina_inicial'), AdminField('pagina_final')),
                Row(AdminField('idioma'), AdminField('pais')),
                Row(AdminField('tipo_obra'), AdminField('meio'), ),
                Row(AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('abrangencia'), AdminField('area_impacto'), ),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        filtered = []
        for item in self.fields['tipo_obra'].choices:
            if item[0] in ('', Producao.TipoObra.APRESENTACAO, Producao.TipoObra.PREFACIO,
                           Producao.TipoObra.POSFACIO, Producao.TipoObra.OUTRA, Producao.TipoObra.COMPLETO,
                           Producao.TipoObra.RESUMO, Producao.TipoObra.RESUMOX):
                filtered.append(item)
        self.fields['tipo_obra'].choices = filtered


class MidiaEletronicaForm(BaseProducaoForm):
    required = [
        'titulo', 'natureza_obra', 'editora', 'natureza_texto_obs',
        'dt_publicacao', 'num_paginas', 'cidade', 'idioma',
        'meio', 'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
        'setor', 'tipo_financiamento', 'comprovante']

    class Meta:
        model = Producao
        fields = (
            'titulo', 'natureza_obra', 'editora', 'natureza_texto_obs',
            'dt_publicacao', 'num_paginas', 'cidade', 'pais', 'idioma',
            'meio', 'abrangencia', 'area_impacto', 'nivel_impacto', 'tipo_impacto', 'complexidade',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'url', 'comprovante'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'natueza_texto_obs': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            AdminFieldset(
                'Mídia Eletrônica (TV e Rádio)',
                Row(AdminField('titulo')),
                Row(AdminField('natureza_obra'), ),
                Row(AdminField('editora'), AdminField('dt_publicacao'), ),
                Row(AdminField('natureza_texto_obs'), ),
                Row(AdminField('num_paginas'), ),
                Row(AdminField('cidade'), AdminField('pais'), AdminField('idioma'), ),
                Row(AdminField('meio'), AdminField('abrangencia'),
                    AdminField('area_impacto'), AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('complexidade'), ),
                Row(AdminField('setor'), ),
                Row(AdminField('tipo_financiamento'), ),
                Row(AdminField('relacao_tese', wrapper_class='fieldBox')),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'), )
            ),
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        filtered = []
        for item in self.fields['natureza_obra'].choices:
            if item[0] in ('', 'e', 'c', 'm', 'O'):
                filtered.append(item)
        self.fields['natureza_obra'].choices = filtered

        self.fields['natureza_texto_obs'].label = 'Tema'
        self.fields['editora'].label = 'Emissora'
        self.fields['num_paginas'].label = 'Duração'


class ProducaoGenericaForm(BaseProducaoForm):
    required = [
        'titulo', 'descricao', 'ano',
        'tipo_acesso', 'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto', 'complexidade',
        'meio', 'idioma',
        'setor', 'tipo_financiamento',
        'comprovante',
    ]

    class Meta:
        model = Producao
        fields = (
            'titulo', 'descricao', 'doi', 'ano',
            'editora',
            'tipo_acesso', 'nivel_impacto', 'tipo_impacto', 'abrangencia', 'area_impacto', 'complexidade',
            'meio', 'idioma', 'pais',
            'setor', 'tipo_financiamento',
            'relacao_tese', 'sem_projeto', 'projeto_livre', 'comprovante', 'url', 'obs'
        )
        widgets = {
            'titulo': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'descricao': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'url': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 1}),
            'projeto_livre': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
            'relacao_tese': forms.Select(choices=TRUE_FALSE_CHOICES),
            'obs': forms.Textarea(attrs={'style': 'width: 100%', 'cols': 200, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('titulo')),
                Row(AdminField('descricao')),
                Row(AdminField('doi'), AdminField('ano')),
                Row(AdminField('editora')),
                Row(AdminField('tipo_acesso')),
                Row(AdminField('meio'), AdminField('idioma'), AdminField('pais')),
                Row(AdminField('nivel_impacto'), AdminField('tipo_impacto'),
                    AdminField('abrangencia'), AdminField('area_impacto'), AdminField('complexidade'), ),
                Row(AdminField('setor'), AdminField('tipo_financiamento'), ),
                Row(AdminField('relacao_tese', )),
                Row(AdminField('sem_projeto', wrapper_class='fieldBox')),
                Row(AdminField('projeto_livre')),
                Row(AdminField('obs'), ),
                Row(AdminField('url'), ),
                Row(AdminField('comprovante'))
            )
        )

    def filter_choices(self, *args, **kwargs):
        super().filter_choices(*args, **kwargs)
        self.fields['descricao'].label = 'Descrição do Trabalho (Natureza)'
        self.fields['editora'].label = 'Instituição Promotora/Financiadora'


class SelecionaProducaoForm(BaseModelFormOdorico):
    """Form para selecionar o tipo de produção que será registrada"""
    record = {}

    class Meta:
        model = Producao
        fields = ('tipo', 'doi',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['tipo'].help_text = 'Selecione o tipo de produção'
        self.fields['tipo'].queryset = TipoProducao.objects.filter(edicao=True)

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('tipo'), AdminField('doi'))
            ),
            AdminSubmitRow(Submit('submit', 'Adicionar Produção'))
        )

    def clean_doi(self):
        data = clean_doi_url(self.cleaned_data['doi'])

        # obtem os dados do DOI e armazena em self.record
        if data is None:
            self.record = {}
        else:
            result = get_doi_record(data, fast=True)
            if not result:
                raise forms.ValidationError('DOI inválido ou indisponível')

            else:
                self.record = doi_record_to_producao(data, result)
                tipo = self.cleaned_data['tipo']
                if result.get('type') == 'book-chapter' and tipo.cod_externo == 'artigo':
                    raise forms.ValidationError(
                        'O DOI informado é de um capítulo de livro')
                save_doi(data, result)

        return data


def get_producao_form(tipo):
    """Retorna o formulário de acordo com o cod_externo do tipo de produção"""
    chave = tipo.cod_externo.lower()

    if chave == 'livroscapitulos':
        form_class = LivroForm
    elif chave == 'capituloslivrospublicados':
        form_class = CapituloForm
    elif chave in ('artigo', 'artigo-aceito'):
        form_class = ArtigoForm
    elif chave == 'midiaimpressa':
        form_class = MidiaImpressaForm
    elif chave == 'traducao':
        form_class = TraducaoForm
    elif chave == 'anais':
        form_class = AnaisForm
    elif chave == 'editoria':
        form_class = EditoriaForm
    elif chave == 'apresentacao':
        form_class = ApresentacaoForm
    elif chave == 'didatico':
        form_class = DidaticoForm
    elif chave == 'curso':
        form_class = CursoCurtoForm
    elif chave == 'orgevento':
        form_class = OrgEventoForm
    elif chave == 'midiaeletronica':
        form_class = MidiaEletronicaForm
    else:
        form_class = ProducaoGenericaForm

    return form_class


class PesquisadorForm(forms.ModelForm):
    """Form utilizado no admin"""

    def clean_nome(self):
        return clean_texto(self.cleaned_data.get('nome'))

    def clean_id_cnpq(self):
        id_cnpq = self.cleaned_data.get('id_cnpq')

        if 'id_cnpq' in self.changed_data:
            validate_id_cnpq(id_cnpq)

        return id_cnpq

    def clean(self):
        cleaned_data = super().clean()

        orcid = self.cleaned_data.get('orcid')
        nome = self.cleaned_data.get('nome')

        if orcid and nome and {'orcid', 'nome'} & set(self.changed_data):
            is_valid, error_message = validate_orcid(orcid, nome)

            if not is_valid:
                self.add_error('orcid', error_message)

        return cleaned_data


class AlunoForm(PesquisadorForm):
    """Form utilizado no admin"""

    class Meta:
        model = Aluno
        fields = '__all__'
        error_messages = {
            # Sobrescreve a mensagem de erro unique para mostrar o verbose_name do modelo proxy
            'CPF': {
                'unique': f'{Aluno._meta.verbose_name} com este CPF já existe.',
            },
            'orcid': {
                'unique': f'{Aluno._meta.verbose_name} com este ORCID já existe.',
            },
        }


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Somente pesquisadores com Lattes podem ser credenciados na linha. No inline de linhas
        # da/o docente o campo é a FK do pai e não faz parte do form.
        if 'professor' in self.fields:
            queryset = Pesquisador.objects.com_lattes()
            if self.instance.professor_id:
                # Não trava a edição de quem já estava credenciado sem Lattes
                queryset = queryset | Pesquisador.objects.filter(pk=self.instance.professor_id)
            self.fields['professor'].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()

        professor = cleaned_data.get('professor')
        linha = cleaned_data.get('linha')

        if linha and linha.professorlinha_set.filter(professor__nome=professor.nome). \
                exclude(professor__pk=professor.pk).exists():
            raise forms.ValidationError(
                f'O professor {professor.nome} já está associado à esta linha de pesquisa'
            )

        return cleaned_data


class BuscaOrientadorForm(forms.Form):
    email = forms.EmailField(label='E-mail do Orientador')
    programa = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('email')),
            ),
            AdminSubmitRow(Submit('submit', 'Buscar'))
        )

    def clean(self):
        cleaned_data = super().clean()

        email = cleaned_data.get('email')

        if email not in EMPTY_VALUES:
            try:
                self.professor = Professor.objects.get(email=email)
            except Professor.DoesNotExist:
                self.add_error(
                    'email', 'Este e-mail não está cadastrado. Entre em contato com a coordenação.')
            except Professor.MultipleObjectsReturned:
                self.add_error(
                    'email', 'E-mail cadastrado para mais do que um orientador. Entre em contato com a coordenação.'
                )

        return cleaned_data


class OrientacaoAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        obj = kwargs.get('instance')
        hoje = now().date
        self.fields['dt_inicio'].initial = hoje
        if obj and obj.matricula:
            self.fields['curso'].initial = obj.matricula.curso

    curso = forms.ModelChoiceField(
        queryset=Curso.objects.all()
    )
    aluno = forms.ModelChoiceField(
        queryset=Aluno.objects.all(), required=False
    )
    matricula = forms.ModelChoiceField(
        queryset=Matricula.objects.all(),
        widget=forms.HiddenInput(), required=False)

    orientador = forms.ModelChoiceField(
        queryset=Pesquisador.objects.all(),
        widget=s2forms.ModelSelect2Widget(
            model=Pesquisador,
            attrs={'data-minimum-input-length': 3},
            dependent_fields={"curso": "curso", "coorientacao": "coorientacao"},
            data_view="orientador-autocomplete",
            width=200,
        )
    )

    def clean(self):
        fields = super().clean()

        if not fields.get('aluno'):
            raise forms.ValidationError("Aluno não selecionado. "
                                        "Verifique se o aluno está com a matrícula ativa nesse curso!")

        matricula = Matricula.objects.filter(
            curso=fields['curso'], pesquisador=fields['aluno']).last()

        if not matricula:
            raise forms.ValidationError("Matricula não encontrada")

        fields['matricula'] = matricula

        if not fields.get('coorientacao'):
            if Orientacao.objects.filter(aluno=fields.get('aluno'), status=STATUS_ATIVO, coorientacao=False).exclude(
                    pk=self.instance.pk).exists():
                raise forms.ValidationError(
                    "Já existe um orientador ativo para este aluno. Marque a outra orientação como Finalizada")

            professor_invalido = True
            linha = ProfessorLinha.objects.filter(professor=fields.get('orientador'),
                                                  linha__programa__curso=fields['curso']).first()
            if linha:
                if not linha.dtsaida:
                    professor_invalido = False
                else:
                    if linha.dtsaida > self.instance.dt_inicio:
                        professor_invalido = False

            if professor_invalido:
                raise forms.ValidationError("O orientador deve ser um professor ativo do programa")

        return fields

    class Media:
        js = ('js/orientacao_chain_fields.js',)

    class Meta:
        fields = ('curso', 'aluno', 'orientador', 'coorientacao', 'dt_inicio', 'status', 'matricula')
        model = Orientacao


class BuscaProfessorAlunoForm(forms.Form):
    email = forms.EmailField(
        label='',  # Label vazio para esconder o rótulo
        widget=forms.EmailInput(attrs={
            'placeholder': 'Digite seu e-mail',  # Placeholder para orientar o usuário
            'class': 'form-control',  # Classe CSS (opcional)
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            AdminFieldset(
                '',
                Row(AdminField('email')),
            ),
            AdminSubmitRow(Submit('submit', 'Buscar'))
        )

    def clean_email(self):
        """Verifica se o e-mail possui um formato válido"""
        email = self.cleaned_data.get('email')

        if not email:
            raise forms.ValidationError("Por favor, insira um endereço de e-mail válido.")

        return email


class AtualizarDadosForm(forms.ModelForm):
    """Formulário base para editar os dados e criar ou atualizar um usuário Django"""

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        validators=[validate_password],
        required=False
    )

    confirm_password = forms.CharField(
        label="Confirmar Senha",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        # Verifica se é o primeiro acesso
        self.is_first_access = kwargs.pop('is_first_access', True)
        readonly_fields = kwargs.pop('readonly_fields', [])
        super().__init__(*args, **kwargs)

        # Remove os campos de senha se não for o primeiro acesso
        if not self.is_first_access:
            del self.fields['password']
            del self.fields['confirm_password']

        for field_name in readonly_fields:
            field = self.fields.get(field_name)
            if field:
                field.widget.attrs['readonly'] = True

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        # Validação das senhas apenas no primeiro acesso
        if 'password' in self.fields and 'confirm_password' in self.fields:
            if password and password != confirm_password:
                raise forms.ValidationError({"confirm_password": "As senhas não coincidem."})

        return cleaned_data

    def clean_id_cnpq(self):
        id_cnpq = self.cleaned_data.get('id_cnpq')

        if 'id_cnpq' in self.changed_data:
            validate_id_cnpq(id_cnpq)

        return id_cnpq

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Atualiza o first_name e e-mail do usuário
        if instance.user:
            instance.user.first_name = instance.nome
            instance.user.email = self.cleaned_data['email']
            instance.user.save()  # Salva o usuário após a atualização

        # Se a senha foi fornecida, cria ou atualiza o usuário no Django
        password = self.cleaned_data.get('password')
        username = instance.get_auth_username()
        # Verificar se o CPF/ORCID já está associado a um usuário
        user = None

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Se o usuário não existir, cria um novo
            if password:
                user = User.objects.create_user(
                    first_name=instance.nome,  # Usa o nome do aluno como first_name
                    email=self.cleaned_data['email'],
                    username=username,
                    password=password
                )
        # Associar o usuário ao objeto
        if user is not None:
            instance.user = user

        if commit:
            instance.save()

        return instance

    class Meta:
        fields = ['sexo', 'email', 'email_alternativo', 'telefones', 'raca', 'id_cnpq']
        widgets = {
            'sexo': forms.Select(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'email_alternativo': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefones': forms.TextInput(attrs={'class': 'form-control'}),
            'raca': forms.Select(attrs={'class': 'form-control'}),
            'id_cnpq': forms.TextInput(attrs={'class': 'form-control'}),
        }


class EditProfessorForm(AtualizarDadosForm):
    """Formulário para editar os dados do aluno e criar ou atualizar um usuário Django"""

    class Meta(AtualizarDadosForm.Meta):
        model = Professor

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'

        post_buttons = Div(Submit('editar', 'Salvar Alterações', css_class='mt-3'))

        # Ajusta o layout com base no primeiro acesso
        fields_layout = [
            Div(
                HTML('<label>CPF</label>'),
                Div(
                    HTML('{{ form.instance.get_CPF_display|default:"---" }}'),
                ),
                css_class='form-group mb-2'
            ),
            Div(
                HTML('<label>ORCID</label>'),
                Div(
                    HTML('{{ form.instance.orcid|default:"---" }}'),
                ),
                css_class='form-group mb-2'
            ),
            Div(
                HTML('<label>Nome Completo</label>'),
                Div(
                    HTML('{{ form.instance.nome }}'),
                ),
                css_class='form-group mb-2'
            ),
            Field('sexo', css_class='mb-2 form-select'),
            Field('email', css_class='mb-2'),
            Field('email_alternativo', css_class='mb-2'),
            Field('raca', css_class='mb-2 form-select'),
            Field('id_cnpq', css_class='mb-2'),
        ]

        # Adiciona os campos de senha apenas no primeiro acesso
        if self.is_first_access:
            fields_layout.append(
                Div(
                    Div(Field('password'), css_class='col-md-6'),
                    Div(Field('confirm_password'), css_class='col-md-6'),
                    css_class='row mt-5'
                )
            )
        fields_layout.append(post_buttons)
        self.helper.layout = Layout(*fields_layout)


class EditAlunoForm(AtualizarDadosForm):
    """Formulário para editar os dados do aluno e criar ou atualizar um usuário Django"""

    local = forms.ChoiceField(label='Local', choices=Matricula.Local.choices)

    class Meta(AtualizarDadosForm.Meta):
        model = Aluno

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        matricula = self.instance.matricula_atual
        if matricula:
            self.fields['local'].initial = matricula.local

        self.helper = FormHelper()
        self.helper.form_method = 'post'

        post_buttons = Div(Submit('editar', 'Salvar Alterações', css_class='mt-3'))

        # Ajusta o layout com base no primeiro acesso
        fields_layout = [
            Div(
                HTML('<label>Matrícula</label>'),
                Div(
                    HTML('{{ form.instance.numero_matricula|default:"---" }}'),
                ),
                css_class='form-group mb-2'
            ),
            Div(
                HTML('<label>CPF</label>'),
                Div(
                    HTML('{{ form.instance.get_CPF_display|default:"---" }}'),
                ),
                css_class='form-group mb-2'
            ),
            Div(
                HTML('<label>ORCID</label>'),
                Div(
                    HTML('{{ form.instance.orcid|default:"---" }}'),
                ),
                css_class='form-group mb-2'
            ),
            Div(
                HTML('<label>Nome Completo</label>'),
                Div(
                    HTML('{{ form.instance.nome }}'),
                ),
                css_class='form-group mb-2'
            ),
            Field('sexo', css_class='mb-2 form-select'),
            Field('email', css_class='mb-2'),
            Field('email_alternativo', css_class='mb-2'),
            Field('telefones', css_class='mb-2'),
            Field('raca', css_class='mb-2 form-select'),
            Field('id_cnpq', css_class='mb-2'),
            Field('local', css_class='mb-2 form-select'),
        ]

        # Adiciona os campos de senha apenas no primeiro acesso
        if self.is_first_access:
            fields_layout.append(
                Div(
                    Div(Field('password'), css_class='col-md-6'),
                    Div(Field('confirm_password'), css_class='col-md-6'),
                    css_class='row mt-5'
                )
            )
        fields_layout.append(post_buttons)
        self.helper.layout = Layout(*fields_layout)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        matricula = instance.matricula_atual
        if matricula:
            matricula.local = self.cleaned_data.get('local')
            matricula.save()
        return instance


# noinspection PyUnresolvedReferences
class SolicitaOrientadorForm(forms.Form):
    orientador = forms.ModelChoiceField(
        queryset=Professor.objects.none(),
        label="Nome do Orientador",
        widget=s2forms.ModelSelect2Widget(
            model=Professor,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 5, 'class': 'form-control', 'style': 'width: 36rem; height: 38px;'}
        ),
        required=True,
        help_text='<small class="form-text text-muted" style="display: block;">Preencha ao menos 5 caracteres</small>'
    )

    coorientador = forms.ModelChoiceField(
        queryset=Pesquisador.objects.all(),
        label="Nome do Coorientador",
        widget=s2forms.ModelSelect2Widget(
            model=Pesquisador,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 5, 'class': 'form-control', 'style': 'width: 36rem; height: 38px;'}
        ),
        required=False,
        help_text='<small class="form-text text-muted" style="display: block;">Preencha ao menos 5 caracteres</small>'
    )

    nome_completo_externo = forms.CharField(
        label="Nome Completo",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'style': 'max-width: 36rem; height: 38px;'})
    )

    email_externo = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'style': 'max-width: 36rem; height: 38px;'})
    )

    instituicao_externa = forms.CharField(
        label="Instituição",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'style': 'max-width: 36rem; height: 38px;'})
    )

    link_lattes = forms.CharField(
        label="Link do Currículo Lattes",
        required=False,
        max_length=100,
        help_text="Insira o link completo do Currículo Lattes.",
        widget=forms.TextInput(attrs={'class': 'form-control', 'style': 'max-width: 36rem; height: 38px;'})
    )

    orcid = forms.CharField(
        label="ORCID",
        required=False,
        help_text="Insira o link ou número do ORCID",
        widget=forms.TextInput(attrs={'class': 'form-control', 'style': 'max-width: 36rem; height: 38px;'})
    )

    comentarios_adicionais = forms.CharField(
        label="Comentários Adicionais",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'style': 'max-width: 36rem;'}),
        required=False
    )

    def clean_link_lattes(self):
        link_lattes = (self.cleaned_data.get("link_lattes") or "").strip()
        if not link_lattes:
            return link_lattes

        id_cnpq = link_lattes.split('/')[-1].strip()
        if not id_cnpq:
            return id_cnpq

        pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
        if pesquisador:
            return id_cnpq

        try:
            validate_id_cnpq(id_cnpq)
        except forms.ValidationError as e:
            error_message = str(e)
            if "Consulta ao CNPQ fora do ar" not in error_message:
                raise e

        return id_cnpq

    def clean_orcid(self):
        raw_orcid = self.cleaned_data.get('orcid')
        orcid = clean_orcid(raw_orcid)
        if raw_orcid and not orcid:
            raise forms.ValidationError("ORCID inválido")

        pesquisador = Pesquisador.objects.filter(orcid=orcid).first()
        if pesquisador:
            return orcid

        name = self.cleaned_data.get('nome_completo_externo') or ""
        is_valid, message = validate_orcid(orcid, name)
        if not is_valid:
            raise forms.ValidationError(message)

        return orcid

    def clean(self):
        cleaned_data = super().clean()
        nome_externo = cleaned_data.get('nome_completo_externo')
        if cleaned_data.get('coorientador'):
            if nome_externo:
                raise forms.ValidationError(
                    'Só preencha o nome externo caso você não tenha encontrado o pesquisador na lista de coorientação')
        else:
            if nome_externo:
                # Alguns alunos não lêem o enunciado e colocam seu próprio nome no lugar do coorientador :(
                if nome_externo == self.aluno.nome:
                    raise forms.ValidationError('O coorientador não pode ser o próprio aluno!')
                if not cleaned_data.get('link_lattes') and not cleaned_data.get('orcid'):
                    raise forms.ValidationError('O ID Lattes ou o ORCID devem ser preenchidos')
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.aluno = kwargs.pop('aluno', None)
        super(SolicitaOrientadorForm, self).__init__(*args, **kwargs)

        if self.aluno and hasattr(self.aluno, 'matricula_atual'):
            programa = self.aluno.matricula_atual.curso.programa
            self.fields['orientador'].queryset = Professor.objects.filter(
                pesquisadorprograma__programa=programa
            ).distinct()
        else:
            self.fields['orientador'].queryset = Professor.objects.all()

        self.helper = FormHelper()
        self.helper.form_method = 'post'

        self.helper.layout = Layout(
            'orientador',
            'coorientador',
            HTML("<p class='mt-4'><b>Caso o coorientador não esteja na lista acima</b>, preencha os dados</p><hr/>"),
            'nome_completo_externo',
            'email_externo',
            'instituicao_externa',
            'link_lattes',
            'orcid',
            'comentarios_adicionais',
            Div(
                Submit('submit',
                       'Enviar Solicitação',
                       css_class='btn btn-primary'
                       ),
                css_class='d-flex justify-content-center mt-4',
            )
        )


class HomologacaoDefesaForm(forms.ModelForm):
    """Formulário para solicitação de homologação de defesa."""

    titulo_trabalho = forms.CharField(
        label="Título do Trabalho",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=True
    )
    ata_quali = forms.FileField(
        label="Ata de Qualificação",
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        required=False
    )
    historico = forms.FileField(
        label="Histórico Escolar",
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        }),
        required=False
    )
    dtevento = forms.DateField(
        label="Data da Qualificação/Defesa",
        widget=forms.DateInput(),
        required=True
    )
    horario = forms.TimeField(
        label="Horário",
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        required=True
    )
    local = forms.CharField(
        label="Local",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )
    modalidade = forms.ChoiceField(
        label="Modalidade",
        choices=MatriculaEvento.Modalidade.choices,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    justificativa = forms.CharField(
        label="Justificativa (caso não seja presencial)",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )
    obs = forms.CharField(
        label="Comentários Adicionais",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.matricula_id = kwargs.pop('matricula', None)
        self.tipo_ocorrencia = kwargs.pop('tipo_ocorrencia', None)
        self.necessita_historico = kwargs.pop('historico', None)
        super(HomologacaoDefesaForm, self).__init__(*args, **kwargs)

        if self.instance.id:
            documento = Documento.objects.filter(
                content_type=ContentType.objects.get_for_model(MatriculaEvento),
                object_id=self.instance.id,
                tipo__chave='ATAQUALI'
            ).first()

            # Criar um dicionário de dados iniciais para o formulário
            if documento and documento.anexo:
                self.fields['ata_quali'].initial = documento.anexo

            documento = Documento.objects.filter(
                content_type=ContentType.objects.get_for_model(MatriculaEvento),
                object_id=self.instance.id,
                tipo__chave='HISTORICO'
            ).first()

            # Criar um dicionário de dados iniciais para o formulário
            if documento and documento.anexo:
                self.fields['historico'].initial = documento.anexo

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        post_buttons = Row(Div(
            Submit('submit', 'Registre esta etapa para continuar', css_class='btn btn-primary mb-4'),
            css_class='d-flex justify-content-center mt-3'))

        fields_layout = [Field('titulo_trabalho', css_class='mb-4')]
        if self.necessita_historico:
            fields_layout.append(Field('historico', css_class='mb-4'))
            self.fields['historico'].required = True

        # se for defesa, a ata da qualificação deve ser enviada
        if self.tipo_ocorrencia in [2, 3]:
            fields_layout.append(Field('ata_quali', css_class='mb-4'))
            self.fields['ata_quali'].required = True

        fields_layout += [
            Row(
                Column(Field('dtevento', css_class='mb-4'), css_class="col-md-6"),
                Column(Field('horario', css_class='mb-4'), css_class="col-md-6"),
                css_class="row"
            ),
            Field('local', css_class='mb-4'),
            Field('modalidade', css_class='mb-4 form-select'),
            Field('justificativa', css_class='mb-4'),
            Field('obs', css_class='mb-4'),
            post_buttons
        ]

        self.helper.layout = Layout(*fields_layout)

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Define o tipo de ocorrência com base na URL recebida
        try:
            instance.tipo = TipoOcorrencia.objects.get(id=self.tipo_ocorrencia)
        except TipoOcorrencia.DoesNotExist:
            raise forms.ValidationError("O tipo de ocorrência correspondente não foi encontrado.")

        content_type = ContentType.objects.get_for_model(instance)

        # Define a matrícula associada
        if self.matricula_id:
            instance.matricula = Matricula.objects.get(id=self.matricula_id)

        if commit:
            instance.save()

        # Salvar o histórico e a ata no modelo Documento
        file_action = self.data.get('file_action', 'keep')
        if self.cleaned_data.get('historico'):
            tipo_documento = TipoDocumento.objects.get(chave='HISTORICO')
            documento_existente, _ = Documento.objects.get_or_create(
                content_type=content_type,
                object_id=instance.id,
                tipo=tipo_documento)
            documento_existente.anexo = self.cleaned_data['historico']
            documento_existente.save()

        if self.cleaned_data.get('ata_quali'):
            tipo_documento = TipoDocumento.objects.get(chave='ATAQUALI')
            documento_existente, _ = Documento.objects.get_or_create(
                content_type=content_type,
                object_id=instance.id,
                tipo=tipo_documento)
            documento_existente.anexo = self.cleaned_data['ata_quali']
            documento_existente.save()

        return instance

    class Meta:
        model = MatriculaEvento
        fields = ['titulo_trabalho', 'historico', 'ata_quali',
                  'dtevento', 'horario', 'local', 'modalidade', 'justificativa', 'obs']


class MatriculaEventoPesquisadorForm(forms.ModelForm):
    membro_interno = forms.ModelChoiceField(
        queryset=Professor.objects.none(),
        widget=s2forms.ModelSelect2Widget(
            model=Professor,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 5, 'class': 'form-control'}
        ),
        required=True,
        help_text='<small class="form-text text-muted">Preencha ao menos 5 caracteres</small>'
    )

    membro_externo = forms.ModelChoiceField(
        queryset=Pesquisador.objects.none(),
        widget=s2forms.ModelSelect2Widget(
            model=Pesquisador,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 5, 'class': 'form-control'}
        ),
        required=True,
        help_text='<small class="form-text text-muted">Preencha ao menos 5 caracteres</small>'
    )

    externo = forms.BooleanField(required=False, widget=forms.HiddenInput())
    suplente = forms.BooleanField(required=False, widget=forms.HiddenInput())
    ordem = forms.IntegerField(widget=forms.HiddenInput())

    status = forms.ChoiceField(
        choices=MatriculaEventoPesquisador.Status.choices,
        initial=MatriculaEventoPesquisador.Status.EM_EDICAO,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = MatriculaEventoPesquisador
        fields = ['pesquisador', 'evento', 'externo', 'suplente', 'ordem', 'instituicao', 'status']
        widgets = {
            'evento': forms.HiddenInput(),
            'externo': forms.HiddenInput(),
            'suplente': forms.HiddenInput(),
            'ordem': forms.HiddenInput(),
            'status': forms.HiddenInput(),
            'instituicao': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        programa = kwargs.pop('programa', None)
        # Define se a posição da banca é de preenchimento obrigatório.
        # Quando False (ex.: um membro externo opcional), o campo pode ficar vazio.
        obrigatorio = kwargs.pop('obrigatorio', True)
        super().__init__(*args, **kwargs)

        if programa is not None:
            self.fields['membro_interno'].queryset = (
                Professor.objects
                .filter(pesquisadorprograma__programa_id=programa)
                .distinct()
            )
            self.fields['membro_externo'].queryset = (
                Pesquisador.objects
                .exclude(pesquisadorprograma__programa_id=programa)
                .distinct()
            )

        if self.initial.get('externo') == 'E':
            self.fields['pesquisador'] = self.fields['membro_externo']
            self.fields.pop('membro_interno')
            self.fields.pop('membro_externo')
        elif self.initial.get('externo') == 'I':
            self.fields['pesquisador'] = self.fields['membro_interno']
            self.fields.pop('membro_externo')
            self.fields.pop('membro_interno')
        else:
            self.fields['membro_externo'].queryset = Pesquisador.objects.all()
            self.fields['pesquisador'] = self.fields['membro_externo']
            self.fields.pop('membro_externo')
            self.fields.pop('membro_interno')

        # A obrigatoriedade é um parâmetro explícito da posição, não fixa no form.
        self.fields['pesquisador'].required = obrigatorio

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False


class InstituicaoWidget(s2forms.ModelSelect2Widget):
    search_fields = ['nome__icontains', 'sigla__icontains']

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs.setdefault('data-minimum-input-length', 2)
        attrs['data-placeholder'] = 'Busque pelo nome ou sigla da instituição'
        return attrs


class MembroExternoBaseForm(forms.Form):
    """
    Campos de identificação comuns ao cadastro de membro externo da banca.

    Caminhos mutuamente exclusivos: estrangeiro usa ORCID + Nome; caso contrário,
    usa o ID CNPq (Lattes). O e-mail é comum aos dois caminhos.
    """
    email = forms.EmailField(label="E-mail", required=True)
    estrangeiro = forms.BooleanField(label="Estrangeiro/a", required=False)
    id_cnpq = forms.CharField(
        label='ID CNPQ', max_length=16, required=False,
        help_text='Usaremos o Lattes para preencher os dados automaticamente.'
    )
    orcid = forms.CharField(
        label='ORCID', max_length=20, required=False,
        widget=forms.TextInput(attrs={'placeholder': '0000-0000-0000-0000'})
    )
    nome = forms.CharField(label='Nome completo', max_length=100, required=False)


class VincularMembroExternoForm(MembroExternoBaseForm):
    """
    Submit final do wizard de membro externo da banca.

    Não cria o membro: o ``Pesquisador`` é identificado/criado via AJAX
    (``identificar_membro_externo``), que preenche ``pesquisador_id``. Este form
    valida a instituição (da lista ou nova) e grava o vínculo
    ``PesquisadorInstituicao`` em ``save()`` (criando a ``Instituicao`` e
    notificando a secretaria quando for uma instituição nova).
    """

    # Preenchidos pela etapa AJAX / contexto da solicitação
    pesquisador_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    matricula_evento_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    # Etapa 3 - instituição
    instituicao = forms.ModelChoiceField(
        label='Instituição', required=False,
        queryset=Instituicao.objects.all(),
        widget=InstituicaoWidget
    )
    instituicao_fora_lista = forms.BooleanField(label='A instituição não está na lista', required=False)
    instituicao_nome = forms.CharField(label='Nome completo da instituição', max_length=80, required=False)
    instituicao_sigla = forms.CharField(label='Sigla', max_length=10, required=False)

    def clean_instituicao_nome(self):
        return clean_texto(self.cleaned_data.get('instituicao_nome'))

    def clean_instituicao_sigla(self):
        return clean_texto(self.cleaned_data.get('instituicao_sigla'))

    def clean(self):
        cleaned_data = super().clean()

        pesquisador_id = cleaned_data.get('pesquisador_id')
        if not pesquisador_id:
            raise forms.ValidationError('Identifique o pesquisador (ID CNPq ou ORCID) antes de salvar.')

        # Resolve o pesquisador já aqui; save() reutiliza self.pesquisador
        self.pesquisador = Pesquisador.objects.filter(id=pesquisador_id).first()
        if self.pesquisador is None:
            raise forms.ValidationError('Pesquisador não encontrado. Refaça a identificação.')

        if cleaned_data.get('instituicao_fora_lista'):
            instituicao_nome = cleaned_data.get('instituicao_nome')
            instituicao_sigla = cleaned_data.get('instituicao_sigla')

            if not instituicao_nome:
                self.add_error('instituicao_nome', 'Informe o nome completo da instituição.')

            if not instituicao_sigla:
                self.add_error('instituicao_sigla', 'Informe a sigla da instituição.')

        elif not cleaned_data.get('instituicao'):
            self.add_error('instituicao', 'Selecione uma instituição.')

        return cleaned_data

    def save(self, user):
        """Grava o vínculo pesquisador↔instituição e retorna o ``Pesquisador``.

        Cria a ``Instituicao`` (+ log + notificação à secretaria) quando o
        usuário indica uma instituição fora da lista. Chamar apenas após
        ``is_valid()`` (``self.pesquisador`` é resolvido no ``clean()``).
        """
        cleaned_data = self.cleaned_data

        if cleaned_data['instituicao_fora_lista']:
            instituicao = Instituicao.objects.create(
                nome=cleaned_data['instituicao_nome'], sigla=cleaned_data['instituicao_sigla']
            )
            log_object(instituicao, f'Criada pelo discente {user}', inclusao=True)
            self._notificar_secretaria(user, instituicao, cleaned_data.get('matricula_evento_id'))
        else:
            instituicao = cleaned_data['instituicao']

        PesquisadorInstituicao.objects.get_or_create(pesquisador=self.pesquisador, instituicao=instituicao)

        return self.pesquisador

    @staticmethod
    def _notificar_secretaria(user, instituicao, matricula_evento_id):
        """Notifica a secretaria do curso sobre uma instituição recém-cadastrada."""
        if not matricula_evento_id:
            return
        evento = (MatriculaEvento.objects
                  .select_related('matricula__curso')
                  .filter(id=matricula_evento_id)
                  .first())
        if not evento:
            return
        curso = evento.matricula.curso
        if not curso.email_secretaria:
            return

        admin_path = reverse('admin:nucleo_instituicao_change', args=[instituicao.id])
        base_url = getattr(settings, 'SITE_URL', '') or ''
        link = f'{base_url}{admin_path}' if base_url else admin_path

        mensagem = (
            f'O discente {user} cadastrou a instituição '
            f'"{instituicao.nome}" ({instituicao.sigla}) durante uma solicitação de '
            f'defesa. <a href="{link}">Revise o cadastro</a>.'
        )
        sendmail('Nova instituição cadastrada', [curso.email_secretaria], message=mensagem, thread=True)


class IdentificarMembroExternoForm(MembroExternoBaseForm):
    """Etapa 1 (AJAX): valida, identifica/cria e devolve o ``Pesquisador``.

    Caminhos mutuamente exclusivos: estrangeiro exige ORCID + Nome; caso
    contrário, exige o ID CNPq. A identificação/criação acontece em ``save()``,
    que retorna o ``Pesquisador``.
    """

    def clean_id_cnpq(self):
        return clean_texto((self.cleaned_data.get('id_cnpq') or '').strip())

    def clean_orcid(self):
        return clean_orcid(self.cleaned_data.get('orcid') or '')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('estrangeiro'):
            if not cleaned_data.get('orcid'):
                self.add_error('orcid', "Informe o ORCID.")
            if not (cleaned_data.get('nome') or '').strip():
                self.add_error('nome', "Informe o nome completo.")
        elif not cleaned_data.get('id_cnpq'):
            self.add_error('id_cnpq', "Informe o ID CNPq.")
        return cleaned_data

    def save(self):
        """
        Identifica ou cria o ``Pesquisador`` e o retorna.

        Levanta ``forms.ValidationError`` (dados inválidos ou falha de importação)
        e pode propagar ``TimeoutError``/``InvalidXMLException`` da raspagem do
        Lattes; a view (``identificar_membro_externo``) é quem trata.
        """
        dados = self.cleaned_data
        email = dados['email']

        if dados['estrangeiro']:
            pesquisador = self._identificar_por_orcid(dados['orcid'], dados['nome'].strip(), email)
        else:
            pesquisador = self._identificar_por_cnpq(dados['id_cnpq'])

        if pesquisador is None:
            raise forms.ValidationError(
                'Não foi possível identificar o pesquisador. Entre em contato com a secretaria.'
            )

        # E-mail comum: grava apenas se o pesquisador ainda não tiver
        if not pesquisador.email:
            pesquisador.email = email
            pesquisador.save(update_fields=['email'])

        return pesquisador

    def _identificar_por_cnpq(self, id_cnpq):
        """Localiza ou importa do Lattes o pesquisador a partir do ID CNPq."""
        # Import local: evita import circular no carregamento do app
        from nucleo.lattes import import_xml, get_lattes_from_proxy

        pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
        if pesquisador:
            return pesquisador

        # Levanta ValidationError se o ID for inválido ou o CNPq estiver fora do ar
        validate_id_cnpq(id_cnpq)

        xml = get_lattes_from_proxy(id_cnpq)
        resultado = import_xml(xml, save_file=False)
        if not resultado.get('sucesso'):
            raise forms.ValidationError(
                'Não foi possível importar o currículo Lattes. Entre em contato com a secretaria.'
            )
        return Pesquisador.objects.filter(id_cnpq=id_cnpq).first()

    def _identificar_por_orcid(self, orcid, nome, email):
        """Localiza ou cria (validando no ORCID) um pesquisador estrangeiro."""
        pesquisador = Pesquisador.objects.filter(orcid__iexact=orcid).first()
        if pesquisador:
            return pesquisador

        valido, msg = validate_orcid(orcid, nome)
        if not valido:
            raise forms.ValidationError(
                (msg or 'ORCID inválido.') +
                ' Entre em contato com a secretaria para que o registro seja manual.'
            )
        return Pesquisador.objects.create(nome=nome, orcid=orcid, email=email)


class InscricaoDisciplinaForm(forms.Form):
    disciplinas = forms.ModelMultipleChoiceField(
        queryset=Disciplina.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label='Disciplinas Disponíveis para Inscrição',
        help_text='Selecione as disciplinas que deseja se inscrever',
        required=True
    )

    def __init__(self, *args, **kwargs):
        aluno = kwargs.pop('aluno')
        periodo_corrente = kwargs.pop('periodo_corrente')
        super().__init__(*args, **kwargs)

        curso_aluno = aluno.matricula_atual.curso if aluno.matricula_atual else None

        # Disciplinas com turmas no período atual associadas ao curso do aluno
        turmas_correntes = Turma.objects.filter(periodo=periodo_corrente,
                                                turmacurso__curso=curso_aluno)
        disciplinas_correntes = Disciplina.objects.filter(turma__in=turmas_correntes)

        # Disciplinas permanentes compatíveis com o curso
        disciplinas_permanentes = Disciplina.objects.filter(status='P')
        if curso_aluno:
            disciplinas_permanentes = disciplinas_permanentes.filter(disciplinacurso__curso=curso_aluno)

        # Disciplinas já cursadas ou em curso
        disciplinas_ja_cursadas = Disciplina.objects.filter(
            turma__inscricao__aluno=aluno,
            turma__inscricao__status__in=[Inscricao.Status.APROVADO, Inscricao.Status.MATRICULADO]
        )

        # Disciplinas disponíveis
        disciplinas_disponiveis = (
                disciplinas_correntes | disciplinas_permanentes
        ).distinct().exclude(id__in=disciplinas_ja_cursadas)

        self.fields['disciplinas'].queryset = disciplinas_disponiveis.order_by('titulo')


class SolicitacaoProrrogacaoForm(forms.Form):
    justificativa = forms.CharField(
        label="Justificativa",
        required=True,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "cols": "99%",
            "style": "height: 90px;",
        }),
        error_messages={
            "required": "Informe a justificativa."
        }
    )

    novo_cronograma = forms.FileField(
        label="Novo cronograma (arquivo)",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        error_messages={
            "required": "Anexe o novo cronograma."
        }
    )

    historico = forms.FileField(
        label="Histórico (arquivo)",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        error_messages={
            "required": "Anexe o histórico."
        }
    )

    comentarios_adicionais = forms.CharField(
        label="Comentários adicionais",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 2,
            "cols": "99%",
            "style": "height: 90px;",
        })
    )

    def clean_justificativa(self):
        texto = (self.cleaned_data.get("justificativa") or "").strip()
        if len(texto) < 10:
            raise forms.ValidationError(
                "A justificativa deve conter pelo menos 10 caracteres."
            )
        return texto


class SolicitacaoReativacaoForm(forms.Form):
    justificativa = forms.CharField(
        label="Justificativa",
        required=True,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "cols": "99%",
            "style": "height: 90px;",
        }),
        error_messages={
            "required": "Informe a justificativa."
        }
    )

    def clean_justificativa(self):
        texto = (self.cleaned_data.get("justificativa") or "").strip()
        if len(texto) < 10:
            raise forms.ValidationError(
                "A justificativa deve conter pelo menos 10 caracteres."
            )
        return texto


class TurmaAvaliacaoItemForm(forms.Form):
    CONCEITOS = (
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('F', 'F'),
    )
    inscricao_id = forms.IntegerField(widget=forms.HiddenInput)
    conceito = forms.ChoiceField(choices=CONCEITOS, required=True, label='')


class SolicitacaoTrancamentoForm(forms.Form):
    justificativa = forms.CharField(
        label="Justificativa",
        required=True,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "cols": "99%",
            "style": "height: 90px;",
        }),
        error_messages={
            "required": "Informe a justificativa."
        }
    )

    historico = forms.FileField(
        label="Histórico escolar",
        required=True,
        help_text="Anexe o arquivo do histórico escolar.",
        error_messages={
            "required": "Anexe o histórico escolar."
        }
    )

    comentarios_adicionais = forms.CharField(
        label="Comentários adicionais",
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 2,
            "cols": "99%",
            "style": "height: 90px;",
        })
    )

    def clean_justificativa(self):
        texto = (self.cleaned_data.get("justificativa") or "").strip()
        if len(texto) < 10:
            raise forms.ValidationError(
                "A justificativa deve conter pelo menos 10 caracteres."
            )
        return texto


class MatriculaEventoAtaForm(forms.ModelForm):
    """Form utilizado para vincular ou desvincular MatriculaEvento de AtaReuniao"""
    selecionado = forms.BooleanField(required=False, label='Vincular')

    class Meta:
        model = MatriculaEvento
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Neste ponto, self.instance.ata_reuniao_id ainda é o valor do banco
        # (BaseInlineFormSet._construct_form sobrescreve esse atributo
        # depois que o __init__ do form retorna).
        if self.instance.pk:
            self.fields['selecionado'].initial = self.instance.ata_reuniao_id is not None


class MatriculaEventoAtaInlineFormSet(BaseInlineFormSet):
    """Formset que renderiza forms com um checkbox para marcar desmarcar MatriculaEvento de ma AtaReuniao"""

    def get_queryset(self):
        if not hasattr(self, '_cached_qs'):
            base = MatriculaEvento.objects.select_related('matricula', 'tipo')
            if self.instance and self.instance.pk:
                qs = base.filter(
                    Q(ata_reuniao__isnull=True) | Q(ata_reuniao=self.instance)
                )
            else:
                qs = base.filter(ata_reuniao__isnull=True)
            self._cached_qs = qs.order_by('matricula', 'dtevento')
        return self._cached_qs

    def save_existing(self, form, instance, commit=True):
        if form.cleaned_data.get('selecionado'):
            instance.ata_reuniao = self.instance
        else:
            instance.ata_reuniao = None

        if commit:
            instance.save()

        return instance
