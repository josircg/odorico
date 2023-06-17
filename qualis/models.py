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
    ('NC', 'NC',),
)

MODELO_ECONOMICO = (
    ('D', 'Diamond'),
    ('A', 'APC'),
    ('T', 'Trancado'),
    ('P', 'Predatório'),
)


class GrandeArea(models.Model):
    nome = models.CharField('Nome', max_length=100)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Grande Área'
        verbose_name_plural = 'Grandes Áreas'
        ordering = ('nome', )


# deprecated - vai ser substituida por Schema/Assunto
class Area(models.Model):
    nome = models.CharField('Nome', max_length=100)
    cod_capes = models.CharField('Cód.Capes', max_length=40)
    grande_area = models.ForeignKey(GrandeArea, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Área de Avaliação'
        verbose_name_plural = 'Áreas de Avaliação'


class AreaConhecimento(models.Model):
    nome = models.CharField('Nome', max_length=100)
    cod_capes = models.CharField('Cód.Capes', max_length=40, blank=True, null=True)
    area_avaliacao = models.ForeignKey(Area, on_delete=models.PROTECT)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Área de Conhecimento'
        verbose_name_plural = 'Áreas de Conhecimento'


class Schema(models.Model):
    descricao = models.CharField('Descrição', max_length=100)
    sigla = models.CharField('Sigla', max_length=10, null=True, blank=True)
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
    descricao = models.CharField('Descrição', max_length=100)
    schema = models.ForeignKey(Schema, on_delete=models.PROTECT)
    parent = models.ForeignKey('Assunto', blank=True, null=True, on_delete=models.PROTECT)
    cod_externo = models.CharField('Cód.Externo', max_length=20, blank=True, null=True)

    class Meta:
        verbose_name = 'Classificação'
        verbose_name_plural = 'Classificação'

    def __str__(self):
        return self.descricao

    def tot_periodicos(self):
        return self.periodicoassunto_set.count()
    tot_periodicos.short_description = 'Periódicos'


# revista
class Periodico(models.Model):
    nome = models.CharField('Nome completo', max_length=400)
    issn = models.CharField('ISSN-L', max_length=9, unique=True)
    eissn = models.CharField('Alt.ISSN', max_length=9, db_index=True, blank=True, null=True)
    url = models.URLField('URL', blank=True, null=True)
    status = models.CharField(max_length=1, default='A', choices=STATUS_ATIVIDADE)
    modelo_economico = models.CharField('Modelo Econômico', max_length=1, choices=MODELO_ECONOMICO,
                                        null=True, blank=True)
    qualis = models.CharField(max_length=2, default='ND', choices=EXTRATO_QUALIS)
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
    google_h5 = models.DecimalField('Google H5', max_digits=10, decimal_places=2, blank=True, null=True)
    google_h5m = models.DecimalField('Google H5M', max_digits=10, decimal_places=2, blank=True, null=True)
    citescore = models.DecimalField('Citescore', max_digits=10, decimal_places=3, blank=True, null=True)
    sjr = models.DecimalField('SJR', max_digits=10, decimal_places=5, blank=True, null=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Periódico'


class PeriodicoISSN(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.PROTECT)
    issn = models.CharField('ISSN', max_length=9, db_index=True)
    meio = models.CharField(max_length=1, choices=(('L', 'Link'),
                                                   ('P', 'Impresso'),
                                                   ('E', 'Eletrônico'),
                                                   ('O', 'Outros')), default='O')

    class Meta:
        verbose_name = 'ISSN Index'

    def __str__(self):
        return self.issn


class PeriodicoIndicador(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.PROTECT)
    schema = models.ForeignKey(Schema, on_delete=models.PROTECT)
    area = ChainedForeignKey(Assunto, chained_field='schema', chained_model_field='schema', sort=True, null=True)
    classe = models.CharField(max_length=2,null=True, blank=True)
    indicador = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)


class PeriodicoAssunto(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.PROTECT)
    assunto = models.ForeignKey(Assunto, on_delete=models.PROTECT)


# Deprecated
class PeriodicoArea(models.Model):
    periodico = models.ForeignKey(Periodico, on_delete=models.PROTECT)
    area = models.ForeignKey(AreaConhecimento, on_delete=models.PROTECT)
    qualis = models.CharField(max_length=2, default='ND')
