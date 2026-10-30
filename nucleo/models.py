import hashlib
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.templatetags.admin_list import _boolean_icon
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.db.models import Count
from django.template import Template, Context
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.timezone import now

from qualis.models import Pais, Periodico
from utils.email import sendmail
from utils.fields import BRCPFField, DiaSemana
from utils.models import TipoProcessamento
from utils.stdlib import EMPTY_VALUES, localize, nvl
from .apps import URL_LATTES_VIEW, generate_24hash, generate_hash, log_object
from .managers import PesquisadorQuerySet

GENDER = (
    ('M', 'Masculino'),
    ('F', 'Feminino'),
    ('N', 'Prefere não declarar'),
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
    ('GR', 'Graduação'),
    ('ES', 'Especialização'),
    ('ME', 'Mestrado'),
    ('MP', 'Mestrado Profissional'),
    ('DO', 'Doutorado'),
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
STATUS_SOLICITADA = 'S'
STATUS_INATIVA = 'I'
STATUS_FINALIZADA = 'F'
STATUS_CANCELADA = 'X'
STATUS_PENDENTE = 'P'

STATUS_ATIVIDADE = (
    (STATUS_ATIVO, 'Ativa'),
    (STATUS_INATIVA, 'Inativa'),
)

STATUS_ATIVIDADE_M = (
    (STATUS_ATIVO, 'Ativo'),
    (STATUS_INATIVA, 'Inativo'),
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
    pais = models.ForeignKey(Pais, null=True, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Instituição'
        verbose_name_plural = 'Instituições'


class Programa(models.Model):
    instituicao = models.ForeignKey(Instituicao, on_delete=models.PROTECT)
    descricao = models.CharField('Descrição', max_length=100)
    cod_sucupira = models.CharField(max_length=20, blank=True, null=True)
    coordenacao = models.ForeignKey('Professor', on_delete=models.PROTECT, blank=True, null=True,
                                    verbose_name='Nome do/a Coordenador/a')
    endereco = models.TextField(blank=True, null=True)

    def __str__(self):
        return f'{self.instituicao.sigla} {self.descricao}'

    class Meta:
        verbose_name = 'Programa de Pós-Graduação'
        verbose_name_plural = 'Programas de Pós-Graduação'

    def num_professores(self):
        total = 0
        for linha in self.linhapesquisa_set.all():
            total += linha.num_professores()
        return total

    num_professores.short_description = "Núm.Docentes"

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
        return f'{self.descricao} ({self.programa.instituicao.sigla})'

    class Meta:
        verbose_name = 'Linha de Pesquisa'
        verbose_name_plural = 'Linhas de Pesquisa'

    def num_professores(self):
        return self.professorlinha_set.filter(dtsaida__isnull=True).count()

    num_professores.short_description = 'Docentes ativas/os'


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


class TipoCurso(models.Model):
    descricao = models.CharField('Descrição', max_length=60)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Tipo do Curso'
        verbose_name_plural = 'Tipos de Cursos'


class Curso(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT)
    tipo_curso = models.ForeignKey(TipoCurso, on_delete=models.PROTECT, blank=True, null=True)
    historico = models.BooleanField('Emite Histórico', default=False)
    controle_matricula = models.CharField('Controle do Número de Matrícula', max_length=1, blank=True, null=True,
                                          help_text='Identificador do tipo de curso que irá constar no número da matrícula')
    meses_conclusao = models.SmallIntegerField(blank=True, null=True,
                                               help_text='Número de meses para conclusão do curso')
    email_secretaria = models.EmailField(blank=True, null=True, help_text='Email da secretaria do curso')

    def __str__(self):
        return f'{self.programa}-{self.descricao}'

    def num_alunos(self):
        return self.matricula_set.filter(status=STATUS_ATIVO).count()

    num_alunos.short_description = 'Alunos matriculados'

    def num_alunos_total(self):
        return self.matricula_set.count()

    num_alunos.short_description = 'Total de Alunos'

    def save(self, *args, **kwargs):
        if self.controle_matricula:
            self.controle_matricula = self.controle_matricula.upper()
        super().save(*args, **kwargs)


class CursoControle(models.Model):
    ano = models.SmallIntegerField()
    controle = models.CharField(max_length=1)
    sequencial = models.SmallIntegerField(default=0)

    def __str__(self):
        return f'{self.ano}-{self.controle}'

    # calcula o digito verificador de um número hexadecimal
    def dv(self, hex_string):
        nr = str(int(hex_string, 16)).zfill(10)
        d = sum([i * int(x) for i, x in enumerate(nr)]) % 11
        return str(0 if d > 9 else d)

    def numero(self):
        sequencial = f'{self.sequencial}'.zfill(4)
        base = f'{self.ano}{self.controle}{sequencial}'
        digito = self.dv(base)
        return f'{self.ano}-{self.controle}-{sequencial}-{digito}'

    class Meta:
        verbose_name = 'Controle'
        verbose_name_plural = 'Controle de Matrículas'


class Curriculo(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    ano = models.SmallIntegerField()
    status = models.CharField('Situação', max_length=1, default='A', choices=STATUS_ATIVIDADE_M)

    class Meta:
        verbose_name = 'Currículo'
        verbose_name_plural = 'Currículos'

    def __str__(self):
        return self.descricao


class Disciplina(models.Model):
    class Status(models.TextChoices):
        ATIVA = 'A', 'Ativa'
        INATIVA = 'I', 'Inativa'
        PERMANENTE = 'P', 'Permanente'  # Sempre disponível

    titulo = models.CharField(max_length=100)
    ementa = models.TextField(blank=True, null=True)
    codigo = models.CharField('Código', max_length=20, blank=True, null=True)
    tipo = models.CharField('Tipo', max_length=1, choices=(('O', 'Obrigatória'), ('P', 'Optativa')), default='O')
    curriculo = models.ForeignKey(Curriculo, on_delete=models.PROTECT)
    creditos = models.IntegerField('Créditos', default=4)
    carga_horaria = models.IntegerField('Carga Horária', default=60)
    status = models.CharField('Situação', max_length=1, default='A', choices=Status.choices)

    class Meta:
        ordering = ('titulo',)

    def __str__(self):
        if self.codigo:
            return f'{self.titulo} ({self.codigo})'
        else:
            return self.titulo

    def turma_ativa(self):
        return self.turma_set.filter(periodo__status=Periodo.Status.ATIVO).last()


class DisciplinaCurso(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE)
    codigo = models.CharField('Código', max_length=20, blank=True, null=True)
    linhapesquisa = models.ForeignKey(LinhaPesquisa, on_delete=models.PROTECT, blank=True, null=True)

    class Meta:
        verbose_name = 'Disciplinas por Curso'
        verbose_name_plural = 'Disciplinas por Curso'


class Periodo(models.Model):
    class Meta:
        verbose_name = 'Período Acadêmico'
        verbose_name_plural = 'Períodos Acadêmicos'

    class Status(models.TextChoices):
        INICIADO = 'I', 'Não iniciado'
        ATIVO = 'A', 'Aberto'  # Inscrições abertas
        FECHADO = 'F', 'Encerrado'  # Fechado pela Secretaria

    class TipoPeriodo(models.TextChoices):
        SEMESTRE = 'S', 'Semestre'
        TRIMESTRE = 'T', 'Trimestre'

    ano = models.SmallIntegerField()
    tipo_periodo = models.CharField('Tipo', max_length=1, choices=TipoPeriodo.choices, default=TipoPeriodo.SEMESTRE)
    ident = models.SmallIntegerField(default=1)
    dt_fim_matricula = models.DateField('Dt.Limite para matrículas', blank=True, null=True)
    status = models.CharField('Situação', max_length=1, default=Status.INICIADO, choices=Status.choices)

    def __str__(self):
        return f'{self.ano}/{self.ident}'


class Turma(models.Model):
    periodo = models.ForeignKey(Periodo, on_delete=models.PROTECT)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT)
    titulo = models.CharField('Título', max_length=120, blank=True, null=True)
    num_alunos_max = models.IntegerField('Número Máximo de Alunos')
    externa = models.BooleanField(verbose_name='Aberta para matrícula externa', default=True)  # Terá ampla divulgação
    info_matricula = models.TextField('Informações para os alunos', blank=True, null=True)
    info_secretaria = models.TextField('Informações internas', blank=True, null=True)
    ava_id = models.CharField('AVA ID', max_length=10, blank=True, null=True)

    def __str__(self):
        return f'{self.disciplina} ({self.periodo})'

    def disciplina_codigo(self):
        return f'{self.disciplina.titulo} ({self.disciplina.codigo})'

    def calendario(self):
        return ' / '.join([f'{record}' for record in self.turmahorario_set.all()])

    def docentes(self):
        return ', '.join([f'{record}' for record in self.turmaprofessor_set.all()])

    def tot_discentes(self):
        return self.inscricao_set.count()

    tot_discentes.short_description = 'Discentes'

    def hash_avaliacao(self):
        base = str(self.id) + '-' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'


class TurmaProfessor(models.Model):
    turma = models.ForeignKey(Turma, on_delete=models.PROTECT)
    professor = models.ForeignKey('Pesquisador', on_delete=models.PROTECT)

    def __str__(self):
        return f'{self.professor}'


class TurmaHorario(models.Model):
    turma = models.ForeignKey(Turma, on_delete=models.PROTECT)
    dia_semana = models.CharField('Dia da Semana', max_length=1, choices=DiaSemana.choices)
    horario = models.TimeField('Início')
    horario_termino = models.TimeField('Término', null=True)

    def __str__(self):
        horario = f'{self.horario}'[:5]
        if self.horario_termino:
            horario += ' - ' + f'{self.horario_termino}'[:5]
        return f'{self.get_dia_semana_display()} ({horario})'


# Cursos que podem ter inscrições aceitas em uma determinada turma
class TurmaCurso(models.Model):
    turma = models.ForeignKey(Turma, on_delete=models.PROTECT)
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT)

    def __str__(self):
        return f'{self.curso}'


class Fomento(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    sigla = models.CharField(max_length=10)

    def __str__(self):
        return self.sigla

    class Meta:
        verbose_name = 'Bolsa/Fomento'
        verbose_name_plural = 'Bolsas e Fomentos'


class GrupoPesquisa(models.Model):
    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição')
    id_cnpq = models.CharField('ID CNPQ', max_length=16, blank=True, null=True, unique=True)

    def __str__(self):
        return self.nome

    def num_pesquisadores(self):
        count = self.pesquisadorgrupo_set.all().count()
        if count == 0:
            return mark_safe('<font color="red">0</font>')
        else:
            return '%d' % count

    num_pesquisadores.short_description = 'Integrantes'

    class Meta:
        verbose_name = 'Grupo de Pesquisa'
        verbose_name_plural = 'Grupos de Pesquisa'


class Pesquisador(models.Model):
    nome = models.CharField('Nome completo', max_length=130, db_index=True)
    CPF = BRCPFField(verbose_name='CPF', blank=True, null=True, unique=True)
    sexo = models.CharField(max_length=1, choices=GENDER, null=True)
    raca = models.CharField('Raça/Cor', max_length=2, choices=RACE_COLOR, null=True, blank=True)
    email = models.EmailField('E-mail principal', blank=True, null=True)
    email_alternativo = models.EmailField('E-mail alternativo', blank=True, null=True)
    id_lattes = models.CharField('Lattes Alfa', max_length=15, blank=True, null=True)
    id_cnpq = models.CharField('ID CNPQ', max_length=16, blank=True, null=True, unique=True)
    orcid = models.CharField('ORCID', max_length=20, blank=True, null=True, unique=True)
    gscholar = models.CharField('Google Scholar', max_length=20, blank=True, null=True)
    id_funcional = models.CharField('Id.Externo', max_length=15, blank=True, null=True,
                                    help_text='Id.na Universidade (DRE, etc)')
    situacao = models.CharField('Titulação', max_length=1, choices=TIPO_TITULACAO, default=TITULACAO_GRADUACAO)
    mini_bio = models.TextField('Mini-Biografia', blank=True, null=True)
    telefones = models.TextField('Telefones de Contato', blank=True, null=True)
    status = models.CharField(max_length=1, choices=STATUS_ATIVIDADE, default=STATUS_ATIVO)
    dtupdate = models.DateField('Atualização Lattes', blank=True, null=True)
    atualizado = models.BooleanField(help_text='Sincronizado com o Lattes', default=False)
    matricula_atual = models.ForeignKey('Matricula', related_name='matricula_atual', blank=True, null=True,
                                        on_delete=models.SET_NULL)
    fotografia = models.ImageField('Fotografia', upload_to='fotos/', blank=True, null=True)
    pais = models.ForeignKey(Pais, verbose_name='Nacionalidade', on_delete=models.PROTECT, blank=True, null=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)

    objects = PesquisadorQuerySet.as_manager()

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Pesquisador(a)'
        verbose_name_plural = 'Pesquisadores(as)'

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = self.nome.upper()
        super().save(*args, **kwargs)

    @property
    def num_artigos(self):
        ano = date.today().year
        quadrienio = (ano, ano - 1, ano - 2, ano - 3)
        return self.producao_set.filter(tipo__cod_externo='Artigo', ano__in=quadrienio).count() or 0

    def num_projetos(self):
        count = self.pesquisadorprojeto_set.filter(projeto__status=STATUS_ATIVO).count()
        if count == 0:
            return mark_safe('<font color="red">0</font>')
        else:
            return '%d' % count

    num_projetos.short_description = 'Projetos'

    def instituicoes(self):
        result = []
        for instituicao in self.pesquisadorinstituicao_set.all():
            result.append(instituicao.instituicao.nome)
        return ','.join(result)

    def fotografia_url(self):
        if self.fotografia:
            url = settings.SITE_URL + self.fotografia.url
        else:
            url = f'{settings.SITE_URL}/static/escola/img/default.png'
        return url

    def dtupdate_html(self):
        if self.dtupdate < date.today() - timedelta(days=30):
            return mark_safe('<font color="red">%s</font>' % self.dtupdate)
        else:
            return self.dtupdate

    dtupdate_html.admin_order_field = 'dtupdate'

    def url_lattes(self):
        if self.id_lattes:
            return mark_safe(URL_LATTES_VIEW % self.id_lattes)
        elif self.id_cnpq:
            return mark_safe('https://lattes.cnpq.br/%s' % self.id_cnpq)

    url_lattes.short_description = 'URL Lattes'

    def url_gscholar(self):
        if self.gscholar:
            return mark_safe('https://scholar.google.com/citations?hl=pt-BR&user=%s' % self.gscholar)

    url_gscholar.short_description = 'URL Google Scholar'

    def hash_confirmacao(self):
        base = str(self.id) + '-' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'

    def get_hash_cadastro(self):
        """Retorna o hash utilizado para validação da finalização do cadastro."""
        return generate_24hash(str(self.pk))

    def get_url_name_finalizacao(self):
        """Retorna o nome da URL de finalização do cadastro (deve ser implementado nas subclasses)."""
        raise NotImplementedError

    def get_url_kwargs_finalizacao(self):
        """Retorna os parâmetros da URL de finalização (deve ser implementado nas subclasses)."""
        raise NotImplementedError

    def url_finalizacao_cadastro(self):
        """Retorna a URL completa para finalização do cadastro."""
        link = reverse_lazy(self.get_url_name_finalizacao(), kwargs=self.get_url_kwargs_finalizacao())
        return f'{settings.SITE_URL}{link}'

    def cadastro_valido(self):
        sem_cpf = not self.CPF
        if sem_cpf:
            estrangeiro_sem_orcid = self.pais_id and self.pais.iso3 != 'BRA' and not self.orcid
            return not estrangeiro_sem_orcid
        else:
            return not sem_cpf

    def get_auth_username(self):
        """Retorna o CPF ou ORCID. Usado na rotina de primeiro acesso."""
        if self.CPF not in EMPTY_VALUES:
            return self.CPF

        return self.orcid


class PesquisadorPrograma(models.Model):
    class TipoVinculo(models.TextChoices):
        PERMANENTE = 'P', 'Permanente'
        COLABORADOR = 'C', 'Colaborador'
        VISITANTE = 'V', 'Visitante'

    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT)
    vinculo = models.CharField('Vínculo', max_length=1, choices=TipoVinculo.choices, default='P')
    interno = models.BooleanField('Interno', default=True,
                                  help_text='Indica se é servidor/funcionário da instituição')

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


class PesquisadorGrupo(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    grupo_pesquisa = models.ForeignKey(GrupoPesquisa, on_delete=models.PROTECT)
    status = models.CharField(max_length=1, choices=STATUS_ATIVIDADE, default=STATUS_ATIVO)

    class Meta:
        verbose_name = 'Grupo do Pesquisador'
        verbose_name_plural = 'Grupos de Pesquisa'
        unique_together = (('pesquisador', 'grupo_pesquisa'),)

    def __str__(self):
        return f'{self.grupo_pesquisa}'


# Onde o Pesquisador trabalha/trabalhou
class PesquisadorInstituicao(models.Model):
    class Status(models.TextChoices):
        ABERTO = 'A', 'Ativo'
        CONVIDADO = 'C', 'Convidado'
        INATIVO = 'I', 'Inativo'

    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    instituicao = models.ForeignKey(Instituicao, on_delete=models.PROTECT)
    status = models.CharField(max_length=1, choices=Status.choices, default=STATUS_ATIVO)
    dt_entrada = models.DateField('Dt.Entrada', null=True, blank=True)
    dt_saida = models.DateField('Dt.Saída', null=True, blank=True)

    class Meta:
        verbose_name = 'Instituição do Pesquisador'
        verbose_name_plural = 'Instituições do Pesquisador'
        unique_together = (('pesquisador', 'instituicao'),)

    def __str__(self):
        return f'{self.pesquisador}'


class PesquisadorFormacao(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    curso = models.CharField(max_length=100, null=True, blank=True)
    nome_instituicao = models.CharField(max_length=100, null=True, blank=True)
    nivel = models.CharField(max_length=2, choices=NIVEL_CURSO)
    instituicao = models.ForeignKey(Instituicao, on_delete=models.PROTECT, null=True, blank=True)
    ano_entrada = models.DateField('Ano Entrada', null=True, blank=True)
    ano_conclusao = models.DateField('Ano Conclusão', null=True, blank=True)

    class Meta:
        verbose_name = 'Formação do Pesquisador'
        verbose_name_plural = 'Formações do Pesquisador'
        ordering = ('-ano_entrada', )

    def __str__(self):
        return f'{self.pesquisador}'


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
        return (super(AlunoManager, self).get_queryset().filter(matricula_atual__isnull=False).
                select_related('matricula_atual', ))


class Aluno(Pesquisador):
    objects = AlunoManager()

    class Meta:
        proxy = True
        verbose_name = 'Discente'

    def bolsista(self):
        return self.matricula_set.filter(status_bolsa=STATUS_ATIVO).count() > 0

    def numero_matricula(self):
        matricula = self.matricula_atual
        if matricula:
            return matricula.numero_readonly()

    @property
    def turma(self):
        matricula = self.matricula_atual
        if matricula:
            return '%s/%s' % (matricula.curso, matricula.ingresso)
        else:
            return None

    def curso(self):
        if self.matricula_atual:
            return '%s' % self.matricula_atual.curso
        else:
            return None

    curso.short_description = 'Curso'

    @property
    def orientador(self):
        # Vai trazer o orientador ativo. Se não achar, traz o último orientador ou None caso não exista
        dset = Orientacao.objects.filter(aluno=self, status=Orientacao.Status.ATIVA, coorientacao=False)
        if dset:
            return dset[0].orientador
        else:
            return None

    @property
    def nome_orientador(self):
        # Vai trazer primeiro o orientador ativo. Se não achar, traz o último orientador
        orientador = self.orientador
        if orientador:
            return orientador.nome
        else:
            return 'Não definido'

    def status_matricula(self):
        if self.matricula_atual:
            return '%s' % self.matricula_atual.get_status_display()
        else:
            return None

    def get_url_name_finalizacao(self):
        return 'edit_aluno'

    def get_url_kwargs_finalizacao(self):
        return {'aluno_id': self.pk, 'aluno_hash': self.get_hash_cadastro()}


class AlunoRegistro(models.Model):
    aluno = models.OneToOneField(Aluno, on_delete=models.CASCADE)
    dtnascimento = models.DateField('Dt.Nascimento', null=True)
    tipo_identidade = models.CharField(max_length=1,
                                       choices=(('P', 'Passaporte'), ('R', 'Registro Civil'), ('O', 'Outro')),
                                       null=True)
    identidade = models.CharField(max_length=20, null=True, blank=True)
    orgao_identidade = models.CharField(max_length=20, null=True, blank=True)
    titulo_eleitor = models.CharField(max_length=20, null=True, blank=True)
    nome_pai = models.CharField(max_length=100, null=True, blank=True)
    nome_mae = models.CharField(max_length=100, null=True, blank=True)
    naturalidade = models.CharField(max_length=100, null=True, blank=True)
    nacionalidade = models.CharField(max_length=100, null=True, blank=True)
    certificado_militar = models.CharField(max_length=20, null=True, blank=True)
    dt_cadastro = models.DateField('Dt.Cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'Dados pessoais Discente'
        verbose_name_plural = 'Dados pessoais Discente'

    def __str__(self):
        return str(self.aluno) if self.pk else ''


# Traz somente pesquisadores que sejam professores do programa
class ProfessorManager(models.Manager):
    def get_queryset(self):
        return super(ProfessorManager, self).get_queryset().filter(pesquisadorprograma__isnull=False).distinct()


class Professor(Pesquisador):
    objects = ProfessorManager()

    class Meta:
        proxy = True
        verbose_name = 'Docente do Programa'
        verbose_name_plural = 'Docentes do Programa'

    def save(self, *args, **kwargs):
        self.professor = True
        self.situacao = TITULACAO_DOUTORADO
        super().save(*args, **kwargs)

    def num_orientandos(self):
        return Orientacao.objects.filter(orientador=self, status=Orientacao.Status.ATIVA).count()

    num_orientandos.short_description = 'Orientandos atuais'

    def num_pos_doc(self):
        return Orientacao.objects.filter(orientador=self, status=Orientacao.Status.ATIVA,
                                         matricula__curso__tipo_curso=8).count()

    num_orientandos.short_description = 'Orientandos Pós-Doc'

    def num_orientandos_concluidos(self):
        return Orientacao.objects.filter(orientador=self, status=Orientacao.Status.CONCLUIDA).count()

    num_orientandos_concluidos.short_description = 'Orientações concluídas'

    def status_lattes(self):
        return mark_safe('<a href="%s">%s</a>' % (
            reverse_lazy('admin:nucleo_producao_changelist') + '?q2=' + self.nome.replace(' ', '+'),
            localize(self.dtupdate)))

    status_lattes.short_description = 'Lattes'

    def get_url_name_finalizacao(self):
        return 'edit_professor'

    def get_url_kwargs_finalizacao(self):
        return {'professor_id': self.pk, 'professor_hash': self.get_hash_cadastro()}


class ProfessorLinha(models.Model):
    professor = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
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
            log_object(self.linha.programa, f'Docente descredenciada/o {self.professor} em {self.dtsaida}')
        else:
            PesquisadorPrograma.objects.get_or_create(pesquisador=self.professor, programa=self.linha.programa)
            log_object(self.linha.programa, f'Docente credenciada/o {self.professor}')


class PesquisadorProjeto(models.Model):
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    projeto = models.ForeignKey(ProjetoPesquisa, on_delete=models.CASCADE)

    def __str__(self):
        return '%s' % self.pesquisador

    class Meta:
        verbose_name = 'Pesquisador do Projeto'
        verbose_name_plural = 'Pesquisadores do Projeto'


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


class Matricula(models.Model):
    class Local(models.TextChoices):
        RIO = 'RIO', 'Rio'
        BRASILIA = 'BRASÍLIA', 'Brasília'

    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT)
    ingresso = models.SmallIntegerField('Ano de Ingresso')
    status = models.CharField(max_length=1, choices=STATUS_MATRICULA, default='A')
    dtmatricula = models.DateField('Dt.Matrícula')
    dtquali = models.DateTimeField('Data da Qualificação', blank=True, null=True)
    dtdefesa = models.DateTimeField('Data da Defesa', blank=True, null=True)
    dtaprovacao = models.DateField('Dt.Aprovação CD', blank=True, null=True) # não utilizar
    dtconclusao = models.DateField('Dt.Conclusão', blank=True, null=True,
                                   help_text='Entrega da Tese/Dissertação')
    trancamento = models.DateField('Data de Trancamento', blank=True, null=True)
    dtprevista = models.DateField('Dt.Prevista de Conclusão', blank=True, null=True)
    titulo = models.TextField('Título', blank=True, null=True,
                              help_text='Título atual da Tese/Dissertação')
    status_bolsa = models.CharField('Status da Bolsa', max_length=1, choices=STATUS_BOLSA, default='N')
    obs = models.TextField('Observações', blank=True, null=True)
    local = models.CharField('Local', max_length=20, choices=Local.choices, blank=True, null=True)

    # número de matrícula (externo ou interno)
    numero = models.CharField('Número', max_length=15, blank=True, null=True, unique=True)

    class Meta:
        verbose_name = 'Matrícula'
        verbose_name_plural = 'Matrículas'

    def __str__(self):
        if self.numero and self.numero[0] != '-':
            return f'{self.numero}'
        else:
            return f'{self.curso}/{self.ingresso} {self.pesquisador}'

    def save(self, *args, **kwargs):
        if not self.dtmatricula:
            self.dtmatricula = date(self.ingresso, 3, 1)

        if self.curso.meses_conclusao:
            meses = self.curso.meses_conclusao
        else:
            meses = 0

        dtprevista = date(self.ingresso, self.dtmatricula.month, 1) + relativedelta(months=meses)

        # verifica se existe prorrogação ou trancamento
        prorrogacoes = self.matriculaevento_set.filter(tipo_id__in=(6,7),
                                                       status=MatriculaEvento.Status.APROVACAO_CD).count()
        if prorrogacoes > 0:
            dtprevista = dtprevista + relativedelta(months=prorrogacoes*6)

        # cálculo da data prevista em função dos trancamentos
        meses = 0
        dtinicio = None
        for evento in self.matriculaevento_set.filter(tipo_id__in=(8,10),
                                                      status=MatriculaEvento.Status.APROVACAO_CD).order_by('dtevento'):
            if evento.tipo_id == 8:
                dtinicio = evento.dtevento
            else:
                if dtinicio:
                    meses = (evento.dtevento.year - dtinicio.year) * 12 + (evento.dtevento.month - dtinicio.month)
                dtinicio = None

        if dtinicio:
            hoje = date.today()
            meses = (hoje.year - dtinicio.year) * 12 + (hoje.month - dtinicio.month)

        if meses > 0:
            dtprevista = dtprevista + relativedelta(months=meses)

        if self.dtprevista != dtprevista:
            self.dtprevista = dtprevista

        super().save(*args, **kwargs)

        # Agenda a criação do número de matrícula (será feita via management gen_num_matricula)
        if not self.numero and self.curso.tipo_curso:
            if self.curso.controle_matricula:
                self.numero = f'{-self.id}'
                super().save(*args, **kwargs)

        # indica que o pesquisador agora é um aluno
        if self.status == 'A' and (
                self.pesquisador.matricula_atual is None or self.pesquisador.matricula_atual.ingresso < self.ingresso):
            self.pesquisador.matricula_atual = self
            self.pesquisador.save()

        # marca as orientações ativas como concluídas caso a defesa seja preenchida
        if self.dtdefesa:
            for orientacao in self.orientacao_set.filter(status=STATUS_ATIVO):
                orientacao.status = STATUS_CONCLUIDA
                orientacao.save()
                log_object(orientacao, f'Defesa realizada em {self.dtdefesa}. Orientações finalizadas')

        # caso a conclusão de um curso anterior seja feita após uma nova matrícula, a matricula atual deve ser atualizada
        if self.status != 'A':
            self.pesquisador.matricula_atual = self.pesquisador.matricula_set.order_by('ingresso').last()
            self.pesquisador.save()
            log_object(self.pesquisador, 'Matrícula atualizada')

    def numero_readonly(self):
        if not self.curso.controle_matricula:
            return self.pesquisador.id_funcional
        else:
            if self.numero:
                if self.numero[0] == '-':
                    return 'Em processamento'
            return self.numero or '-'
    numero_readonly.short_description = u'Matrícula'

    def link(self):
        return u'<a href="%s">%s</a>' % (reverse_lazy('admin:nucleo_matricula_change', args=(self.pk,)), 'Matrícula')

    link.short_description = u'Matrícula'
    link.allow_tags = True

    @property
    def hash(self):
        return f'{self.id}-'+generate_hash(f'{self.id}-{settings.SECRET_KEY}')

    @property
    def orientador_atual(self):
        orientacao = Orientacao.objects.filter(matricula=self,
                                               coorientacao=False).exclude(
            status=Orientacao.Status.CANCELADA
        ).select_related('orientador').only('id','orientador__nome').first()
        if orientacao:
            return orientacao.orientador.nome
        else:
            return ''

    @property
    def coorientador(self):
        orientacao = Orientacao.objects.filter(matricula=self,
                                               coorientacao=True).exclude(
            status=Orientacao.Status.CANCELADA
        ).select_related('orientador').only('id','orientador__nome').first()
        if orientacao:
            return orientacao.orientador.nome
        else:
            return ''

    @property
    def pesquisador_email(self):
        return nvl(self.pesquisador.email, '-')

    def delete(self, *args, **kwargs):
        if not self.pesquisador.matricula_atual or self.pesquisador.matricula_atual.id == self.id:
            self.pesquisador.matricula_atual = self.pesquisador.matricula_set.exclude(id=self.id).order_by(
                'ingresso').last()
            self.pesquisador.save()
        super().delete(*args, **kwargs)


class Orientacao(models.Model):
    class Status(models.TextChoices):
        SOLICITADA = 'S', 'Solicitada'
        PENDENTE = 'P', 'Aguardando CD'
        ATIVA = 'A', 'Ativa'
        CONCLUIDA = 'C', 'Concluída'
        CANCELADA = 'X', 'Cancelada'

    orientador = models.ForeignKey(Pesquisador, related_name='orientador', on_delete=models.PROTECT)
    aluno = models.ForeignKey(Aluno, related_name='aluno', on_delete=models.PROTECT)
    matricula = models.ForeignKey(Matricula, null=True, on_delete=models.PROTECT)
    coorientacao = models.BooleanField('Coorientação', default=False)
    dt_inicio = models.DateField('Início da Orientação', blank=True, null=True)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.ATIVA)

    class Meta:
        verbose_name = 'Orientação'
        verbose_name_plural = 'Orientações'

    def __str__(self):
        return self.orientador.nome

    @property
    def turma(self):
        return self.aluno.turma

    def orientacao_url(self):
        return mark_safe(f'<a href="/admin/nucleo/orientacao/{self.id}">{self.orientador.nome}</a>')

    orientacao_url.short_description = u'Orientação'
    orientacao_url.allow_tags = True

    @property
    def matricula_url(self):
        if self.matricula:
            return f'/admin/nucleo/matricula/{self.matricula.id}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        log_object(self.aluno, f'Orientação adicionada para {self.orientador}')
        log_object(self.orientador, f'Nova(o) orientanda(o): {self.aluno}')


class Inscricao(models.Model):
    class Meta:
        verbose_name = 'Inscrição'
        verbose_name_plural = 'Inscrições'
        ordering = ('turma__periodo', 'dtinscricao',)

    class Status(models.TextChoices):
        MATRICULADO = 'M', 'Matriculado'
        APROVADO = 'A', mark_safe('<font color="green">Aprovado</font>')
        TRANCADO = 'T', 'Trancada'
        DISPENSA = 'D', 'Dispensa'
        ABANDONO = 'N', 'Abandono não justificado'
        REP_FALTA = 'F', mark_safe('<font color="red">Reprovado por faltas</font>')
        REPROVADO = 'R', mark_safe('<font color="red">Reprovado</font>')
        OUVINTE = 'O', 'Ouvinte'

    turma = models.ForeignKey(Turma, on_delete=models.PROTECT)
    aluno = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    matricula = models.ForeignKey(Matricula, on_delete=models.PROTECT, null=True,
                                  blank=True)  # pode ser nulo por conta de alunos externos
    conceito = models.CharField(max_length=1, default='X')
    status = models.CharField('Status', choices=Status.choices, max_length=1, default=Status.MATRICULADO)
    obs = models.TextField(u'Observações', blank=True, null=True)
    dtinscricao = models.DateTimeField(u'Data de inscrição', auto_now_add=True)

    def __str__(self):
        return '%s/%s' % (self.turma, self.aluno)

    def save(self, *args, **kwargs):
        if self.status in (Inscricao.Status.MATRICULADO,Inscricao.Status.APROVADO,
                           Inscricao.Status.REPROVADO, Inscricao.Status.REP_FALTA):
            if self.conceito == 'D':
                self.status = Inscricao.Status.REPROVADO
            elif self.conceito == 'F':
                self.status = Inscricao.Status.REP_FALTA
            elif self.conceito in ('A', 'B', 'C'):
                self.status = Inscricao.Status.APROVADO
        else:
            self.conceito = 'X'
        super().save(*args, **kwargs)


class BaseOcorrenciaValidator:
    """
    Classe base para validação de templates de TipoOcorrencia.

    Fornece um contexto padrão com instâncias reais do banco (matricula, aluno,
    orientacao, orientador, ocorrencia). Subclasses podem estender esse contexto
    via `super().get_mock_context() | {...}` para incluir variáveis específicas
    do grupo de ocorrências.

    A função `validate()` executa a renderização em modo dry-run: se o template
    contiver chaves inválidas ou sintaxe malformada, lança exceção capturada por
    `TipoOcorrencia.validate_templates()`.
    """

    def __init__(self, tipo_ocorrencia):
        self.tipo_ocorrencia = tipo_ocorrencia

    def get_mock_context(self):
        matricula = Matricula.objects.first()
        aluno = matricula.pesquisador
        orientacao = Orientacao.objects.first()
        orientador = orientacao.orientador
        ocorrencia = MatriculaEvento.objects.first()
        link = ''

        return {
            'matricula': matricula, 'aluno': aluno, 'orientacao': orientacao, 'orientador': orientador,
            'ocorrencia': ocorrencia, 'link': link,
        }

    def validate(self):
        ctx = self.get_mock_context()
        if self.tipo_ocorrencia.template:
            self.tipo_ocorrencia.template.format(**ctx)
        for tiponotificacao in self.tipo_ocorrencia.tiponotificacao_set.all():
            tiponotificacao.texto.format(**ctx)


class OrientacaoValidator(BaseOcorrenciaValidator):
    """
    Validator para o tipo 1 (Solicitação de Orientação).
    """

    def get_mock_context(self):
        context = super().get_mock_context()
        return context | {'coorientador_se_houver': ''}


class BancaValidator(BaseOcorrenciaValidator):
    """
    Validator para os tipos 2-5 (Homologação de Defesa e Qualificação).
    """

    def get_mock_context(self):
        context = super().get_mock_context()
        return context | {'horario': '', 'modalidade': ''}


class ProrrogacaoValidator(BaseOcorrenciaValidator):
    """
    Validator para os tipos 6-8 (Prorrogação de Defesa, Prorrogação de
    Qualificação e Trancamento).
    """

    def get_mock_context(self):
        context = super().get_mock_context()
        del context['orientador']
        return context | {'nome_orientador': '',}

TIPO_OCORRENCIA_VALIDATORS = {
    1: OrientacaoValidator,
    2: BancaValidator,
    3: BancaValidator,
    4: BancaValidator,
    5: BancaValidator,
    6: ProrrogacaoValidator,
    7: ProrrogacaoValidator,
    8: ProrrogacaoValidator,
   10: ProrrogacaoValidator,
   11: ProrrogacaoValidator,
}


class TipoOcorrencia(models.Model):
    class Status(models.TextChoices):
        ATIVO = 'A', u'Ativo'
        INATIVO = 'D', 'Desabilitado'

    descricao = models.CharField('Descrição', max_length=100)
    detalhe = models.TextField(blank=True, null=True)
    template = models.TextField('Texto base', blank=True, null=True)
    url_requerimento = models.CharField('URL do formulário', max_length=120, blank=True, null=True)
    status = models.CharField('Status', choices=Status.choices, max_length=1, default=Status.ATIVO)
    cursos = models.ManyToManyField(Curso, verbose_name='Cursos aceitos')

    class Meta:
        verbose_name = 'Tipo de Ocorrência'
        verbose_name_plural = 'Tipos de Ocorrências da Matrícula'
        ordering = ('id',)

    def __str__(self):
        return self.descricao

    def validate_templates(self, request):
        try:
            validator_cls = TIPO_OCORRENCIA_VALIDATORS.get(self.pk)
            if validator_cls:
                validator = validator_cls(self)
                validator.validate()
            else:
                messages.warning(request, f'Validador não implementado para este Tipo de Ocorrência')
            return True
        except Exception as e:
            messages.warning(request, f'Erro: {type(e).__name__} - {e}. Tipo de Ocorrência desabilitada')
            return False


class TipoNotificacao(models.Model):
    class Fluxo(models.TextChoices):
        CRIACAO = 'C', 'Notificação Requerente'
        SECRETARIA = 'S', 'Notificação Secretaria'
        ORIENTADOR = 'O', 'Notificação para o Orientador'
        APROVACAO = 'A', 'Aprovado pelo orientador'

    tipo_ocorrencia = models.ForeignKey(TipoOcorrencia, on_delete=models.CASCADE)
    destinatario = models.CharField(choices=Fluxo.choices, max_length=2)
    texto = models.TextField()

    class Meta:
        verbose_name = 'Tipo de Notificação'
        verbose_name_plural = 'Tipos de Notificações'

    def __str__(self):
        return f'{self.tipo_ocorrencia}/{self.destinatario}'


class TipoDocumento(models.Model):
    descricao = models.CharField('Descrição', max_length=100)
    chave = models.CharField('Chave Interna', max_length=10)

    class Meta:
        verbose_name = 'Tipo de Documento'
        verbose_name_plural = 'Tipos de Documentos'

    def __str__(self):
        return self.descricao


class Documento(models.Model):
    tipo = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT)
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()
    anexo = models.FileField('Comprovante', upload_to='anexos/', blank=True, null=True)
    validado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def __str__(self):
        return f'{self.tipo}'


class AtaReuniao(models.Model):
    descricao = models.CharField('Descrição', max_length=100, unique=True)
    dt = models.DateField('Data', blank=True, null=True)
    arquivo = models.FileField(upload_to='atas/', blank=True, null=True)

    class Meta:
        verbose_name = 'Ata da Reunião'
        verbose_name_plural = 'Atas de Reuniões Deliberativas'

    def __str__(self):
        return f'{self.descricao}'


class MatriculaEvento(models.Model):
    class Modalidade(models.TextChoices):
        PRESENCIAL = 'P', 'Presencial'
        HIBRIDA = 'H', 'Híbrida'

    class Status(models.TextChoices):
        EM_EDICAO = 'E', 'Em Edição'
        FINALIZADO = 'F', 'Aguardando aprovação do orientador'
        AGUARDANDO_CD = 'G', 'Aguardando aprovação da CD'
        APROVACAO_ORIENTADOR = 'A', 'Aprovado pelo orientador'
        APROVACAO_CD = 'C', 'Aprovado pela CD'
        CANCELADO = 'X', 'Cancelado'
        NAO_APROVADO = 'Z', 'Não Aprovado pela CD'

    matricula = models.ForeignKey(Matricula, on_delete=models.PROTECT)
    tipo = models.ForeignKey(TipoOcorrencia, on_delete=models.PROTECT)
    descricao = models.TextField('Descrição', blank=True, null=True)
    dtevento = models.DateField('Dt.Evento')
    horario = models.TimeField('Horário', blank=True, null=True)
    local = models.TextField('Local', blank=True, null=True)
    modalidade = models.CharField(max_length=1, choices=Modalidade.choices, blank=True, null=True)
    titulo_trabalho = models.TextField('Título do Trabalho', blank=True, null=True)
    justificativa = models.TextField('Justificativa', blank=True, null=True)
    dtinclusao = models.DateTimeField(auto_now_add=True)
    obs = models.TextField('Observações', blank=True, null=True)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.EM_EDICAO)
    dtaprovacao = models.DateTimeField(blank=True, null=True)
    ata_reuniao = models.ForeignKey(AtaReuniao, blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'Ocorrência'
        verbose_name_plural = 'Ocorrências'
        ordering = ('matricula', 'dtevento',)

    def __str__(self):
        return f'{self.dtevento} {self.tipo}'

    def ocorrencia_url(self):
        reversed_url = reverse('admin:nucleo_matriculaevento_change', args=(self.pk,))
        return mark_safe(f'<a href={reversed_url}>{self.pk}</a>')
    ocorrencia_url.short_description = u'Ocorrência'
    ocorrencia_url.allow_tags = True

    def link_externo(self):
        if self.id and self.tipo.id in [2,3,4,5]:
            reversed_url = reverse('defesa', args=(self.matricula.pesquisador.id,self.id))
            return mark_safe(f'<a href={reversed_url}>Link Público</a>')
        else:
            return '-'
    ocorrencia_url.short_description = u'Link Público'
    ocorrencia_url.allow_tags = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Se for solicitação de orientação for aprovado na CD, marcar a Orientação como ativa
        if self.status == self.Status.APROVACAO_CD:
            if self.tipo.id == 1:
                Orientacao.objects.filter(matricula=self.matricula,
                                          status__in=(Orientacao.Status.SOLICITADA,
                                                      Orientacao.Status.PENDENTE)).update(
                    status=Orientacao.Status.ATIVA)
            elif self.tipo.id in (2, 3, 4, 5):
                # se for homologação de defesa
                if self.tipo.id in (2,3) and not self.matricula.dtdefesa:
                    self.matricula.dtdefesa = datetime(self.dtevento.year,self.dtevento.month,self.dtevento.day,
                                                       self.horario.hour, self.horario.minute)
                    log_object(self.matricula,f'Defesa aprovada em CD e agendada para {self.dtevento}')
                if self.tipo.id in (4, 5) and not self.matricula.dtquali:
                    self.matricula.dtquali = datetime(self.dtevento.year,self.dtevento.month,self.dtevento.day,
                                                       self.horario.hour, self.horario.minute)
                    log_object(self.matricula, f'Qualificação aprovada em CD e agendada para {self.dtevento}')
                if self.titulo_trabalho:
                    self.matricula.titulo = self.titulo_trabalho
                self.matricula.save()

            # trancamento
            elif self.tipo.id == 8:
                self.matricula.status = "T"
                self.matricula.trancamento = self.ata_reuniao.dt if self.ata_reuniao else self.dtevento
                self.matricula.save(update_fields=["status", "trancamento"])
                log_object(self.matricula,'Matrícula trancada')

            # reativacao
            elif self.tipo.id == 10:
                self.matricula.status = "A"
                self.matricula.save(update_fields=["status", "dtprevista"])
                log_object(self.matricula,'Matrícula reativada')

    def solicita_aprovacao_orientador(self, orientador):
        # Gerar hash
        hash_id_matricula_evento = generate_hash(str(self.id))

        # Criar URL de aprovação
        link = reverse('solicitacao_defesa_aprovacao', kwargs={
            'hash_id_matricula_evento': hash_id_matricula_evento
        })
        link = f"{settings.SITE_URL}{link}"
        aluno = self.matricula.pesquisador
        ocorrencia = self
        matricula = self.matricula

        # Enviar o e-mail do orientador
        modelo = TipoNotificacao.objects.filter(tipo_ocorrencia=self.tipo,
                                                destinatario=TipoNotificacao.Fluxo.ORIENTADOR).first()
        if modelo:
            mensagem = modelo.texto.format(**locals())
            sendmail('Pedido de Aprovação de Banca', [orientador.email], message=mensagem)
        else:
            sendmail('Pedido de Aprovação de Banca', [self.matricula.curso.email_secretaria,],
                     message=f'Texto para o orientador não definido: {self.tipo.descricao}')

    def notifica_banca_agendada(self):
        """
        Envia o e-mail 'Banca aprovada e agendada' para a lista de 'Destinatários de Agendamento de Bancas'.
        Retorna a qtd de destinatários.
        """
        # ListaContato vive no app escola (opcional, flag ESCOLA): acesso tardio e protegido.
        try:
            listacontato_cls = apps.get_model('escola', 'ListaContato')
            destinatarios = list(
                listacontato_cls.objects.listacontato_agendamento_banca()
                .values_list('contato__email', flat=True).distinct()
            )
        except LookupError:
            destinatarios = []

        membros_banca = (
            self.matriculaeventopesquisador_set
            .select_related('pesquisador', 'evento__matricula')
        )
        for membro in membros_banca:
            if membro.pesquisador.email:
                destinatarios.append(membro.pesquisador.email)

        html = render_to_string('email_banca_agendada.html', {
            'titulo': " ".join(self.tipo.descricao.split()[-3:]),
            'matricula_evento': self,
            'membros_banca': membros_banca,
        })
        sendmail("Banca aprovada e agendada", destinatarios, message=html)

        return len(destinatarios)


class MatriculaEventoPesquisador(models.Model):
    class Meta:
        verbose_name = 'Participante'
        verbose_name_plural = 'Participantes do Evento'
        ordering = ('evento', 'ordem',)

    class Status(models.TextChoices):
        EM_EDICAO = 'E', 'Em Edição'
        VALIDADO = 'V', 'Validado'
        CONFIRMADO = 'C', 'Confirmado'

    evento = models.ForeignKey(MatriculaEvento, on_delete=models.CASCADE)
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT, blank=True, null=True)
    externo = models.BooleanField()
    suplente = models.BooleanField()
    ordem = models.SmallIntegerField()
    instituicao = models.CharField(max_length=60, blank=True, null=True)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.EM_EDICAO)

    def __str__(self) -> str:
        status = f'{self.pesquisador}'
        if self.externo:
            status += ' (Externo)'
        if self.suplente:
            status += ' (Suplente)'
        return status

    def link_lattes(self):
        url = self.pesquisador.url_lattes()
        if url:
            return mark_safe(f'{self.pesquisador.nome}<a href={url} style="margin-left:10px">Link Lattes</a>')
        else:
            return self.pesquisador.nome

class TipoProducao(models.Model):
    descricao = models.CharField(max_length=40)
    cod_externo = models.CharField(max_length=40)
    edicao = models.BooleanField(default=True)  # Permite criar registro manualmente
    categoria = models.CharField(max_length=1, choices=(('B', 'Bibliográfica'),
                                                        ('T', 'Técnica'),
                                                        ('A', 'Artística')), default='T')

    class Meta:
        verbose_name = 'Tipo de Produção Acadêmica'
        verbose_name_plural = 'Tipos de Produção Acadêmica'
        ordering = ('descricao',)

    def __str__(self):
        return '%s' % self.descricao


class AreaImpacto(models.Model):
    descricao = models.CharField(max_length=80)

    class Meta:
        verbose_name = 'Área impactada pela produção'
        verbose_name_plural = 'Áreas de Impacto'
        ordering = ('descricao',)

    def __str__(self):
        return '%s' % self.descricao


class SetorEconomico(models.Model):
    descricao = models.CharField('Descrição', max_length=100)
    edicao = models.BooleanField(default=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Setor Econômico'
        verbose_name_plural = 'Setores Econômicos'
        ordering = ['descricao', ]


class NaturezaTexto(models.Model):
    descricao = models.CharField('Descrição', max_length=200)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Natureza do Texto'
        verbose_name_plural = 'Naturezas do Texto'
        ordering = ['descricao', ]


# Produção Acadêmica/Profissional.
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

    # específica o tipo de contéudo dentro de uma coleção/evento
    class TipoObra(models.TextChoices):
        CAPITULO = 'C', 'Capítulo'
        VERBETE = 'V', 'Verbete'
        APRESENTACAO = 'A', 'Apresentação'
        INTRODUCAO = 'I', 'Introdução'
        PREFACIO = 'P', 'Prefacio'
        POSFACIO = 'F', 'Posfácio'
        COMPLETO = 'T', 'Trabalho Completo'
        RESUMO = 'R', 'Resumo'
        RESUMOX = 'X', 'Resumo Expandido'
        # específicos para Eventos
        CURADORIA = '1', 'Curadoria'
        MONTAGEM = '2', 'Montagem'
        MUSEOGRAFIA = '3', 'Museografia'
        ORGANIZACAO = '4', 'Organização'
        OUTRA = '5', 'Outra'
        # específico para Mat.Didático
        EDICAO = '6', 'Edição'
        EDITORACAO = '7', 'Editoração'
        # Curso
        DOCENTE = 'D', 'Docente'

    # TODO: Cresceu muito: em nova versão temos que transformar em uma tabela
    # Especifica o sub-tipo da produção
    class NaturezaObra(models.TextChoices):
        ARTIGO = 'A', 'Artigo Completo'
        RESUMOS = 'R', 'Resumo'
        RESUMO = 'X', 'Resumo Expandido'
        LIVRO = 'L', 'Livro'
        COLECAO = 'C', 'Coleção'
        COLETANEA = 'T', 'Coletânea'
        CATALOGO = 'G', 'Catálogo'
        ANAIS = 'N', 'Anais'
        DICIONARIO = 'D', 'Dicionário'
        ENCICLOPEDIA = 'E', 'Enciclopédia'
        PERIODICO = 'P', 'Periódico'
        OUTRA = 'O', 'Outra'
        # Eventos
        CONCERTO = '1', 'Concerto'
        CONCURSO = '2', 'Concurso'
        EXPOSICAO = '3', 'Exposição'
        FESTIVAL = '4', 'Festival'

        # Apresentação de Trabalho
        COMUNICACAO = '5', 'Comunicação'
        CONFERENCIA = '6', 'Conferência'
        CONGRESSO = '7', 'Congresso'
        SEMINARIO = '8', 'Seminário'
        ENTREVISTA = 'e', 'Entrevista'
        COMENTARIO = 'c', 'Comentário'
        MESA_REDONDA = 'm', 'Mesa Redonda'
        SITE = 's', 'Site'
        BLOG = 'b', 'Blog'

    # Especifica o objetivo do conteúdo
    class NaturezaConteudo(models.TextChoices):
        DIDATICA = 'D', 'Didática'
        TECNICA = 'M', 'Técnica/Manual'
        ARTISTICA = 'A', 'Artística'
        TRADUCAO = 'T', 'Tradução'
        RELATO = 'R', 'Relato Profissional'
        RESULTADO = 'P', 'Resultado de Projeto de Pesquisa'

        # Cursos
        ESPECIALIZACAO = 'E', 'Especialização'
        APERFEICOAMENTO = 'F', 'Aperfeiçoamento'
        EXTENSAO = 'X', 'Extensão'
        OUTRA = 'O', 'Outro'

    class MeioDivulgacao(models.TextChoices):
        IMPRESSO = 'I', 'Impresso'
        MAGNETICA = 'M', 'Mídia Magnética (fita, disquete, etc.)'
        DIGITAL = 'D', 'Mídia Digital (CD, DVD, Bluray, USB, etc.)'
        FILME = 'F', 'Filme (inclusive online)'
        HIPERTEXTO = 'H', 'Hipertexto(Website, blog etc.)'
        OUTRO = 'O', 'Outro'

    class TipoFinanciamento(models.TextChoices):
        PROPRIO = 'P', 'Própria Editora'
        EDITAL = 'E', 'Edital de Fomento'
        EDITAL_NACIONAL = 'N', 'Agência de Fomento Nacional'
        EDITAL_INTERNACIONAL = 'I', 'Agência de Fomento Internacional'
        ASSOCIACAO = 'A', 'Associação Científica/Profissional'
        PARCERIA = 'C', 'Cooperação/Parceria'
        OUTRO = 'O', 'Outro'
        NENHUM = 'X', 'Não houve'

    class NivelImpacto(models.TextChoices):
        ALTO = 'A', 'Alto'
        MEDIO = 'M', 'Médio'
        BAIXO = 'B', 'Baixo'

    class TipoImpacto(models.TextChoices):
        POTENCIAL = 'P', 'Potencial'
        REAL = 'R', 'Real'

    class TipoAcesso(models.TextChoices):
        RESTRITO = 'R', 'Restrito'
        ABERTO = 'A', 'Irrestrito/Aberto'

    class Complexidade(models.TextChoices):
        ALTO = 'A', 'Alta'
        MEDIO = 'M', 'Média'
        BAIXO = 'B', 'Baixa'

    class Abrangencia(models.TextChoices):
        INTERNACIONAL = 'I', 'Internactional'
        NACIONAL = 'N', 'Nacional'
        REGIONAL = 'R', 'Regional'
        LOCAL = 'L', 'Local'

    class TipoEditora(models.TextChoices):
        INT_COMERCIAL = 'I', 'Estrangeira Comercial'
        INT_UNIVERSITARIA = 'U', 'Estrangeira Universitária'
        OUTRA = 'O', 'Outra'
        NAC_COMERCIAL = 'N', 'Editora Brasileira Comercial'
        NAC_UNIVERSITARIA = 'V', 'Editora Universitária Brasileira'
        INST_CIENTIFICAO = 'C', 'Instituição Científica'
        PROGRAMA = 'P', 'Programa'
        IES_PROGRAMA = 'R', 'IES do Programa'

    class ConselhoEditorial(models.TextChoices):
        NACIONAL = 'N', 'Membros nacionais'
        INTERNACIONAL = 'I', 'Membros internacionais'
        OUTRA = 'O', 'Outra'
        NA = 'A', 'Não se aplica'

    class Premiacao(models.TextChoices):
        NACIONAL = 'N', 'Membros nacionais'
        INTERNACIONAL = 'I', 'Membros internacionais'
        NA = 'A', 'Não se aplica'

    class TipoLeitor(models.TextChoices):
        ACADEMICA = 'A', 'Obras acadêmicas destinadas a pesquisadores, docentes e especialistas da área e áreas afins'
        GERAL = 'G', 'Obras destinadas ao público em geral'
        POS = 'P', 'Obras acadêmicas destinadas a alunos da graduação e pós-graduação'
        OUTROS = 'O', 'Outros'

    class OrigemGrupo(models.TextChoices):
        INTL = 'I', 'Originada de grupos ou redes de pesquisa internacionais'
        INST = 'T', 'Originada de grupos interinstitucionais de pesquisa'
        NACIONAL = 'N', 'Originada de outros grupos ou redes de pesquisa nacionais'
        SEMGRUPO = 'X', 'Não envolve grupos ou rede de pesquisa'
        INTERNO = 'P', 'Originada de grupos ou redes de pesquisa internas ao programa'
        OUTRO = 'O', 'Outro'

    # pesquisador "dono" do registro. Quem criou o registro
    pesquisador = models.ForeignKey(Pesquisador, on_delete=models.PROTECT)
    tipo = models.ForeignKey(TipoProducao, on_delete=models.PROTECT, verbose_name='Tipo de Produção',
                             limit_choices_to={'edicao': True})
    titulo = models.TextField('Título')
    descricao = models.TextField('Descrição Completa', blank=True, null=True)
    doi = models.CharField("DOI", max_length=200, blank=True, null=True, db_index=True)
    isbn = models.CharField("ISBN", max_length=13, blank=True, null=True, db_index=True)
    ano = models.SmallIntegerField()
    dt_publicacao = models.DateField('Dt.Publicação', blank=True, null=True)  # Mídias Impressa/Eletrônica
    volume = models.CharField(max_length=20, blank=True, null=True)
    serie = models.CharField(max_length=20, blank=True, null=True)
    periodico = models.ForeignKey(Periodico, blank=True, null=True, on_delete=models.SET_NULL,
                                  help_text='Preencha ao menos 5 caracteres ou o ISSN')

    projeto = models.ForeignKey(ProjetoPesquisa, blank=True, null=True, on_delete=models.PROTECT)
    projeto_livre = models.TextField('Projeto', blank=True, null=True)
    sem_projeto = models.BooleanField('Sem Projeto/Produção externa ao Programa', default=False)

    tipo_obra = models.CharField('Tipo da Obra', max_length=1, blank=True, null=True, choices=TipoObra.choices)
    natureza_obra = models.CharField('Natureza da obra', max_length=1, blank=True, null=True,
                                     choices=NaturezaObra.choices)
    natureza_conteudo = models.CharField('Natureza do Conteúdo', max_length=1, blank=True, null=True,
                                         choices=NaturezaConteudo.choices)
    meio = models.CharField('Meio de Divulgação', max_length=1, blank=True, null=True, choices=MeioDivulgacao.choices)
    abrangencia = models.CharField('Abrangência Territorial', max_length=1, blank=True, null=True,
                                   choices=Abrangencia.choices)
    area_impacto = models.ForeignKey(AreaImpacto, blank=True, null=True, on_delete=models.PROTECT)
    nivel_impacto = models.CharField('Nível de Impacto', max_length=1, blank=True, null=True,
                                     choices=NivelImpacto.choices)
    tipo_impacto = models.CharField('Tipo de Impacto', max_length=1, blank=True, null=True,
                                    choices=TipoImpacto.choices)
    complexidade = models.CharField('Complexidade', max_length=1, blank=True, null=True,
                                    choices=Complexidade.choices)
    setor = models.ForeignKey(SetorEconomico, blank=True, null=True, on_delete=models.SET_NULL)

    cidade = models.CharField(max_length=200, blank=True, null=True)
    pais = models.CharField(max_length=60, blank=True, null=True)
    idioma = models.CharField(max_length=30, blank=True, null=True)

    organizacao = models.TextField('Editores/Coordenação/Organização', blank=True, null=True)
    tipo_editora = models.CharField('Tipo de Editora', max_length=1, blank=True, null=True,
                                    choices=TipoEditora.choices)
    editora = models.CharField(max_length=300, blank=True, null=True)
    conselho_editorial = models.CharField('Conselho Editorial', max_length=1, blank=True, null=True,
                                          choices=ConselhoEditorial.choices)
    num_paginas = models.IntegerField('Núm.Páginas', blank=True, null=True)
    pagina_inicial = models.IntegerField('Núm.Pág.Inicial', blank=True, null=True)
    pagina_final = models.IntegerField('Núm.Pág.Final', blank=True, null=True)
    premiacao = models.CharField('Premiação', max_length=1, blank=True, null=True,
                                 choices=Premiacao.choices)
    reedicao = models.BooleanField('Reedição', default=False)
    reimpressao = models.BooleanField('Reimpressão', default=False)
    info_autores = models.BooleanField('Informação sobre autores', default=False)
    revisao_pares = models.BooleanField('Parecer/Revisão por Pares', default=False)
    indice_remissivo = models.BooleanField('Índice Remissivo', default=False)
    traducao = models.BooleanField('Tradução', default=False)
    tipo_acesso = models.CharField('Disponibilidade', max_length=1, blank=True, null=True,
                                   choices=TipoAcesso.choices)
    natureza_texto = models.ForeignKey(NaturezaTexto, verbose_name='Natureza do Texto', blank=True, null=True,
                                       on_delete=models.PROTECT)
    natureza_texto_obs = models.TextField('Observações sobre a natureza do texto', blank=True, null=True)

    leitor_preferencial = models.CharField('Leitor Preferencial', max_length=1, blank=True, null=True,
                                           choices=TipoLeitor.choices)
    leitor_preferencial_obs = models.TextField('Observações sobre o leitor preferencial', blank=True, null=True)

    origem_grupo = models.CharField('Origem da Obra', max_length=1, blank=True, null=True,
                                    choices=OrigemGrupo.choices)
    obs = models.TextField('Observação', blank=True, null=True)

    relacao_tese = models.BooleanField('Produção é relacionado à dissertação ou tese?', default=False)
    ident_unico = models.CharField('Identificador Interno', max_length=32, blank=True, null=True, db_index=True)
    validacao = models.CharField('Validação', choices=Status.choices, max_length=1, default=Status.ABERTO)
    conta_sucupira = models.BooleanField('Contabilizado no Sucupira', default=False)
    comprovante = models.FileField('Comprovante', upload_to='producao/', blank=True, null=True)
    doi_validado = models.BooleanField(default=False)
    url = models.URLField('URL', blank=True, null=True)
    titulo_colecao = models.TextField('Título do Livro/Coletânea', blank=True, null=True)
    tipo_financiamento = models.CharField('Tipo de Financiamento', max_length=1, blank=True, null=True,
                                          choices=TipoFinanciamento.choices)
    # Titulo original recebido pela fonte de dados (Lattes/DOI/ISBN)
    titulo_original = models.TextField(blank=True, null=True)
    dt_inclusao = models.DateTimeField(auto_now_add=True, null=True)

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
        if not self.titulo_original:
            self.titulo_original = self.titulo
        self.ident_unico = generate_hash(self.titulo_original)
        # MySQL: XML Lattes vem com números loucos
        if self.pagina_inicial and self.pagina_inicial >= 2 ** 31: self.pagina_inicial = None
        if self.pagina_final and self.pagina_final >= 2 ** 31: self.pagina_final = None
        if self.num_paginas and self.num_paginas >= 2 ** 31: self.num_paginas = None
        super().save(*args, **kwargs)

    def validada(self):
        """Retorna ícone do admin para True/False """
        return mark_safe(_boolean_icon(self.validacao == self.Status.VALIDADO))


class ProducaoAutor(models.Model):
    producao = models.ForeignKey(Producao, on_delete=models.CASCADE)
    autor = models.ForeignKey(Pesquisador, null=True, blank=True, on_delete=models.PROTECT)
    nome = models.CharField(max_length=130, null=True, blank=True)
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
    REVISADO = 'R'  # Professor solicitou revisão
    REGISTRADO = 'Z'  # Secretaria já registrou no Sucupira
    STATUS = (
        (NAO_INICIADO, 'Não iniciado'),
        (EM_EDICAO, 'Em edição'),
        (CADASTRO_OK, 'Cadastro Ok'),
        (RESUMO_OK, 'Resumo Ok'),
        (VALIDADO, 'Validado'),
        (REVISADO, 'Revisão solicitada'),
        (AVALIADO, 'Finalizado'),
        (REGISTRADO, 'Registrado no Sucupira')
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
    grupo_pesquisa = models.TextField(verbose_name='Participação em Núcleo de Pesquisa', null=True, blank=True)
    part_pesquisa = models.TextField(verbose_name='Participação em pesquisas coletivas coordenadas por docentes',
                                     null=True, blank=True)
    part_extensao = models.TextField(verbose_name='Participação em Atividades de Extensão', null=True, blank=True)
    part_editoria = models.TextField(verbose_name='Participação em Atividades Editoriais', null=True, blank=True)
    part_outras = models.TextField(verbose_name='Participação em outras atividades coletivas de pesquisa e/ou extensão',
                                   null=True, blank=True)
    part_discente = models.TextField(verbose_name='Participação em Instâncias de Representação Discente', null=True,
                                     blank=True)
    part_movimento = models.TextField(verbose_name='Participação em Coletivos e Movimentos da Universidade',
                                      null=True, blank=True)
    curso_anterior = models.TextField(verbose_name='Caso esteja no Doutorado, indicar PPG e área do curso de Mestrado',
                                      null=True, blank=True)
    seminarios = models.TextField(verbose_name='Seminários do Programa', null=True, blank=True)
    premios = models.TextField(verbose_name='Prêmios e distinções',
                               null=True, blank=True)
    impacto_pp = models.TextField(verbose_name='Formulação e implementação de políticas públicas',
                                  null=True, blank=True)
    impacto_gestao = models.TextField(
        verbose_name='Gestão pública e não-governamental com impactos sociais e econômicos',
        null=True, blank=True)
    impacto_educacao = models.TextField(verbose_name='Programas para educação básica',
                                        null=True, blank=True)
    impacto_projetos = models.TextField(verbose_name='Projetos de extensão ou ações de popularização',
                                        null=True, blank=True)
    impacto_empresarial = models.TextField(verbose_name='Interações com o setor empresarial, '
                                                        'em função da natureza e vocação do programa',
                                           null=True, blank=True)

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
    def _avaliacao_anual_url(hash_auth):
        s = reverse_lazy('avaliacao_anual', args=(hash_auth,))
        return s

    def get_absolute_url(self):
        return self._avaliacao_anual_url(self.hash_auth)

    def get_approval_url(self):
        return self._avaliacao_anual_url(self.hash_apr) + '?apr=1'

    def readonly(self):
        return self.status in (RelatorioAnual.AVALIADO, RelatorioAnual.REGISTRADO)

    def save(self, *args, **kwargs):
        if not self.hash_auth:
            self.hash_auth = generate_hash()
        if not self.hash_apr:
            self.hash_apr = generate_hash()

        if self.pk:
            if self.aprovado:
                if self.status != self.AVALIADO:
                    self.status = self.AVALIADO
                    log_object(self, f'Avaliado')
        super().save(*args, **kwargs)

    def send_invite(self, subject, processamento, thread=True):
        modelo = Template(processamento.template_email)
        link = '%s%s' % (settings.SITE_URL, self._avaliacao_anual_url(self.hash_auth))
        message = modelo.render(Context({'name': self.pesquisador.nome, 'link': link}))
        sendmail(subject, [self.pesquisador.email], message=message, thread=thread)
        return

    def enviar_convite_aprovacao(self):
        processamento = TipoProcessamento.objects.get(tipo=TipoProcessamento.CONVITE_PROFESSOR)
        orientador = Aluno.objects.get(id=self.pesquisador.id).orientador
        if not orientador:
            orientacao = Orientacao.objects.filter(aluno=self.pesquisador.id).order_by('pk').last()
            orientador = orientacao.orientador

        if not orientador:
            mensagem_erro = 'Aluno sem orientador: %s' % self.pesquisador.nome
            log_object(self, mensagem_erro)
            sendmail(mensagem_erro, [settings.REPLY_TO_EMAIL], message='')
            return False

        if not orientador.email:
            mensagem_erro = f'Orientador sem email: {orientador}'
            log_object(self, mensagem_erro)
            sendmail(mensagem_erro, [settings.REPLY_TO_EMAIL], message='')
            return False

        modelo = Template(processamento.template_email)
        link = '%s%s?apr=1' % (settings.SITE_URL, self._avaliacao_anual_url(self.hash_apr))
        artigo = 'o' if orientador.sexo == 'M' else 'a'

        message = modelo.render(Context({'nome': orientador.nome, 'link': link, 'artigo': artigo}))
        sendmail('Solicitação de Aprovação do Relatório Anual: %s' % self.pesquisador.nome,
                 [orientador.email], message=message)
        return True

    def enviar_convite_correcao(self):
        processamento = TipoProcessamento.objects.get(tipo=TipoProcessamento.CONVITE_CORRECAO)
        orientador = Aluno.objects.get(id=self.pesquisador.id).orientador
        if orientador:
            modelo = Template(processamento.template_email)
            link = '%s%s' % (settings.SITE_URL, self._avaliacao_anual_url(self.hash_auth))
            message = modelo.render(Context({'name': self.pesquisador.nome, 'link': link,
                                             'observacao': self.comentario_orientador}))
            sendmail('Solicitação de Correção do Relatório Anual: %s' % self.pesquisador.nome,
                     [orientador.email], message=message)
        else:
            sendmail('Aluno sem orientador: %s' % self.pesquisador.nome, [settings.REPLY_TO_EMAIL], message='')

    def enviar_mensagem_final(self):
        processamento = TipoProcessamento.objects.get(tipo=TipoProcessamento.AVISO_APROVACAO)
        orientador = Aluno.objects.get(id=self.pesquisador.id).orientador
        if orientador:
            modelo = Template(processamento.template_email)
            link = '%s%s?apr=1' % (settings.SITE_URL, self._avaliacao_anual_url(self.hash_apr))
            artigo = 'o' if orientador.sexo == 'M' else 'a'
            message = modelo.render(Context({'nome': orientador.nome, 'link': link, 'artigo': artigo}))
            sendmail('Solicitação de Aprovação do Relatório Anual: %s' % self.pesquisador.nome,
                     [orientador.email], message=message)
        else:
            sendmail('Aluno sem orientador: %s' % self.pesquisador.nome, [settings.REPLY_TO_EMAIL], message='')

    @property
    def resumo_ok(self):
        return self.status == RelatorioAnual.RESUMO_OK

    @property
    def desenvolvimento_total(self):
        """Retorna o total de palavras no campo desenvolvimento"""
        return len((self.desenvolvimento or '').split())
