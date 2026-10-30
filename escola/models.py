import hashlib
import os
import threading
from datetime import datetime

from utils.stdlib import EMPTY_VALUES

import requests
from ckeditor.fields import RichTextField
from django.conf import settings
from django.db import models
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from nucleo.apps import log_object
from nucleo.models import GENDER, STATUS_ATIVO, STATUS_ATIVIDADE_M, Pesquisador, Instituicao, PesquisadorInstituicao
from utils.apps import pdf_to_png
from utils.email import sendmail
from utils.fields import BRCPFField
from utils.text import extrai_texto_de_html

from .managers import ModuloTrilhaQuerySet, ModuloSessaoQuerySet, ListaContatoQuerySet


FORMACAO_CHOICES = (
    ('X', 'Ensino Básico em andamento'),
    ('0', 'Ensino Básico'),
    ('1', 'Graduação em andamento'),
    ('2', 'Graduação'),
    ('3', 'Mestrado em andamento'),
    ('4', 'Mestrado'),
    ('5', 'Doutorado em andamento'),
    ('6', 'Doutorado'),
)

# Como você ficou sabendo deste curso?
ORIGEM_OPTIONS = [
    'Redes Sociais',
    'Indicação de professores',
    'Indicação de amigos',
    'Canais de alunos ou ex-alunos',
]


# Evento que contém um conjunto de Cursos ou Trilhas (Mesas, GT, Sessões)
class Modulo(models.Model):
    nome = models.CharField('Nome', max_length=60)
    descricao = RichTextField('Descrição')
    dt_inicio = models.DateField('Dt.Início')
    imagem = models.ImageField('Imagem (768x768)', upload_to='images/', null=True, blank=True)
    imagem2 = models.ImageField('Banner', upload_to='images/', null=True, blank=True)
    imagem3 = models.ImageField('Imagem interna', upload_to='images/', null=True, blank=True)
    modelo = models.ForeignKey('ModeloCertificado', on_delete=models.PROTECT, null=True, blank=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True, null=True)
    # se houver url_pagina então deve-se buscar
    url_tema = models.URLField('URL Tema', max_length=300, blank=True, null=True)

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'

    def __str__(self):
        return f'{self.nome}'

    def descricao_limpa(self):
        return strip_tags(self.descricao).encode('')

    def url(self):
        if self.slug:
            if self.url_tema:
                return f'/evento/{self.slug}'
            else:
                return f'/modulo/{self.slug}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.slug:
            tipo = TipoCurso.objects.get(descricao='Evento')
            curso, _ = Curso.objects.get_or_create(modulo=self, slug=self.slug,
                                                   defaults={'tipo': tipo, 'nome': self.nome,
                                                             'dt_inicio': self.dt_inicio})
            curso.save()


class ModuloTrilha(models.Model):
    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE)
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, null=True)

    objects = ModuloTrilhaQuerySet.as_manager()

    class Meta:
        verbose_name = 'Trilha'
        verbose_name_plural = 'Trilhas do Evento'

    def __str__(self):
        return self.nome


class ModuloSessao(models.Model):
    trilha = models.ForeignKey(ModuloTrilha, on_delete=models.CASCADE)
    dia = models.DateField()
    titulo = models.CharField(max_length=150, blank=True, null=True)
    sessao = models.TextField()
    hora_inicial = models.TimeField()
    hora_final = models.TimeField(blank=True, null=True)
    trabalhos = models.TextField(blank=True, null=True)
    busca = models.TextField(blank=True, null=True)

    objects = ModuloSessaoQuerySet.as_manager()

    def __str__(self):
        return f'{self.titulo}'

    def save(self, *args, **kwargs):
        self.busca = extrai_texto_de_html(self.trabalhos) + ' ' + extrai_texto_de_html(self.sessao)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Sessão'
        verbose_name_plural = 'Sessões'
        ordering = ('trilha__nome', 'dia', 'hora_inicial',)


class ContatoAgenda(models.Model):
    cookie = models.CharField(max_length=64)
    contato = models.ForeignKey('Contato', on_delete=models.CASCADE, null=True, blank=True)
    sessao = models.ForeignKey(ModuloSessao, on_delete=models.CASCADE)

    def __str__(self):
        return self.cookie

    class Meta:
        unique_together = ('cookie', 'sessao')


class TipoCurso(models.Model):
    descricao = models.CharField('Descrição', max_length=60)
    # listado apenas como evento (aparece apenas na listagem de eventos)
    evento = models.BooleanField('Evento', default=False, help_text='Aparece apenas na listagem de eventos')
    # cursos privados não aparecem na listagem dos cursos oferecidos para o público
    publico = models.BooleanField('Público', default=True,
                                  help_text='Se desmarcada, não aparece na listagem de cursos e eventos')
    # meta-cursos são os criados para alocar GTs ou mesas para eventos
    meta = models.BooleanField('Meta', default=False, help_text='Cursos, Mesas e GTs internos de um evento')

    def __str__(self):
        return f'{self.descricao}'

    class Meta:
        verbose_name = 'Tipo de Curso/Evento'
        verbose_name_plural = 'Tipos de Curso/Evento'


class PalavraChave(models.Model):
    termo = models.CharField('Termo', max_length=80)
    contador = models.IntegerField(default=0)

    def __str__(self):
        return f'{self.termo}'


class ModeloCertificado(models.Model):
    descricao = models.CharField(max_length=200)
    font_name = models.CharField(max_length=100, default="DejaVuSans.ttf")
    font_size = models.IntegerField(default=32)
    color = models.CharField(max_length=20, default='rgb(0,0,0)')
    linha = models.IntegerField('Linha do Nome', default=440)
    status = models.CharField(max_length=1, choices=STATUS_ATIVIDADE_M, default=STATUS_ATIVO)
    reply_to = models.CharField(max_length=100, null=True, blank=True,
                                help_text=mark_safe("No formato 'Nome &lt;email@domain.com&gt;'"))

    class Meta:
        verbose_name = 'Modelo do Certificado'
        verbose_name_plural = 'Modelos de Certificados'

    def __str__(self):
        return f'{self.descricao}'


class Curso(models.Model):
    class Status(models.TextChoices):
        EM_EDICAO = 'E', 'Em elaboração'  # Não aparece para inscrições
        ATIVO = 'A', 'Matrículas abertas'  # Inscrições abertas
        FINALIZADO = 'F', 'Finalizado'  # Curso Finalizado
        CANCELADO = 'C', 'Cancelado'  # Curso cancelado

    nome = models.CharField(max_length=200)
    tipo = models.ForeignKey(TipoCurso, on_delete=models.PROTECT)
    modulo = models.ForeignKey(Modulo, on_delete=models.PROTECT, null=True, blank=True)
    online = models.BooleanField('Online', default=False)
    cod_externo = models.CharField(
        'Código/Numeração', max_length=10, null=True, blank=True)
    ementa = RichTextField('Descrição/Ementa', null=True, blank=True)
    programacao = RichTextField('Programação/Local', null=True, blank=True)
    espelho_pdf = models.FileField('Espelho em PDF', upload_to='arquivos/', null=True, blank=True,
                                   help_text='Programação ou Arquivo')
    imagem = models.ImageField(
        'Imagem (768x768)', upload_to='images/', null=True, blank=True)
    banner = models.ImageField('Banner (1440x558)', upload_to='images/', null=True, blank=True)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.EM_EDICAO)
    dt_inicio = models.DateField('Dt.Início')
    dt_matricula = models.DateField('Matrícula iniciando em', null=True, blank=True)
    dt_fim_matricula = models.DateTimeField('Matrículas até', null=True, blank=True)
    duracao = models.DecimalField('Duração (Horas)', max_digits=6, decimal_places=1, null=True, blank=True)
    num_aulas = models.IntegerField('Número de Aulas', default=1)
    num_max_alunos = models.IntegerField('Número Máximo de Alunos', default=0)
    dt_limite_presenca = models.DateTimeField('Presença até', null=True, blank=True)
    slug = models.SlugField('URL Externa', null=True, blank=True)
    tema = models.FileField('Tema', upload_to='curso', null=True, blank=True)  # vai morrer
    certificado = models.FileField('Certificado', upload_to='modelo_certificado/', null=True, blank=True)
    modelo = models.ForeignKey(ModeloCertificado, on_delete=models.PROTECT, null=True, blank=True)
    docentes = models.ManyToManyField('Docente', related_name='docentes', through='CursoDocente')
    envio_certificado = models.CharField('Certificado Enviado', max_length=1,
                                         choices=(('N', 'Não enviado'),
                                                  ('A', 'Agendado'),
                                                  ('E', 'Enviado')), default='N')
    moodle_id = models.IntegerField('Moodle ID', null=True, blank=True)

    class Meta:
        verbose_name = 'Evento/Agenda'
        verbose_name_plural = 'Eventos e Agendas'

    def __str__(self):
        if self.modulo:
            return f'{self.modulo}/{self.nome}'
        else:
            return f'{self.nome}'

    # Retorna o detalhamento do status das inscrições
    def status_matricula(self):
        hoje = datetime.today()
        if self.status == self.Status.ATIVO and self.dt_matricula:
            if self.dt_matricula > hoje.date():
                return 'Matrículas iniciando em ' + self.dt_matricula.strftime('%d/%m')
            else:
                if self.dt_fim_matricula and self.dt_fim_matricula < hoje:
                    return 'Matrículas encerradas'
                else:
                    if self.tot_alunos() >= self.num_max_alunos:
                        return 'Todas as vagas foram preenchidas'
                    else:
                        return None
        else:
            return 'Matrículas encerradas'

    def imagem_url(self):
        if self.imagem:
            url = settings.SITE_URL + self.imagem.url
        elif self.modulo and self.modulo.imagem:
            url = settings.SITE_URL + self.modulo.imagem.url
        else:
            url = f'{settings.SITE_URL}/static/escola/img/default.png'
        return url

    def banner_url(self):
        if self.banner:
            return settings.SITE_URL + self.banner.url
        elif self.modulo and self.modulo.imagem2:
            return settings.SITE_URL + self.modulo.imagem2.url
        else:
            return f'{settings.SITE_URL}/static/escola/img/banner.png'

    def external_url(self):
        if self.slug:
            return f'{settings.SITE_URL}/evento/{self.slug}'
        else:
            return f'{settings.SITE_URL}/curso/{self.id}'

    @property
    def header(self):
        return 'Ementa' if self.tipo.__str__().startswith('Curso') else ''

    @property
    def tipo_docente(self):
        return 'Docentes' if self.tipo.__str__().startswith('Curso') else 'Palestrantes'

    def edit_link(self):
        return mark_safe(f'<a href="/admin/escola/curso/{self.id}">Edição</a>')

    edit_link.short_description = 'Edição'

    @property
    def periodo(self):
        hoje = datetime.now()
        if self.num_aulas > 0:
            if self.dt_fim_matricula and self.dt_fim_matricula > hoje:
                s = f'Ministrado em {self.dt_inicio:%d/%m/%Y}'
            else:
                s = f'Início em {self.dt_inicio:%d/%m}'
        else:
            s = ''
        return s

    def lista_docentes(self):
        lista = []
        for item in self.cursodocente_set.select_related('docente').all().order_by('ordem', 'id'):
            lista.append(item.docente.nome.title())
        return ','.join(lista)[:100]

    def categorias(self):
        result = []
        if self.online:
            result.append('Online')
        if self.modulo:
            result.append(self.modulo.nome)
        return result

    def tot_alunos(self):
        return self.inscricao_set.filter(status=Inscricao.Status.ATIVA).count()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.certificado:
            filename = self.certificado.path
            _, extension = os.path.splitext(filename)
            if extension == '.pdf':
                t = threading.Thread(target=pdf_to_png, args=[filename, self], daemon=True)
                t.start()

    def hash_confirmacao(self):
        base = str(self.id) + '#' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'


class CursoFormalManager(models.Manager):
    def get_queryset(self):
        return super(CursoFormalManager, self).get_queryset().filter(tipo__meta=False, tipo__evento=False)


class CursoFormal(Curso):
    objects = CursoFormalManager()

    class Meta:
        proxy = True
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'


class DocenteManager(models.Manager):
    def get_queryset(self):
        return super(DocenteManager, self).get_queryset().filter(pesquisadorinstituicao__instituicao_id=settings.ESCOLA)


class Docente(Pesquisador):
    objects = DocenteManager()

    def save(self, *args, **kwargs):
        self.professor = True
        super().save(*args, **kwargs)
        # PesquisadorInstituicao.objects.get_or_create(instituicao_id=settings.ESCOLA, pesquisador=self,
        #                                             defaults={'status': STATUS_ATIVO})

    class Meta:
        proxy = True
        verbose_name = 'Docente'
        verbose_name_plural = 'Docentes'

    def __str__(self):
        return f'{self.nome}'

    def num_cursos(self):
        return self.cursodocente_set.all().count()


class CursoDocente(models.Model):
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT)
    docente = models.ForeignKey(Docente, on_delete=models.PROTECT)
    ordem = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f'{self.curso} - {self.docente}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.docente.email and self.curso.tipo.meta:
            contato, _ = Contato.objects.get_or_create(email=self.docente.email,
                                                       defaults={'nome': self.docente.nome,
                                                                 'origem': 'Docente',
                                                                 'curso_origem': self.curso})
            contato.save()
            inscricao, _ = Inscricao.objects.get_or_create(curso=self.curso, contato=self.docente,
                                                           defaults={'status': Inscricao.Status.ATIVA})
            inscricao.save()


# Discente ocasional dos Cursos Livres ou Eventos
class Discente(models.Model):
    nome = models.CharField('Nome', max_length=120, db_index=True)
    email = models.EmailField('E-mail principal', max_length=191, null=True, unique=True, db_index=True)
    sexo = models.CharField(max_length=1, choices=GENDER, null=True, blank=True)
    cpf = BRCPFField(verbose_name='CPF', blank=True, null=True, db_index=True, unique=True)
    cep = models.CharField('CEP', max_length=8, blank=True, null=True)
    localidade = models.CharField('Localidade', max_length=100, blank=True, null=True)
    UF = models.CharField(max_length=2, blank=True, null=True)
    telefone = models.CharField(max_length=11, blank=True, null=True)
    formacao = models.CharField(max_length=1, blank=True, null=True, choices=FORMACAO_CHOICES)
    id_cnpq = models.CharField(
        'ID CNPQ', max_length=16, blank=True, null=True, unique=True)
    orcid = models.CharField('ORCID', max_length=20, blank=True, null=True, db_index=True, unique=True)
    validado = models.BooleanField('Validado', default=False)
    contato = models.ForeignKey('Contato', on_delete=models.PROTECT, blank=True, null=True)
    instituicao = models.CharField('Vínculo Institucional', max_length=100, blank=True, null=True,
                                   help_text='Nome da instituição onde você trabalha ou estuda')
    moodle_id = models.IntegerField('Moodle ID', null=True, blank=True)

    def __str__(self):
        if self.nome:
            return f'{self.nome}'
        else:
            if self.email:
                return f'{self.email}'
            else:
                return f'{self.id}'

    def save(self, *args, **kwargs):
        if self.telefone:
            self.telefone = self.telefone.replace('(', '').replace(')', '').replace('-', '')
        if self.cep:
            self.cep = self.cep.replace('-', '')
        if not self.UF and self.cep:
            try:
                response = requests.get(f'https://viacep.com.br/ws/{self.cep}/json/')
                record = response.json()
                self.UF = record['uf']
                self.localidade = record['localidade']
            except Exception as e:
                if self.id:
                    log_object(self, f"Erro CEP: {e}")
        # Força None para evitar gravar com vazio e causar IntegrityError
        if self.orcid is not None and self.orcid.strip() in EMPTY_VALUES:
            self.orcid = None

        super().save(*args, **kwargs)

    '''
    def hash_key(self):
        base = str(self.id) + '#' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'
    '''


class Contato(models.Model):
    nome = models.CharField('Nome', max_length=120, db_index=True, null=True)
    email = models.EmailField('E-mail', max_length=191, db_index=True, null=True)
    dtcontato = models.DateTimeField('Data de Contato', auto_now_add=True)
    origem = models.CharField(max_length=100, blank=True, null=True)
    utm_source = models.CharField(max_length=60, blank=True, null=True)
    curso_origem = models.ForeignKey(Curso, blank=True, null=True, on_delete=models.SET_NULL)
    email_invalido = models.BooleanField('Email inválido', default=False)
    moodle_id = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f'{self.nome}' if self.nome else f'{self.email}' if self.email else f'ID {self.id}'

    def hash_key(self):
        base = str(self.id) + '#' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'


class Inscricao(models.Model):
    class Status(models.TextChoices):
        # Inscrição realizada, mas o discente não confirmou
        ABERTO = 'N', 'Não confirmada'
        ATIVA = 'A', 'Ativa'  # Inscrição Ativa
        LISTA_ESPERA = 'L', 'Lista de Espera'  # Entrou em lista de Espera
        CANCELADA = 'C', 'Cancelada'  # Aluno cancelou a inscrição

    curso = models.ForeignKey(Curso, on_delete=models.PROTECT)
    discente = models.ForeignKey(Discente, on_delete=models.PROTECT)
    dt_inscricao = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.ABERTO)
    presenca = models.BooleanField(default=False)
    hash_certificado = models.CharField(max_length=32, null=True, blank=True)
    inscrito_curso_moodle = models.BooleanField('Inscrito no Moodle', default=False,
                                                help_text='Indica que a inscrição do discente neste curso na '
                                                          'plataforma Moodle ocorreu com sucesso')

    def __str__(self):
        return f'{self.curso}'

    # confirmação da inscrição
    def hash_confirmacao(self):
        base = str(self.id) + '#' + settings.SECRET_KEY
        hash_string = hashlib.sha1(base.encode()).hexdigest()
        return f'{self.id}-{hash_string}'

    # envia email para verificar a identidade do contato
    def send_email_verificacao(self):
        link = f'{settings.SITE_URL}/confirma_inscricao/{self.hash_confirmacao()}'
        sendmail(subject=f"Confirme sua inscrição! {self.curso.tipo.descricao} {self.curso.nome}",
                 dest_list=[self.discente.email],
                 message=f'<html><body><p><a href="{link}">Clique aqui</a>'
                         f' para confirmar o seu cadastro e continuar a sua inscrição</p><br/><b>IMPORTANTE</b>:<br/><ul>'
                         f' <li>Esse link não deve ser repassado para outras pessoas. Ele é único para a sua conta</li>'
                         f' <li>Você só estará inscrito se confirmar através deste link</li></ul></body></html>')

    # envia email confirmando que a inscrição foi realizada
    def email_confirmacao(self):
        url = self.curso.external_url()
        sendmail(subject=f"Inscrição confirmada! {self.curso.nome}",
                 dest_list=[self.discente.email],
                 message=f'<html><body><br/>Veja a programação <a href="{url}">neste link</a><br/></body></html>')

    @classmethod
    def inscrever(cls, curso, discente, validado=False):
        mensagem_erro = ''
        inscricao = cls.objects.filter(curso=curso, discente=discente).first()
        if inscricao:
            if inscricao.status == cls.Status.ABERTO:
                mensagem_erro = ("Já existe uma inscrição em aberto para este email. "
                                 "Verifique a sua caixa postal para confirmar a sua inscrição")
                inscricao.send_email_verificacao()
            elif inscricao.status == cls.Status.ATIVA:
                mensagem_erro = "Inscrição já confirmada!"
            elif inscricao.status == cls.Status.LISTA_ESPERA:
                mensagem_erro = "Você ainda está em lista de espera"
            else:
                inscricao.status = cls.Status.ATIVA
                inscricao.save()

        else:
            if curso.tot_alunos() < curso.num_max_alunos or curso.num_max_alunos == 0:
                status = cls.Status.ATIVA if validado else cls.Status.ABERTO
                inscricao = cls(curso=curso, discente=discente, status=status)
                inscricao.save()
            else:
                inscricao = cls(curso=curso, discente=discente, status=cls.Status.LISTA_ESPERA)
                inscricao.save()
                mensagem_erro = (
                    "Infelizmente não há mais vagas para este curso/trilha. Incluímos seu nome em uma lista "
                    "de espera e caso haja alguma desistência, iremos notificá-la(o).")
        return inscricao, mensagem_erro

    class Meta:
        verbose_name = 'Inscrição'
        verbose_name_plural = 'Inscrições'


class ListaInteresse(models.Model):
    titulo = models.CharField(max_length=200)
    descricao = models.TextField('Descrição/Origem da Lista', null=True, blank=True)
    modelo = models.ForeignKey(ModeloCertificado,
                               on_delete=models.PROTECT, null=True, blank=True)
    arquivo = models.FileField('Imagem do Certificado',
                               upload_to='modelo_certificado/', null=True, blank=True)
    status_envio = models.CharField('Status de Envio', max_length=1,
                                    choices=(('N', 'Não enviado'),
                                             ('A', 'Agendado'),
                                             ('E', 'Enviado')), default='N')

    def __str__(self):
        return f'{self.titulo}'

    class Meta:
        verbose_name = 'Lista'
        verbose_name_plural = 'Listas Especiais'


class ListaContato(models.Model):
    lista = models.ForeignKey(ListaInteresse, on_delete=models.CASCADE)
    contato = models.ForeignKey(Contato, on_delete=models.CASCADE)

    objects = ListaContatoQuerySet.as_manager()

    def __str__(self):
        return f'{self.contato}'

    class Meta:
        verbose_name = 'Contato'
        verbose_name_plural = 'Contatos em Listas Especiais'


class Comunicado(models.Model):
    tipo = models.CharField(max_length=1, choices=(('A', 'Toda base'), ('M', 'Módulo'),
                                                   ('C', 'Curso'), ('L', 'Lista'), ('T', 'Teste')))
    modulo = models.ForeignKey(Modulo, on_delete=models.SET_NULL, null=True, blank=True)
    curso = models.ForeignKey(Curso, on_delete=models.PROTECT, null=True, blank=True)
    lista = models.ForeignKey(ListaInteresse, on_delete=models.SET_NULL, null=True, blank=True)
    titulo = models.CharField(max_length=200)
    texto = RichTextField()
    email_teste = models.EmailField('Email de Teste', max_length=100, null=True, blank=True)
    dt_criacao = models.DateTimeField('Dt.Criação', auto_now_add=True)
    status = models.CharField(max_length=1, choices=(('A', 'Em elaboração'),
                                                     ('P', 'Em processamento'),
                                                     ('E', 'Erro no envio'),
                                                     ('F', 'Envio Finalizado')), default='A')
    cont_erro = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f'{self.titulo}'
