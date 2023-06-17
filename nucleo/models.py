from datetime import date, timedelta

from django.db import models
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.timezone import now

from chupalattes import URL_LATTES
from nucleo.apps import generate_hash
from qualis.models import Periodico, Area
from utils.stdlib import localize, nvl

GENDER = (
    ('M', u'Masculino'),
    ('F', u'Feminino'),
)

RACE_COLOR = (
    ('04', 'Amarela'),
    ('01', 'Branca'),
    ('05', 'Indígena'),
    ('03', 'Parda'),
    ('02', 'Preta'),
    ('99', 'Não declarada')
)

NIVEL_CURSO = (
    ('ME', 'Mestrado'),
    ('DO', 'Doutorado'),
    ('MP', 'Mestrado Profissional'),
    ('DP', 'Doutorado Profissional'),
    ('PD', 'Pós-Doutorado'),
)

TIPO_TITULACAO = (
    ('G', 'Graduação'),
    ('M', 'Mestrado'),
    ('D', 'Doutorado'),
)

TITULACAO_GRADUACAO = 'G'
TITULACAO_MESTRADO = 'M'
TITULACAO_DOUTORADO = 'D'

STATUS_ATIVO = 'A'
STATUS_CONCLUIDA = 'C'
STATUS_INATIVA = 'I'
STATUS_FINALIZADA = 'F'
STATUS_CANCELADA = 'X'

STATUS_ATIVIDADE = (
    (STATUS_ATIVO, 'Ativa'),
    (STATUS_INATIVA, 'Inativa'),
)

STATUS_ATIVIDADE_M = (
    (STATUS_ATIVO, 'Ativo'),
    (STATUS_INATIVA, 'Inativo'),
)

STATUS_ORIENTACAO = (
    (STATUS_ATIVO, 'Ativa'),
    (STATUS_CONCLUIDA, 'Concluída'),
    (STATUS_CANCELADA, 'Cancelada'),
)

STATUS_MATRICULA = (
    ('A', 'Ativa'),
    ('C', 'Concluída'),
    ('T', 'Trancada'),
    ('B', 'Abandono'),
    ('O', 'Óbito'),
    ('J', 'Jubilamento'),
)

STATUS_BOLSA = (
    ('N', 'Nenhuma'),
    ('A', 'Ativa'),
    ('E', 'Lista de Espera'),
    ('C', 'Concluída'),
)


class Instituicao(models.Model):
    nome = models.CharField(max_length=80)
    sigla = models.CharField(max_length=10)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Instituição'
        verbose_name_plural = 'Instituições'


class Programa(models.Model):
    instituicao = models.ForeignKey(Instituicao, on_delete=models.PROTECT)
    descricao = models.CharField('Descrição', max_length=100)
    cod_sucupira = models.CharField(max_length=20, blank=True, null=True)
    area = models.ForeignKey(Area, null=True, on_delete=models.PROTECT)

    def __str__(self):
        return '%s %s' % (self.instituicao.sigla, self.descricao)

    class Meta:
        verbose_name = 'Programa de Pós Graduação'
        verbose_name_plural = 'Programas de Pós Graduação'

    def num_professores(self):
        total = 0
        for linha in self.linhapesquisa_set.all():
            total += linha.num_professores()
        return total

    num_professores.short_description = "Núm.Professores"

    def num_pesquisadores(self):
        return self.pesquisadorprograma_set.count()

    num_pesquisadores.short_description = "Núm.Pesquisadores"

    def num_alunos(self):
        cursos = Curso.objects.filter(programa=self).values_list('programa', flat=True).distinct()
        return Matricula.objects.filter(curso__in=cursos, status=STATUS_ATIVO).count()

    num_alunos.short_description = "Matrículas ativas"

    def num_artigos(self):
        ano = now().year
        if now().month == 1:
            ano = ano - 1
        tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
        producoes = ProducaoAutor.objects.filter(autor__pesquisadorprograma__programa=self,
                                                 producao__tipo=tipo_artigo, producao__ano=ano). \
            values('autor__pesquisadorprograma__programa__id'). \
            annotate(cnt=Count('producao__id', distinct=True))
        if producoes:
            return producoes[0]['cnt']
        else:
            return 0

    num_artigos.short_description = "Artigos no Ano"


class LinhaPesquisa(models.Model):
    descricao = models.CharField('Descrição', max_length=120)
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Linha de Pesquisa'
        verbose_name_plural = 'Linhas de Pesquisa'

    def num_professores(self):
        return self.professorlinha_set.filter(dtsaida__isnull=True).count()

    num_professores.short_description = 'Professores ativos'


class ProjetoPesquisa(models.Model):
    linha = models.ForeignKey(LinhaPesquisa, on_delete=models.PROTECT)
    nome = models.CharField(max_length=400)
    descricao = models.TextField('Descrição', blank=True, null=True)
    proponente = models.ForeignKey('Professor', on_delete=models.PROTECT)
    status = models.CharField('Situação', max_length=1, default='A', choices=STATUS_ATIVIDADE_M)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Projeto de Pesquisa'
        verbose_name_plural = 'Projetos de Pesquisa'

    def num_pesquisadores(self):
        return self.pesquisadorprojeto_set.all().count()

    num_pesquisadores.short_description = 'Total de Pesquisadores'

    def num_producao(self):
        return self.producao_set.all().count()

    num_producao.short_description = 'Produção'

    def num_artigos(self):
        return self.producao_set.filter(tipo__cod_externo='artigo').count()

    num_artigos.short_description = 'Artigos'


class Curso(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT)
    nivel = models.CharField(max_length=2, choices=NIVEL_CURSO)

    def __str__(self):
        return f'{self.programa}-{self.descricao}'

    def num_alunos(self):
        return self.matricula_set.filter(status=STATUS_ATIVO).count()


class Fomento(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    sigla = models.CharField(max_length=10)

    def __str__(self):
        return self.sigla

    class Meta:
        verbose_name = 'Bolsa/Fomento'
        verbose_name_plural = 'Bolsas e Fomentos'


class Pesquisador(models.Model):
    nome = models.CharField('Nome completo', max_length=100, db_index=True)
    CPF = models.CharField(max_length=11, blank=True, null=True)
    sexo = models.CharField(max_length=1, choices=GENDER, null=True)
    raca = models.CharField('Raça/Cor', max_length=2, choices=RACE_COLOR, null=True)
    email = models.EmailField('E-mail principal', blank=True, null=True)
    email_alternativo = models.EmailField('E-mail alternativo', blank=True, null=True)
    id_lattes = models.CharField('Lattes Alfa', max_length=15, blank=True, null=True)
    id_cnpq = models.CharField('ID CNPQ', max_length=16, blank=True, null=True, unique=True)
    orcid = models.CharField('ORCID', max_length=20, blank=True, null=True)
    gscholar = models.CharField('Google Scholar', max_length=20, blank=True, null=True)
    id_funcional = models.CharField('Id.Externo', max_length=15, blank=True, null=True,
                                    help_text='Id.na Universidade (DRE, etc)')
    situacao = models.CharField('Titulação', max_length=1, choices=TIPO_TITULACAO, default=TITULACAO_GRADUACAO)
    status = models.CharField(max_length=1, choices=STATUS_ATIVIDADE, default=STATUS_ATIVO)
    dtupdate = models.DateField('Atualização Lattes', blank=True, null=True)
    atualizado = models.BooleanField(help_text='Sincronizado com o Lattes', default=False)

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Pesquisador(a)'
        verbose_name_plural = 'Pesquisadores'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = self.nome.upper()
        super().save(*args, **kwargs)

    @property
    def num_artigos(self):
        ano = date.today().year
        trienio = (ano, ano - 1, ano - 2)
        return self.producao_set.filter(tipo__cod_externo='Artigo', ano__in=trienio).count() or 0

    def num_projetos(self):
        count = self.pesquisadorprojeto_set.filter(projeto__status=STATUS_ATIVO).count()
        if count == 0:
            return mark_safe('<font color="red">0</font>')
        else:
            return '%d' % count

    num_projetos.short_description = 'Projetos'

    def dtupdate_html(self):
        if self.dtupdate < date.today() - timedelta(days=30):
            return mark_safe('<font color="red">%s</font>' % self.dtupdate)
        else:
            return self.dtupdate

    dtupdate_html.admin_order_field = 'dtupdate'

    def url_lattes(self):
        if self.id_lattes:
            return mark_safe(URL_LATTES % self.id_lattes)
        elif self.id_cnpq:
            return mark_safe('http://lattes.cnpq.br/%s' % self.id_cnpq)

    url_lattes.short_description = 'URL Lattes'

    def url_gscholar(self):
        if self.gscholar:
            return mark_safe('https://scholar.google.com/citations?hl=pt-BR&user=%s' % self.gscholar)

    url_gscholar.short_description = 'URL Google Scholar'


class PesquisadorPrograma(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Programa do Pesquisador'
        verbose_name_plural = 'Programas do Pesquisador'
        unique_together = (('pesquisador', 'programa'),)

    def __str__(self):
        return '%s' % self.programa

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        linha = LinhaPesquisa.objects.filter(programa=self.programa).first()
        if linha:
            ProfessorLinha.objects.get_or_create(professor=self.pesquisador, linha=linha)


class PesquisadorNomeCitacao(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    nome_citacao = models.CharField('Nome na citação', max_length=100)

    class Meta:
        verbose_name = 'Nome para Citação'
        verbose_name_plural = 'Nomes para Citação'

    def __str__(self):
        return '%s' % self.nome_citacao


class AlunoManager(models.Manager):
    def get_queryset(self):
        return super(AlunoManager, self).get_queryset().filter(matricula__isnull=False).distinct()


class Aluno(Pesquisador):
    objects = AlunoManager()

    class Meta:
        proxy = True
        verbose_name = 'Discente'

    def bolsista(self):
        return self.matricula_set.filter(status_bolsa=STATUS_ATIVO).count() > 0

    @property
    def turma(self):
        matricula = self.matricula_set.all().order_by('-ingresso')
        if matricula:
            return '%s/%s' % (matricula[0].curso, matricula[0].ingresso)
        else:
            return None

    @property
    def orientador(self):
        dset = Orientacao.objects.filter(aluno=self, status=STATUS_ATIVO)
        if dset:
            return '%s' % dset[0].orientador.nome
        else:
            return None

    def status_matricula(self):
        matricula = self.matricula_set.all().order_by('-ingresso')
        if matricula:
            return '%s' % matricula[0].get_status_display()
        else:
            return None


# Traz somente pesquisadores que sejam professores do programa
class ProfessorManager(models.Manager):
    def get_queryset(self):
        return super(ProfessorManager, self).get_queryset().filter(pesquisadorprograma__isnull=False).distinct()


class Professor(Pesquisador):
    objects = ProfessorManager()

    class Meta:
        proxy = True
        verbose_name = 'Professor(a) do Programa'
        verbose_name_plural = 'Professores/as do Programa'

    def save(self, *args, **kwargs):
        self.professor = True
        self.situacao = 'D'
        super().save(*args, **kwargs)

    def num_orientandos(self):
        return Orientacao.objects.filter(orientador=self, status=STATUS_ATIVO).count()

    num_orientandos.short_description = 'Orientandos atuais'

    def num_orientandos_concluidos(self):
        return Orientacao.objects.filter(orientador=self, status=STATUS_CONCLUIDA).count()

    num_orientandos_concluidos.short_description = 'Orientações concluídas'

    def status_lattes(self):
        return mark_safe('<a href="%s">%s</a>' % (
            reverse_lazy('admin:nucleo_producao_changelist') + '?q2=' + self.nome.replace(' ', '+'),
            localize(self.dtupdate)))

    status_lattes.short_description = 'Lattes'


class ProfessorLinha(models.Model):
    professor = models.ForeignKey(Professor, on_delete=models.PROTECT)
    linha = models.ForeignKey(LinhaPesquisa, on_delete=models.PROTECT)
    permanente = models.BooleanField(default=True)
    dtentrada = models.DateField('Ingresso', blank=True, null=True)
    dtsaida = models.DateField('Dt.Saída', blank=True, null=True)

    class Meta:
        unique_together = (('professor', 'linha'),)

    def __str__(self):
        return '%s' % self.linha

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.dtsaida:
            PesquisadorPrograma.objects.filter(pesquisador=self.professor, programa=self.linha.programa).delete()
        else:
            PesquisadorPrograma.objects.get_or_create(pesquisador=self.professor, programa=self.linha.programa)


class AlunoLinha(models.Model):
    aluno = models.ForeignKey(Aluno, on_delete=models.PROTECT)
    linha = models.ForeignKey(LinhaPesquisa, on_delete=models.PROTECT)
    dtentrada = models.DateField('Ingresso', blank=True, null=True)
    dtsaida = models.DateField('Dt.Saída', blank=True, null=True)

    def __str__(self):
        return '%s' % self.linha


class PesquisadorTitulacao(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    instituicao = models.ForeignKey(Instituicao, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=1, choices=TIPO_TITULACAO, default='G')
    curso_extenso = models.CharField('Nome do Curso', max_length=200)

    def __str__(self):
        return self.curso_extenso

    class Meta:
        verbose_name = 'Titulação do Pesquisador'
        verbose_name_plural = 'Titulações do Pesquisador'


class PesquisadorProjeto(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    projeto = models.ForeignKey(ProjetoPesquisa, on_delete=models.PROTECT)

    def __str__(self):
        return '%s' % self.pesquisador

    class Meta:
        verbose_name = 'Pesquisador do Projeto'
        verbose_name_plural = 'Pesquisadores do Projeto'


class Matricula(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT)
    ingresso = models.SmallIntegerField('Ano de Ingresso')
    status = models.CharField(max_length=1, choices=STATUS_MATRICULA, default='A')
    status_bolsa = models.CharField('Status da Bolsa', max_length=1, choices=STATUS_BOLSA, default='N')
    dtquali = models.DateTimeField('Data da Qualificação', blank=True, null=True)
    dtdefesa = models.DateTimeField('Data da Defesa', blank=True, null=True)
    dtaprovacao = models.DateField('Dt.Aprovação CD', blank=True, null=True)
    dtconclusao = models.DateField('Dt.Conclusão', blank=True, null=True, help_text='Entrega da Tese/Dissertação')
    trancamento = models.DateField('Data de Trancamento', blank=True, null=True)
    meses_previstos = models.IntegerField('Meses Previstos', default=24)
    titulo = models.TextField('Título', blank=True, null=True,
                              help_text='Título atual da Tese/Dissertação')
    obs = models.TextField('Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Matrícula'
        verbose_name_plural = 'Matrículas'

    def __str__(self):
        return '%s/%s %s' % (self.curso, self.ingresso, self.pesquisador)

    def save(self, *args, **kwargs):
        if not self.meses_previstos:
            if self.curso and self.curso.nivel == 'DO':
                self.meses_previstos = 48
        super().save(*args, **kwargs)

    def link(self):
        return u'<a href="%s">%s</a>' % (reverse_lazy('admin:nucleo_matricula_change', args=(self.pk,)), 'Matrícula')

    link.short_description = u'Matrícula'
    link.allow_tags = True

    @property
    def pesquisador_email(self):
        return nvl(self.pesquisador.email, '-')


class Orientacao(models.Model):
    orientador = models.ForeignKey(Professor, related_name='orientador', on_delete=models.PROTECT)
    aluno = models.ForeignKey(Aluno, related_name='aluno', on_delete=models.PROTECT)
    matricula = models.ForeignKey(Matricula, null=True, on_delete=models.PROTECT)
    coorientacao = models.BooleanField('Coorientação', default=False)
    status = models.CharField(max_length=1, choices=STATUS_ORIENTACAO, default=STATUS_ATIVO)

    class Meta:
        verbose_name = 'Orientação'
        verbose_name_plural = 'Orientações'

    def __str__(self):
        return self.orientador.nome

    @property
    def turma(self):
        return self.aluno.turma


class PesquisadorFomento(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    fomento = models.ForeignKey(Fomento, on_delete=models.PROTECT)
    dtinicio = models.DateField('Data de Início', blank=True, null=True)
    dtfim = models.DateField('Data de Fim', blank=True, null=True)
    obs = models.TextField('Observações')

    class Meta:
        verbose_name_plural = 'Pesquisadores'

    def __str__(self):
        return '%s (%s)' % (self.pesquisador, self.fomento)


class TipoProducao(models.Model):
    descricao = models.CharField(max_length=40)
    cod_externo = models.CharField(max_length=40)

    class Meta:
        verbose_name = 'Tipo de Produção Acadêmica'
        verbose_name_plural = 'Tipos de Produção Acadêmica'
        ordering = ('descricao',)

    def __str__(self):
        return '%s' % self.descricao


# Produção importada do Lattes.
# Como uma mesma produção é repetida para cada autor, o Odorico procura os duplicados para que somente uma produção
# entre no cálculo de produções do programa. Assim o campo ident_unico é calculado pelo hash do DOI ou quando este
# não existe, monta-se um hash a partir da combinação do ISSN+Sobrenome do Primeiro Autor+Título.
#
# O campo conta_sucupira indica se a produção será contabilizada no relatório de produção do Sucupira
# pois se uma produção tem o mesmo hash e for de pesquisadores do mesmo programa, somente uma delas será contabilizada
# Somente Artigos e Livros tem o atributo conta_sucupira preenchido.
#
class Producao(models.Model):
    class Status(models.TextChoices):
        ABERTO = 'A', 'Em aberto'
        IMPORTADO = 'I', 'Importado'
        EM_EDICAO = 'E', 'Editado'
        VALIDADO = 'V', 'Validado'

    class NaturezaObra(models.TextChoices):
        OBRA = 'O', 'Obra Única'
        ANAIS = 'A', 'Anais'
        COLECAO = 'C', 'Coleção'
        COLETANEA = 'L', 'Coletânea'
        DICIONARIO = 'D', 'Dicionário'
        ENCICLOPEDIA = 'E', 'Enciclopédia'

    class MeioDivulgacao(models.TextChoices):
        IMPRESSO = 'I'
        MAGNETICA = 'M', 'Mídia Magnética (fita, disquete, etc.)'
        DIGITAL = 'D', 'Mídia Digital (CD, DVD, Bluray, USB, etc.)'
        FILME = 'F', 'Filme (inclusive online)'
        HIPERTEXTO = 'H', 'Hipertexto(Website, blog etc.)'
        OUTRO = 'O', 'Outro'

    class TipoObra(models.TextChoices):
        CAPITULO = 'C', 'Capítulo'
        VERBETE = 'V', 'Verbete'
        APRESENTACAO = 'A', 'Apresentação'
        INTRODUCAO = 'I', 'Introdução'
        PREFACIO = 'P', 'Prefacio'
        POSFACIO = 'O', 'Posfácio'
        LIVRO = 'L', 'Obra completa(Livro)'
        COMPLETO = 'T', 'Trabalho Completo'
        RESUMO = 'R', 'Resumo'
        RESUMOX = 'X', 'Resumo Expandido'

    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    tipo = models.ForeignKey(TipoProducao, on_delete=models.PROTECT, verbose_name='Tipo de Produção')
    titulo = models.TextField('Título')
    descricao = models.TextField('Descrição Completa', blank=True, null=True)
    doi = models.CharField("DOI", max_length=200, blank=True, null=True, db_index=True)
    isbn = models.CharField("ISBN", max_length=13, blank=True, null=True, db_index=True)
    ano = models.SmallIntegerField()
    volume = models.CharField(max_length=20, blank=True, null=True)
    serie = models.CharField(max_length=20, blank=True, null=True)
    periodico = models.ForeignKey(Periodico, blank=True, null=True, on_delete=models.SET_NULL,
                                  help_text='Preencha ao menos 5 caracteres ou o ISSN')
    projeto = models.ForeignKey(ProjetoPesquisa, blank=True, null=True, on_delete=models.PROTECT)
    natureza_obra = models.CharField('Natureza da obra', max_length=1, blank=True, null=True,
                                     choices=NaturezaObra.choices)
    meio = models.CharField('Meio de Divulgação', max_length=1, blank=True, null=True, choices=MeioDivulgacao.choices)
    tipo_obra = models.CharField('Tipo da Obra', max_length=1, blank=True, null=True, choices=TipoObra.choices)
    organizacao = models.TextField('Editores/Coordenação/Organização', blank=True, null=True)
    editora = models.CharField(max_length=200, blank=True, null=True)
    cidade = models.CharField(max_length=200, blank=True, null=True)
    pais = models.CharField(max_length=30, blank=True, null=True)
    idioma = models.CharField(max_length=20, blank=True, null=True)
    sem_projeto = models.BooleanField('Produção externa ao Programa', default=False)
    ident_unico = models.CharField('Identificador Interno', max_length=32, blank=True, null=True, db_index=True)
    validacao = models.CharField('Validação', choices=Status.choices, max_length=1, default=Status.ABERTO)
    conta_sucupira = models.BooleanField('Contabilizado no Sucupira', default=False)
    comprovante = models.FileField('Comprovante', blank=True, null=True)
    doi_validado = models.BooleanField(default=False)
    url = models.URLField('URL', blank=True, null=True)

    class Meta:
        verbose_name = 'Produção Acadêmica'
        verbose_name_plural = 'Produção Acadêmica'

    @property
    def titulo_breve(self):
        if self.titulo:
            return u'%s' % self.titulo[:100]
        else:
            if self.descricao:
                return u'%s' % self.descricao[:100]
            else:
                return u'%d' % self.id

    @property
    def qualis(self):
        if self.periodico:
            return self.periodico.qualis
        else:
            return None

    def __str__(self):
        return '%s' % self.titulo

    def save(self, *args, **kwargs):
        self.ident_unico = generate_hash(self.titulo)
        super().save(*args, **kwargs)


class ProducaoAutor(models.Model):
    producao = models.ForeignKey(Producao, on_delete=models.PROTECT)
    autor = models.ForeignKey(Pesquisador, null=True, blank=True, on_delete=models.PROTECT)
    nome = models.CharField(max_length=100, null=True, blank=True)
    ordem = models.SmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Autor'
        verbose_name_plural = 'Autores'

    def __str__(self):
        if not self.autor:
            return '%s' % self.nome
        else:
            return '%s' % self.autor.nome

    @property
    def titulo(self):
        return self.producao.titulo

    @property
    def ano(self):
        return self.producao.ano

    @property
    def qualis(self):
        if self.producao.periodico:
            return self.producao.periodico.qualis


class ResumoAnual(models.Model):
    ABERTO = 'A'
    FECHADO = 'F'
    STATUS = (
        (ABERTO, 'Aberto'),
        (FECHADO, 'Fechado'),
    )

    ano = models.SmallIntegerField()
    status = models.CharField(max_length=1, choices=STATUS, default=ABERTO)
    dtregistro = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = 'Resumo Anual'
        verbose_name_plural = 'Resumos Anuais'

    def __str__(self):
        return '%d' % self.ano

    def total_pesquisadores(self):
        return RelatorioAnual.objects.filter(ano=self.ano).count()

    total_pesquisadores.short_description = 'Total de Relatórios'

    def total_em_edicao(self):
        return RelatorioAnual.objects.filter(ano=self.ano,
                                             status__in=(RelatorioAnual.EM_EDICAO,
                                                         RelatorioAnual.RESUMO_OK,
                                                         RelatorioAnual.CADASTRO_OK)).count()

    total_em_edicao.short_description = 'Em Edição'

    def total_aguardando(self):
        return RelatorioAnual.objects.filter(ano=self.ano, status=RelatorioAnual.VALIDADO).count()

    total_aguardando.short_description = 'Aguardando avaliação'

    def total_avaliados(self):
        return RelatorioAnual.objects.filter(ano=self.ano, status=RelatorioAnual.AVALIADO).count()

    total_avaliados.short_description = 'Avaliados'


class RelatorioAnual(models.Model):
    NAO_INICIADO = 'I'
    EM_EDICAO = 'E'  # Pesquisador iniciou o cadastro
    CADASTRO_OK = 'C'  # Cadastro validado
    RESUMO_OK = 'R'  # Cadastro e Resumo validado
    VALIDADO = 'V'  # Cadastro validado pelo sistema
    AVALIADO = 'A'  # Cadastro avaliado pelo orientador / coordenador
    STATUS = (
        (NAO_INICIADO, 'Não iniciado'),
        (EM_EDICAO, 'Em edição'),
        (CADASTRO_OK, 'Cadastro Ok'),
        (RESUMO_OK, 'Resumo Ok'),
        (VALIDADO, 'Validado'),
        (AVALIADO, 'Avaliado'),
    )

    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    ano = models.SmallIntegerField()
    tipo_bolsa = models.ForeignKey(Fomento, on_delete=models.PROTECT, null=True, blank=True,
                                   verbose_name='Tipo de Bolsa')
    descr_bolsa = models.CharField(verbose_name='Bolsa', max_length=100, null=True, blank=True)
    desenvolvimento = models.TextField(null=True, verbose_name='Desenvolvimento da Pesquisa',
                                       help_text='Descreva aqui os principais avanços de sua pesquisa de mestrado ou '
                                                 'doutorado alcançados neste semestre. Você deve elaborar um texto '
                                                 'substantivo de caráter acadêmico – e não meramente formal descrendo '
                                                 'atividades realizadas. Considere a revisão bibliográfica realizada, '
                                                 'coleta e análise de informações qualitativas e quantitativas, achados'
                                                 ' e interpretações desenvolvidas. Limite mínimo: 1000 palavras. '
                                                 'Limite máximo: 2000 palavras.')
    disciplinas = models.TextField(verbose_name='Disciplinas cursadas', null=True, blank=True)
    grupo_estudo = models.TextField(verbose_name='Grupos de Estudo ou Leitura', null=True, blank=True)
    grupo_pesquisa = models.TextField(verbose_name='Participação em Grupos do Programa', null=True, blank=True)
    part_pesquisa = models.TextField(verbose_name='Participação em Pesquisas do Programa', null=True, blank=True)
    part_extensao = models.TextField(verbose_name='Participação em Atividades de Extensão', null=True, blank=True)
    part_outras = models.TextField(verbose_name='Participação em outras atividades coletivas de pesquisa e/ou extensão',
                                   null=True, blank=True)
    part_discente = models.TextField(verbose_name='Participação em Instâncias de Representação Discente', null=True,
                                     blank=True)
    part_movimento = models.TextField(verbose_name='Participação em Coletivos e Movimentos da Universidade', null=True,
                                      blank=True)
    seminarios = models.TextField(verbose_name='Seminários do Programa', null=True, blank=True)
    premios = models.TextField(verbose_name='Prêmios e distinções', null=True, blank=True)
    outras_atividades = models.TextField(verbose_name='Outras atividades que considerar relevantes', null=True,
                                         blank=True)
    sandwich_universidade = models.CharField(verbose_name='Universidade', max_length=200, null=True, blank=True)
    sandwich_orientador = models.CharField(verbose_name='Orientador', max_length=200, null=True, blank=True)
    sandwich_periodo = models.CharField(verbose_name='Periodo', max_length=200, null=True, blank=True)
    sandwich_bolsa = models.CharField(verbose_name='Bolsa', max_length=200, null=True, blank=True)
    sandwich_descricao = models.CharField(verbose_name='Relato', max_length=200, null=True, blank=True,
                                          help_text='Descreva sua experiência durante o estágio sanduiche')
    status = models.CharField(max_length=1, choices=STATUS, default=NAO_INICIADO)
    aprovado = models.BooleanField(blank=True, null=True)
    comentario_orientador = models.TextField(blank=True, null=True)
    hash_auth = models.CharField(max_length=32, db_index=True)  # hash de autorização para o aluno
    hash_apr = models.CharField(max_length=32, db_index=True, null=True)  # Hash para o aprovador

    class Meta:
        verbose_name = 'Relatório de Produção'
        verbose_name_plural = 'Relatórios de Produção'

    def __str__(self):
        return f'{self.pesquisador} ({self.ano})'

    def alt_title(self):
        """Representação alternativa para o relatório anual"""
        try:
            aluno = Aluno.objects.get(pk=self.pesquisador_id)
            titulo = f'{aluno} - {aluno.turma} ({self.ano})'
        except Aluno.DoesNotExist:
            # O Pesquisador não é aluno, então retorna somente nome e ano do relatório
            titulo = str(self)

        return titulo

    @staticmethod
    def _avaliacao_anual_url(hash):
        return reverse_lazy('avaliacao_anual', args=(hash,))

    def get_absolute_url(self):
        return self._avaliacao_anual_url(self.hash_auth)

    def get_approval_url(self):
        return self._avaliacao_anual_url(self.hash_apr) + '?apr=1'

    def save(self, *args, **kwargs):
        if not self.hash_auth:
            self.hash_auth = generate_hash()
        if not self.hash_apr:
            self.hash_apr = generate_hash()

        if self.pk:
            if self.desenvolvimento_total > 1000:
                self.status = RelatorioAnual.RESUMO_OK

            if self.aprovado:
                self.status = self.AVALIADO

        super().save(*args, **kwargs)

    def send_edit_invite(self):
        return

    def send_approval_invite(self):
        return

    @property
    def resumo_ok(self):
        return self.status == RelatorioAnual.RESUMO_OK

    @property
    def desenvolvimento_total(self):
        """Retorna o total de palavras no campo desenvolvimento"""
        return len((self.desenvolvimento or '').split())
