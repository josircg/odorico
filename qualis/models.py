from django.db import models
from smart_selects.db_fields import ChainedForeignKey

STATUS_ATIVIDADE = (
    ('A', 'Ativa'),
    ('F', 'Inativa'),
)

EXTRATO_QUALIS = (
    ('A1', 'A1',),
    ('A2', 'A2',),
    ('A3', 'A3',),
    ('A4', 'A4',),
    ('B1', 'B1',),
    ('B2', 'B2',),
    ('B3', 'B3',),
    ('B4', 'B4',),
    ('C',  'C',),
    ('ND', 'ND',),
)

MODELO_ECONOMICO = (
    ('U', 'Unkown'),
    ('D', 'Diamond'),
    ('A', 'APC'),
    ('T', 'Trancado'),
    ('P', 'Predatório'),
)


# Utilizada para a classificação interna do ODORICO para a visualização das coleções de Comunicação e CI
# deprecated - vai ser substituida por Schema/Assunto
class AreaConhecimento(models.Model):
    nome = models.CharField('Nome', max_length=100)

    def __str__(self):
        return self.nome

    @property
    def tot_periodicos(self):
        return self.periodico_set.count()

    class Meta:
        verbose_name = 'Área de Conhecimento'
        verbose_name_plural = 'Áreas de Conhecimento'
        ordering = ('nome',)


class Schema(models.Model):
    descricao = models.CharField('Descrição', max_length=100)
    sigla = models.CharField('Sigla', max_length=10, null=True, blank=True)
    nota = models.TextField('Nota sobre a Classificação', null=True, blank=True)
    ano_inicial = models.SmallIntegerField('Ano Inicial', null=True, blank=True)
    ano_final = models.SmallIntegerField('Ano Final', null=True, blank=True)

    class Meta:
        verbose_name = 'Esquema de Classificação'
        verbose_name_plural = 'Esquemas de Classificação'

    def __str__(self):
        if self.ano_inicial:
            return '%s (%s)' % (self.descricao, self.ano_inicial)
        else:
            return self.descricao

    @property
    def tot_classes(self):
        return self.assunto_set.count()


class Assunto(models.Model):
    descricao = models.CharField('Descrição', max_length=400)
    schema = models.ForeignKey(Schema, on_delete=models.PROTECT)
    parent = models.ForeignKey('Assunto', blank=True, null=True, on_delete=models.PROTECT)
    cod_externo = models.CharField('Cód.Externo', max_length=20, blank=True, null=True)

    class Meta:
        verbose_name = 'Classificação'
        verbose_name_plural = 'Classificação'

    def __str__(self):
        return self.descricao

    def tot_periodicos(self):
        return PeriodicoAssunto.objects.filter(assunto=self).count()
    tot_periodicos.short_description = 'Periódicos'


# revista
class Periodico(models.Model):
    class Status(models.TextChoices):
        ATIVA = 'A', 'Ativa'
        INATIVA = 'F', 'Inativa'
        AEXCLUIR = 'D', 'Para exclusão' # Status temporário para permitir a exportação de registros entre bases

    nome = models.CharField('Nome completo', max_length=400)
    issn = models.CharField('ISSN-L', max_length=9, unique=True)
    eissn = models.CharField('Alt.ISSN', max_length=9, db_index=True, blank=True, null=True)
    url = models.URLField('URL', max_length=400, blank=True, null=True)
    status = models.CharField(max_length=1, default='A', choices=Status.choices)
    modelo_economico = models.CharField('Modelo Econômico', max_length=1, choices=MODELO_ECONOMICO,
                                        null=True, blank=True, default='U')
    qualis = models.CharField(max_length=2, default='ND', choices=EXTRATO_QUALIS)
    qualis_ant = models.CharField(max_length=2, default='ND', choices=EXTRATO_QUALIS)
    pais = models.CharField(max_length=30, blank=True, null=True)
    area = models.ForeignKey(AreaConhecimento, blank=True, null=True, on_delete=models.PROTECT)
    sistema = models.CharField(max_length=10, blank=True, null=True,
                               help_text='Sistema de Gerenciamento do Períodico')
    frequencia = models.CharField(max_length=100, blank=True, null=True)
    historico = models.CharField(max_length=100, blank=True, null=True)
    referencia = models.CharField('Nome de Referência', max_length=100, blank=True, null=True,
                                  help_text='Como o nome aparece nas referências bibliográficas')
    editora = models.CharField(max_length=200, blank=True, null=True)
    dtvalidacao = models.DateField(null=True, blank=True)
    google_code = models.CharField(max_length=20, blank=True, null=True)
    scopus_code = models.CharField(max_length=20, blank=True, null=True)
    doaj_code = models.CharField(max_length=32, blank=True, null=True)
    oalex_code = models.CharField(max_length=12, blank=True, null=True)
    google_h5 = models.DecimalField('Google H5', max_digits=10, decimal_places=2, blank=True, null=True)
    google_h5m = models.DecimalField('Google H5M', max_digits=10, decimal_places=2, blank=True, null=True)
    oalex_h5 = models.DecimalField('OpenAlex H5', max_digits=10, decimal_places=2, blank=True, null=True)
    citescore = models.DecimalField('Citescore', max_digits=10, decimal_places=3, blank=True, null=True)
    sjr = models.DecimalField('SJR', max_digits=10, decimal_places=5, blank=True, null=True)
    keywords = models.TextField(blank=True, null=True)
    dtupdate = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Periódico'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # não pode colocar get_or_create pois pode haver mais de um registro
        dset = PeriodicoISSN.objects.filter(periodico=self, issn=self.issn)
        if dset.count() == 0:
            PeriodicoISSN.objects.create(periodico=self, issn=self.issn)
        if self.eissn:
            dset = PeriodicoISSN.objects.filter(periodico=self, issn=self.eissn)
            if dset.count() == 0:
                PeriodicoISSN.objects.create(periodico=self, issn=self.eissn, meio='E')

    def qualis_evolucao(self):
        matriz_equivalencia = {'A1':8,'A2':7,'A3':6,'A4':5,'B1':4,'B2':3,'B3':2,'B4':1}
        evolucao = []
        for qualis in self.periodicoindicador_set.filter(
                schema__sigla__startswith='QUALIS',
                periodico=self).values('schema__ano_inicial',
                                       'classe').distinct().order_by('schema__ano_inicial'):
            classe = matriz_equivalencia.get(qualis['classe'],0)
            if classe:
                evolucao.append({ qualis['schema__ano_inicial']: classe })
        return evolucao

class PeriodicoISSN(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.CASCADE)
    issn = models.CharField('ISSN', max_length=9, db_index=True)
    meio = models.CharField(max_length=1, choices=(('L', 'Link'),
                                                   ('P', 'Impresso'),
                                                   ('E', 'Eletrônico'),
                                                   ('O', 'Outros')), default='O')
    valido = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'ISSN Index'

    def __str__(self):
        return self.issn


# Permite registrar o histórico de indicadores ou classes de um determinado periódico
class PeriodicoIndicador(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.CASCADE)
    schema = models.ForeignKey(Schema, on_delete=models.PROTECT)
    area = ChainedForeignKey(Assunto, chained_field='schema', chained_model_field='schema',
                             sort=True, null=True, blank=True)
    classe = models.CharField(max_length=2,null=True, blank=True)
    indicador = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)


class PeriodicoAssunto(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.CASCADE)
    schema = models.ForeignKey(Schema, on_delete=models.PROTECT, null=True)
    assunto = ChainedForeignKey(Assunto, chained_field='schema', chained_model_field='schema',
                                sort=True, on_delete=models.PROTECT)
    ordem = models.SmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Classificação do Periódico'


class Pais(models.Model):
    iso3 = models.CharField(max_length=3, unique=True)
    iso2 = models.CharField(max_length=2, unique=True)
    nome = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    nombre = models.CharField(max_length=100)
    tld = models.CharField(max_length=3, blank=True, null=True) # Top Level Domains
    phone_code = models.CharField(max_length=4, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)

    class Meta:
        verbose_name = 'País'
        verbose_name_plural = 'Países'

    def __str__(self):
        return self.nome
