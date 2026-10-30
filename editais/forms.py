import re
from datetime import date

from crispy_forms.helper import FormHelper
from django import forms
from django.utils.safestring import mark_safe

from nucleo.apps import validate_id_cnpq
from nucleo.models import LinhaPesquisa, Pesquisador, PesquisadorFormacao
from nucleo.lattes import import_xml, verifica_lattes

from qualis.models import Assunto
from utils.stdlib import EMPTY_VALUES
from utils.widgets import TelefoneInput
from utils.fields import validate_orcid

from .models import EditalTipoDocumento, Inscricao, TipoVaga, Edital

def _buscar_pesquisador(cpf, id_cnpq):
    """Busca Pesquisador por CPF ou id_cnpq e valida consistência entre os dois.

    Levanta ValidationError caso o pesquisador encontrado tenha CPF ou id_cnpq
    divergentes dos informados. Retorna o Pesquisador ou None.
    """
    pesquisador = None
    if id_cnpq:
        pesquisador = Pesquisador.objects.filter(id_cnpq=id_cnpq).first()
    if not pesquisador and cpf:
        pesquisador = Pesquisador.objects.filter(CPF=cpf).first()

    if pesquisador:
        if pesquisador.CPF and pesquisador.CPF != cpf:
            raise forms.ValidationError(
                "O ID Lattes não confere com o CPF informado, entre em contato com a secretaria."
            )
        if id_cnpq and pesquisador.id_cnpq and pesquisador.id_cnpq != id_cnpq:
            raise forms.ValidationError(
                "O CPF não confere com o registro no Lattes, entre em contato com a secretaria."
            )

    return pesquisador


class InscricaoInicialEditalForm(forms.ModelForm):
    id_cnpq = forms.CharField(
        label="ID Lattes",
        help_text="O ID Lattes é o número de identificação no seu currículo Lattes.",
        max_length=100,
        required=True,
    )
    termo1 = forms.BooleanField(
        label=mark_safe(
            '''<small>Declaro serem verdadeiras as informações prestadas neste 
            formulário e nos documentos apresentados</small>'''
        ),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input',})
    )
    termo2 = forms.BooleanField(
        label=mark_safe(
            '''<small>Declaro estar ciente de que os dados pessoais fornecidos serão tratados exclusivamente 
            para as finalidades relacionadas à execução deste edital, em conformidade com a Lei nº 13.709/2018 
            (Lei Geral de Proteção de Dados Pessoais – LGPD), observados os princípios da legalidade, finalidade, 
            adequação, necessidade, transparência, segurança e confidencialidade.</small>'''
        ),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input',})
    )

    termo3 = forms.BooleanField(
        label=mark_safe(
            '''<small>Autorizo o tratamento dos dados pessoais estritamente necessários à gestão do processo seletivo, 
            incluindo análise documental, comunicação institucional, divulgação dos resultados e demais procedimentos 
            administrativos decorrentes do edital, resguardados os direitos do titular dos dados 
            previstos na legislação vigente.</small>'''
        ),
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input',})
    )

    class Meta:
        model = Inscricao
        fields = ["CPF", "id_cnpq", "email", "tipo_vaga", "termo1", "termo2", "termo3"]

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop("edital", None)
        self.request = kwargs.pop("request", None)
        self.pesquisador = None
        self.nome_pesquisador = None
        self.erro_cnpq = False
        super().__init__(*args, **kwargs)
        self.fields['CPF'].required = True
        self.fields['email'].required = True
        self.fields['id_cnpq'].required = True
        self.fields['tipo_vaga'].required = True
        if 'tipo_vaga' in self.fields:
            self.fields['tipo_vaga'].label = 'Tipo de Vaga Desejada'
            self.fields['tipo_vaga'].queryset = TipoVaga.objects.filter(
                id__in=self.edital.editalvaga_set.values_list('tipo_vaga', flat=True)
            )

    def clean_email(self):
        # normaliza
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_CPF(self):
        value = self.cleaned_data.get('CPF')

        if value in EMPTY_VALUES:
            return value
        # Evita duplicidade no mesmo edital (sempre usando apenas dígitos)
        if self.edital and Inscricao.objects.filter(edital=self.edital, CPF=value).exists():
            raise forms.ValidationError(
                "Já existe uma inscrição com esse CPF. Enviamos um e-mail para que você visualize ou ajuste a sua inscrição."
                "Caso você não receba o email, entre em contato com a secretaria."
            )

        return value

    def clean_id_cnpq(self):
        # aceita colagem com texto e extrai 16 dígitos
        bruto = (self.cleaned_data.get("id_cnpq") or "").strip()
        m = re.search(r"(\d{16})", bruto)
        if not m:
            raise forms.ValidationError("Informe um ID Lattes válido (16 dígitos).")
        id_cnpq = m.group(1)

        if self.edital and Inscricao.objects.filter(edital=self.edital, id_cnpq=id_cnpq).exists():
            raise forms.ValidationError("Já existe uma inscrição para esse edital com esse ID Lattes.")
        return id_cnpq

    def clean(self):
        cleaned_data = super().clean()
        cpf = cleaned_data.get("CPF")
        id_cnpq = cleaned_data.get("id_cnpq")
        lattes_ok = False
        if cpf and id_cnpq:
            self.pesquisador = _buscar_pesquisador(cpf, id_cnpq)
            if self.pesquisador:
                self.nome_pesquisador = self.pesquisador.nome
                lattes_ok = self.pesquisador.atualizado
        else:
            self.pesquisador = None

        if not lattes_ok and id_cnpq:
            nome_no_lattes = verifica_lattes(id_cnpq)
            if nome_no_lattes:
                self.nome_pesquisador = nome_no_lattes
            else:
                try:
                    validate_id_cnpq(id_cnpq)
                except forms.ValidationError as e:
                    msg = str(e)
                    if "Consulta ao CNPQ fora do ar" in msg:
                        self.erro_cnpq = True
                    else:
                        raise

        return cleaned_data

    def save(self, commit=True):
        inscricao = super().save(commit=False)
        inscricao.edital = self.edital
        inscricao.nome = self.nome_pesquisador or '*'
        inscricao.candidato = self.pesquisador
        if inscricao.candidato:
            inscricao.orcid = inscricao.candidato.orcid
            inscricao.sexo = inscricao.candidato.sexo
            inscricao.raca = inscricao.candidato.raca

        if not self.erro_cnpq and self.nome_pesquisador:
            inscricao.status_cnpq = Inscricao.StatusCNPQ.VALIDADO

        if commit:
            inscricao.save()

        return inscricao


class InscricaoEditalForm(forms.ModelForm):
    class Meta:
        model = Inscricao
        fields = [
            'nome', 'CPF', 'id_cnpq', 'email', 'sexo',
            'pais_nascimento', 'cidade_nascimento', 'estado_nascimento', 'dt_nascimento',
            'telefone', 'telefone_alt', 'raca',
            'orcid', 'linha', 'condicao_economica',
            'bolsa',
        ]
        widgets = {
            'telefone': TelefoneInput(),
            'telefone_alt': TelefoneInput(),
        }

    def __init__(self, *args, **kwargs):
        edital = kwargs.pop('edital', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if 'id_cnpq' in self.fields:
            self.fields['id_cnpq'].label = "ID Lattes"

        if not edital.requer_condicao:
            del self.fields['condicao_economica']

        optional_fields = ['orcid', 'telefone_alt', 'bolsa']

        for field_name in self.fields:
            if field_name not in optional_fields:
                self.fields[field_name].required = True

        if 'tema' in self.fields:
            self.fields['tema'].queryset = Assunto.objects.filter(schema__sigla='TEMAS-CI')

        if 'linha' in self.fields:
            self.fields['linha'].queryset = LinhaPesquisa.objects.filter(programa=edital.programa)

        self.helper = FormHelper()
        self.helper.form_method = 'post'

        if self.instance and self.instance.pk:
            readonly_fields = ['CPF', 'id_cnpq', 'email',]
            if self.instance.status_cnpq == Inscricao.StatusCNPQ.VALIDADO:
                readonly_fields += ['nome_pesquisador']

            for f in readonly_fields:
                if f in self.fields:
                    self.fields[f].disabled = True
                    self.fields[f].widget.attrs['readonly'] = True
                    self.fields[f].widget.attrs['aria-disabled'] = 'true'
                    self.fields[f].help_text = "Campo bloqueado após o cadastro inicial."

    def clean_nome(self):
        nome = self.cleaned_data.get("nome").strip()
        if len(nome.split()) < 2:
            raise forms.ValidationError('O nome deve ter um sobrenome')
        return nome.upper()

    def clean_orcid(self):
        orcid = self.cleaned_data.get('orcid')
        if orcid:
            name = self.cleaned_data.get('nome')
            is_valid, message = validate_orcid(orcid, name)
            if not is_valid:
                raise forms.ValidationError(message)

        return orcid

    def clean(self):
        cleaned_data = super().clean()
        nascimento = cleaned_data.get("dt_nascimento")

        # Regra de idade mínima (16 anos)
        if nascimento:
            hoje = date.today()
            idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            if idade < 16:
                self.add_error(
                    "dt_nascimento",
                    "A inscrição só é permitida para candidatos com 16 anos ou mais."
                )

        return cleaned_data


class PesquisadorFormacaoForm(forms.ModelForm):
    class Meta:
        model = PesquisadorFormacao
        fields = ['curso', 'nome_instituicao', 'ano_entrada', 'ano_conclusao']
        widgets = {
            'ano_entrada': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'ano_conclusao': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'form-control'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Verifica se há uma instância e formata as datas, se necessário
        if self.instance and self.instance.pk:
            if self.instance.ano_entrada:
                self.fields['ano_entrada'].initial = self.instance.ano_entrada.strftime('%Y-%m-%d')
            if self.instance.ano_conclusao:
                self.fields['ano_conclusao'].initial = self.instance.ano_conclusao.strftime('%Y-%m-%d')


class DocumentoUploadForm(forms.Form):
    def __init__(self, *args, edital=None, tipo_vaga, documentos_existentes_tipo_ids=None, **kwargs):
        super().__init__(*args, **kwargs)

        existentes_tipo_ids = set(documentos_existentes_tipo_ids or [])

        self.possui_mestrado = False  # indicador para a view
        self.tipo_documento_por_field = {}
        self.tipo_vaga = tipo_vaga
        documentos = EditalTipoDocumento.objects.filter(edital=edital)

        for doc in documentos:
            if doc.tipo_vaga is None or doc.tipo_vaga == tipo_vaga:
                field_name = f'documento_{doc.id}'

                # se já existe Documento salvo com o mesmo tipo_id, não exige novo upload
                ja_anexado = (doc.tipo_id in existentes_tipo_ids)

                self.fields[field_name] = forms.FileField(
                    label=doc.descricao,
                    required=(doc.obrigatorio and not ja_anexado)
                )

                self.tipo_documento_por_field[field_name] = doc.tipo_id
