from django.db import models
from nucleo.models import GENDER, RACE_COLOR, LinhaPesquisa, TipoDocumento, Pesquisador, Programa
from qualis.models import Assunto
from utils.fields import BRCPFField


class TipoVaga(models.Model):
    descricao = models.CharField('Descrição', max_length=100)
    ativa = models.BooleanField('Ativa', default=True)

    class Meta:
        verbose_name = 'Tipo de Vaga'
        verbose_name_plural = 'Tipos de Vagas'

    def __str__(self):
        return f'{self.descricao}'


class Edital(models.Model):
    class Status(models.TextChoices):
        EM_EDICAO = 'E', 'Em Edição'
        ATIVO = 'A', 'Ativo'
        FINALIZADO = 'F', 'Finalizado'

    descricao = models.CharField('Descrição', max_length=100)
    notas = models.TextField(blank=True, null=True)
    dt_inicio = models.DateTimeField('Dt.Início')
    dt_fim = models.DateTimeField('Dt.Final')
    url = models.URLField('URL do Edital', max_length=200)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.EM_EDICAO)
    programa = models.ForeignKey(Programa, on_delete=models.SET_NULL, blank=True, null=True)
    requer_condicao = models.BooleanField('Solicita condição socioeconômica', default=True)

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'

    def __str__(self):
        return f'{self.descricao}'

    @property
    def num_inscricoes(self):
        return self.inscricao_set.all().count()


# Tipos de Vagas possíveis para o edital
class EditalVaga(models.Model):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE)
    tipo_vaga = models.ForeignKey(TipoVaga, on_delete=models.RESTRICT)
    num_vagas = models.IntegerField('Núm.Vagas', default=0)

    class Meta:
        verbose_name = 'Vaga do Edital'
        verbose_name_plural = 'Vagas do Edital'

    def __str__(self):
        return f'{self.tipo_vaga}'


# Quais os documentos que serão necessários para o edital
class EditalTipoDocumento(models.Model):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE)
    tipo = models.ForeignKey(TipoDocumento, on_delete=models.RESTRICT)
    descricao = models.CharField('Descrição', max_length=100)
    tipo_vaga = models.ForeignKey(TipoVaga, blank=True, null=True, on_delete=models.RESTRICT)
    obrigatorio = models.BooleanField('Obrigatório', default=True)

    class Meta:
        verbose_name = 'Documento do Edital'
        verbose_name_plural = 'Documentos do Edital'

    def __str__(self):
        return f'{self.descricao}'


class Inscricao(models.Model):

    class Status(models.TextChoices):
        EM_EDICAO = 'E', 'Em Edição'
        SUBMETIDA = 'V', 'Submetida'
        APROVADA = 'A', 'Homologada'

    class StatusCNPQ(models.TextChoices):
        VALIDADO = 'V', 'Validado'
        ERRO = 'E', 'Não validado'

    edital = models.ForeignKey(Edital, on_delete=models.RESTRICT)
    nome = models.CharField('Nome completo', max_length=100)
    CPF = BRCPFField(max_length=11, blank=True, null=True, db_index=True)
    email = models.EmailField('E-mail principal', max_length=60, db_index=True)
    candidato = models.ForeignKey(Pesquisador, on_delete=models.RESTRICT, blank=True, null=True, related_name='candidato')
    sexo = models.CharField(max_length=1, choices=GENDER, null=True)
    pais_nascimento = models.CharField('Nacionalidade', max_length=100, null=True, blank=True)
    cidade_nascimento = models.CharField('Cidade', max_length=100, null=True, blank=True)
    estado_nascimento = models.CharField('Estado', max_length=2, null=True, blank=True)
    dt_nascimento = models.DateField('Data de Nascimento',null=True, blank=True)
    telefone = models.CharField('Telefone', max_length=20, null=True, blank=True)
    telefone_alt = models.CharField('Telefone Alternativo', max_length=20, null=True, blank=True)
    raca = models.CharField('Raça/Cor', max_length=2, choices=RACE_COLOR, null=True, blank=True)
    id_cnpq = models.CharField('ID CNPQ', max_length=16, blank=True, null=True, unique=True)
    orcid = models.CharField('ORCID', max_length=20, blank=True, null=True)
    linha = models.ForeignKey(LinhaPesquisa,null=True, blank=True, on_delete=models.RESTRICT)
    tema = models.ForeignKey(Assunto,blank=True, null=True, on_delete=models.RESTRICT)
    condicao_economica = models.CharField('Condição Econômica', max_length=1,
                                          choices=(('C','Inscrito no Cad.Único'),
                                                   ('N','Sem Rendimentos'),
                                                   ('R','Com Rendimentos')), blank=True, null=True)
    bolsa = models.BooleanField('Interesse em Bolsa de Estudo', default=False)
    tipo_vaga = models.ForeignKey(TipoVaga, blank=True, null=True, on_delete=models.RESTRICT)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.EM_EDICAO)
    status_cnpq = models.CharField('Status CNPQ', choices=StatusCNPQ.choices,
                                   max_length=1, default=StatusCNPQ.ERRO)

    class Meta:
        verbose_name = 'Inscrição'
        verbose_name_plural = 'Inscrições'

    def __str__(self):
        return f'{self.nome}'

    # calcula o digito verificador de um número hexadecimal
    def dv(self, hex_string):
        nr = str(int(hex_string, 16)).zfill(10)
        d = sum([i * int(x) for i, x in enumerate(nr)]) % 11
        return str(0 if d > 9 else d)

    @property
    def numero(self):
        if self.status != Inscricao.Status.EM_EDICAO:
            sequencial = f'{self.id}'.zfill(4)
            base = f'{self.edital.id}{sequencial}'
            digito = self.dv(base)
            return f'{sequencial}-{digito}'
        else:
            return '-'
