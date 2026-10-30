import json

from django import forms
from django.contrib import admin
from django.contrib.admin import widgets
from django.contrib.contenttypes.admin import GenericTabularInline
from django.contrib.contenttypes.models import ContentType
from django.core.validators import EMPTY_VALUES
from django.http import HttpResponse
from django.urls import path, resolve
from django_select2 import forms as s2forms
from poweradmin.admin import PowerButton, PowerModelAdmin, PowerStackedInline, PowerTabularInline

from nucleo.actions import merge_instituicoes, merge_pesquisadores
from nucleo.apps import URL_CNPQ, obtem_dt_cnpq
from nucleo.forms import (AlunoForm, MatriculaEventoAtaForm, MatriculaEventoAtaInlineFormSet, OrientacaoAdminForm,
                          PesquisadorForm, PesquisadorProgramaForm, ProfessorLinhaForm, ProjetoPesquisaForm)
from nucleo.models import *
from nucleo.models import Matricula
from nucleo.relatorios import view_resumo_qualis
from utils.admin_mixins import WidgetCustomAdminMixin


class InstituicaoInline(PowerTabularInline):
    model = PesquisadorInstituicao
    autocomplete_fields = ('pesquisador',)
    fields = ('pesquisador', 'status')
    extra = 0


class InstituicaoAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    list_display = ('nome', 'sigla', 'pais')
    list_filter = ('pais',)
    search_fields = ('nome',)
    inlines = (InstituicaoInline,)
    autocomplete_fields = ('pais',)
    actions = ('merge',)
    field_styles = {
        'nome': 'width: 40em;',
        'sigla': 'width: 10em;',
    }

    def merge(self, request, queryset):
        if queryset.count() < 2:
            result = merge_instituicoes(queryset)
            if result > 0:
                messages.info(request, f'{result} instituições foram consolidadas')
        else:
            messages.warning(request, 'Escolha ao menos 2 instituições')


class LinhaPesquisaInline(PowerTabularInline):
    model = LinhaPesquisa
    fields = ('descricao',)
    extra = 0


class LinhaProfessorInline(PowerTabularInline):
    model = ProfessorLinha
    fields = ('linha', 'permanente', 'dtentrada', 'dtsaida',)
    extra = 0
    form = ProfessorLinhaForm


class CursoInline(admin.TabularInline):
    model = Curso
    fields = ('descricao', 'tipo_curso')
    extra = 0


class PesquisadorProgramaInline(PowerTabularInline):
    model = PesquisadorPrograma
    fields = ('pesquisador', 'vinculo')
    readonly_fields = ('pesquisador', 'vinculo')
    ordering = ('pesquisador',)
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Programa)
class ProgramaAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    list_filter = ('instituicao',)
    search_fields = ('descricao',)
    list_display = ('instituicao', 'descricao',
                    'num_pesquisadores', 'num_alunos', 'num_artigos')
    inlines = (LinhaPesquisaInline, CursoInline, PesquisadorProgramaInline)

    fields = (
        'instituicao',
        'descricao',
        'coordenacao',
    )
    field_widgets = {
        'coordenacao': s2forms.ModelSelect2Widget(
            model=Professor,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 3}
        ),
    }

    def get_buttons(self, request, object_id=None):
        buttons = super(ProgramaAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/resumo_qualis/%d' % object_id,
                            label='Qualis Docentes'))

            buttons.append(
                PowerButton(url='/programa_csv_producao/%d' % object_id,
                            label='CSV Produção Docente')
            )

            buttons.append(
                PowerButton(url='/orientacoes?programa=%d' % object_id,
                            label='Orientações')
            )

        return buttons

    def get_actions(self, request):
        actions = super(ProgramaAdmin, self).get_actions(request)
        actions['resumo_qualis'] = (
            view_resumo_qualis, 'resumo_qualis', 'Resumo Qualis')
        return actions


@admin.register(TipoCurso)
class TipoCursoAdmin(PowerModelAdmin):
    list_display = ('id', 'descricao')


@admin.register(Curso)
class CursoAdmin(PowerModelAdmin):
    list_display = ('programa', 'descricao', 'num_alunos', 'num_alunos_total')

    def get_buttons(self, request, object_id=None):
        buttons = super(CursoAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/resumo_qualis/0/%d' % object_id,
                            label='Qualis Discentes'))
        return buttons


@admin.register(CursoControle)
class CursoControleAdmin(PowerModelAdmin):
    pass


class DisciplinaInline(PowerTabularInline):
    model = Disciplina
    fields = ('titulo', 'codigo', 'status')
    extra = 0
    readonly_fields = ('titulo', 'codigo', 'status')
    ordering = ('titulo',)


@admin.register(Curriculo)
class CurriculoAdmin(PowerModelAdmin):
    list_display = ('descricao', 'ano', 'status')
    inlines = (DisciplinaInline,)


class DisciplinaCursoInline(PowerTabularInline):
    model = DisciplinaCurso
    fields = ('curso', 'codigo', 'linhapesquisa')
    extra = 0


class CursoFilter(admin.SimpleListFilter):
    title = 'Curso'
    parameter_name = 'curso'
    default_value = None

    def lookups(self, request, model_admin):
        q = DisciplinaCurso.objects.all().values(
            'curso_id', 'curso__descricao').distinct()
        cursos = []
        for ano in q:
            cursos.append((ano['curso_id'], ano['curso__descricao']))
        return tuple(cursos)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(disciplinacurso__curso_id=value)
        else:
            return queryset.all()


@admin.register(Disciplina)
class DisciplinaAdmin(PowerModelAdmin):
    list_display = ('titulo', 'codigo', 'curriculo', 'status', 'tipo',)
    list_filter = (CursoFilter,)
    search_fields = ('titulo', 'codigo', 'disciplinacurso__codigo',)
    inlines = (DisciplinaCursoInline,)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super(DisciplinaAdmin, self).get_search_results(request, queryset, search_term)
        queryset.distinct()
        return queryset, use_distinct


class ProfessorInline(PowerTabularInline):
    model = ProfessorLinha
    fields = ('professor', 'linha', 'permanente', 'dtentrada', 'dtsaida')
    autocomplete_fields = ('professor',)
    extra = 0
    form = ProfessorLinhaForm
    verbose_name = 'Professor'
    verbose_name_plural = 'Professores'


class LinhaPesquisaAdmin(PowerModelAdmin):
    list_display = ('descricao', 'programa')
    list_filter = ('programa',)
    multi_search = (('q1', 'Docente', ['professorlinha__professor__nome']),)
    inlines = (ProfessorInline,)


class ProjetoInline(admin.TabularInline):
    model = PesquisadorProjeto
    fields = ('pesquisador',)
    raw_id_fields = ('pesquisador',)
    extra = 0


class ProjetoPesquisaAdmin(PowerModelAdmin):
    multi_search = (
        ('q1', 'Título do Projeto', ['nome']),
        ('q2', 'Pesquisador', ['proponente__nome'])
    )
    form = ProjetoPesquisaForm
    list_filter = ('status',)
    list_display = ('nome', 'proponente', 'num_pesquisadores',
                    'num_producao', 'num_artigos', 'status')
    inlines = (ProjetoInline,)

    def save_related(self, request, form, formsets, change):
        super(ProjetoPesquisaAdmin, self).save_related(
            request, form, formsets, change)
        projeto = form.instance
        PesquisadorProjeto.objects.get_or_create(
            projeto=projeto, pesquisador=projeto.proponente)


@admin.register(PesquisadorProjeto)
class PesquisadorProjetoAdmin(PowerModelAdmin):
    multi_search = (
        ('q1', 'Pesquisador', ['pesquisador__nome'])
    )
    list_display = ('pesquisador', 'projeto',)


class InlineNotificacao(PowerStackedInline):
    model = TipoNotificacao
    fields = ('destinatario', 'texto')
    extra = 0


@admin.register(TipoOcorrencia)
class TipoOcorrenciaAdmin(PowerModelAdmin):
    search_fields = ('descricao',)
    list_filter = ('status',)
    list_display = ('id', 'descricao', 'url_link', 'status',)
    fields = ('descricao', 'detalhe', 'template', 'url_requerimento', 'status', 'cursos',)
    inlines = (InlineNotificacao,)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    @admin.display(description='URL Externa')
    def url_link(self, instance):
        return mark_safe(f'<a href="{instance.url_requerimento}">Link Externo</a>')

    url_link.allow_tags = True

    def save_model(self, request, obj, form, change):
        if change:
            if not obj.validate_templates(request):
                obj.status = TipoOcorrencia.Status.INATIVO
        super().save_model(request, obj, form, change)


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(PowerModelAdmin):
    list_display = ('descricao',)
    fields = ('descricao', 'chave')


@admin.register(Periodo)
class PeriodoAdmin(PowerModelAdmin):
    list_filter = ('status', 'ano',)
    list_display = ('ano', 'tipo_periodo', 'ident', 'status')
    fields = ('ano', 'tipo_periodo', 'ident', 'dt_fim_matricula', 'status')

    def get_buttons(self, request, object_id=None):
        buttons = super(PeriodoAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(PowerButton(url='/periodo_resumo/%s' % object_id, label='Resumo'))
        return buttons

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.dt_fim_matricula:
            messages.warning(request,
                             'Sem a data de fim de matrícula, o período não ficará habilitado para a/os discentes')


class PeriodoFilter(admin.SimpleListFilter):
    title = 'Período'
    parameter_name = 'periodo'
    default_value = None
    _todos = '__all__'

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(PeriodoFilter, self).value()

        if value is None:
            if self.default_value is None:
                periodo = Periodo.objects.filter(status='A').first()
                value = None if periodo is None else periodo.id
                self.default_value = value
            else:
                value = self.default_value

        return str(value) if value is not None else None

    def lookups(self, request, model_admin):
        q = Periodo.objects.all()
        dataset = []
        for periodo in q:
            dataset.append((str(periodo.id), periodo.__str__()))
        return tuple(dataset)

    def queryset(self, request, queryset):
        value = self.value()

        if value is None or value == self._todos:
            return queryset

        lookup = 'periodo__id' if queryset.model == Turma else 'turma__periodo__id'

        return queryset.filter(**{lookup: value})

    def choices(self, changelist):
        """
        Função sobrescrita, para adicionar __all__ em todos e assim permitir que o filtro venha com um valor default no
        carregamento inicial da página e que o usuário consiga selecionar a opção todos em uma segunda busca.
        """
        choices_gen = super().choices(changelist)
        # Retorna o item que representa o todos
        todos = next(choices_gen)
        # O item "Todos" agora tem um valor real na URL
        todos['query_string'] = changelist.get_query_string({self.parameter_name: self._todos})
        todos['selected'] = self.value() == self._todos

        yield todos
        yield from choices_gen


class TurmaCursoInline(PowerTabularInline):
    model = TurmaCurso
    fields = ('curso',)
    extra = 1
    verbose_name_plural = 'Cursos Permitidos'


class TurmaProfessorInline(PowerTabularInline):
    model = TurmaProfessor
    fields = ('professor',)
    raw_id_fields = ('professor',)
    extra = 0


class TurmaHorarioInline(PowerTabularInline):
    model = TurmaHorario
    fields = ('dia_semana', 'horario', 'horario_termino')
    extra = 0


@admin.register(Turma)
class TurmaAdmin(PowerModelAdmin):
    list_filter = (PeriodoFilter, 'disciplina')
    list_display = ('periodo', 'disciplina_codigo', 'titulo', 'calendario', 'tot_discentes', 'externa')
    fields = ('periodo', 'disciplina', 'titulo', 'num_alunos_max', 'externa', 'info_matricula', 'info_secretaria')
    inlines = (TurmaHorarioInline, TurmaProfessorInline, TurmaCursoInline)
    multi_search = (
        ('professor', 'Pesquisador', ['turmaprofessor__professor__nome']),
        ('curso', 'Curso', ['turmacurso__curso__descricao']),
    )

    def get_changeform_initial_data(self, request):
        periodo_atual = Periodo.objects.order_by('id').last()
        initial_data = {'periodo': periodo_atual}
        return initial_data

    def get_buttons(self, request, object_id=None):
        buttons = super(TurmaAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url=f'/turma/completa/{object_id}', label=u'Inscrever todos')
            )
            buttons.append(
                PowerButton(url=f'/admin/nucleo/inscricao/?turma_id={object_id}', label=u'Inscrições')
            )
            buttons.append(
                PowerButton(
                    url=reverse('diario_de_classe', args=(object_id,)),
                    label='Diário de Classe', attrs={'target': '_blank'}
                )
            )
        return buttons

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # adiciona todos os cursos associados à disciplina da turma, caso o usuário não tenha especificado os cursos
        total_cursos = obj.turmacurso_set.count()
        if total_cursos == 0:
            for record in obj.disciplina.disciplinacurso_set.all():
                if not obj.turmacurso_set.filter(curso=record.curso).exists():
                    obj.turmacurso_set.create(curso=record.curso)


@admin.register(Inscricao)
class InscricaoAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    list_filter = (PeriodoFilter,)
    list_display = ('turma', 'aluno', 'status', 'dtinscricao',)
    list_csv = ('turma', 'aluno__nome', 'aluno__email', 'aluno__CPF', 'aluno__matricula_atual',
                'conceito', 'status', 'obs')
    multi_search = (
        ('q1', 'Discente', ['aluno__nome']),
        ('q2', 'Disciplina', ['turma__disciplina__titulo']),
        ('q3', 'Curso', ['aluno__matricula_atual__curso__descricao'])
    )
    fields = ('turma', 'aluno', 'conceito', 'status', 'obs')
    raw_id_fields = ('aluno',)
    list_select_related = ('turma', 'aluno', 'aluno__matricula_atual__curso')
    field_styles = {
        'obs': 'height: 2em; width: 80em;',
    }
    field_widgets = {
        'aluno': s2forms.ModelSelect2Widget(
            model=Pesquisador,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 3}),
    }

    def lookup_allowed(self, lookup, value):
        if lookup in ('turma__id',):
            return True
        return super(InscricaoAdmin, self).lookup_allowed(lookup, value)

    @admin.display(description='Campus')
    def local(self, instance):
        if instance.aluno.matricula_atual:
            return instance.aluno.matricula_atual.local or 'RIO'
        else:
            return '-'


class ProfessorAtivoFilter(admin.SimpleListFilter):
    title = 'Ativo'
    parameter_name = 'ativo'
    default_value = None

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(ProfessorAtivoFilter, self).value()
        if value is None:
            value = 'Sim'
        return str(value)

    def lookups(self, request, model_admin):
        return tuple([('Sim', 'Sim'), ('Não', 'Não'), ])

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'Sim':
            return queryset.filter(pesquisadorprograma__isnull=False)
        if value == 'Não':
            return queryset.filter(pesquisadorprograma__isnull=True)
        else:
            return queryset.all()


class ProgramaFilter(admin.SimpleListFilter):
    title = 'Programa'
    parameter_name = 'programa'
    default_value = None

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(ProgramaFilter, self).value()
        if value is None:
            if self.default_value is None:
                programa = PesquisadorPrograma.objects.first()
                value = None if programa is None else programa.id
                self.default_value = value
            else:
                value = self.default_value
        return str(value)

    def lookups(self, request, model_admin):
        q = PesquisadorPrograma.objects.all().values(
            'programa', 'programa__descricao').distinct()
        programas = []
        for ano in q:
            programas.append((ano['programa'], ano['programa__descricao']))
        return tuple(programas)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(pesquisadorprograma__programa_id=value)
        else:
            return queryset.all()


class AnoFilter(admin.SimpleListFilter):
    title = 'ano'
    parameter_name = 'ano'

    def lookups(self, request, model_admin):
        q = Matricula.objects.values(
            'ingresso').distinct().order_by('ingresso')
        anos = []
        for ano in q:
            anos.append((ano['ingresso'], ano['ingresso']))
        return tuple(anos)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(matricula__ingresso=value)
        else:
            return queryset.all()


class BolsaFilter(admin.SimpleListFilter):
    title = 'Tem Bolsa'
    parameter_name = 'bolsa'

    def lookups(self, request, model_admin):
        return (
            ('S', 'Sim'),
            ('N', 'Não'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'S':
            return queryset.filter(matricula__status_bolsa='A')
        elif value == 'N':
            return queryset.exclude(matricula__status_bolsa='A')
        return queryset


class EgressoFilter(admin.SimpleListFilter):
    title = 'Egresso'
    parameter_name = 'egresso'

    def lookups(self, request, model_admin):
        return (
            ('S', 'Sim'), ('N', 'Não'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'S':
            return queryset.exclude(matricula__status='A')
        elif value == 'N':
            return queryset.filter(matricula__status__in=('A', 'T'))
        return queryset


class AtualizadoFilter(admin.SimpleListFilter):
    title = 'Lattes Atualizado'
    parameter_name = 'atualizado'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Sim'), ('0', 'Não'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == '0':
            return queryset.filter(atualizado=False)
        elif value == '1':
            return queryset.filter(atualizado=True)
        return queryset


class MatriculaInline(admin.TabularInline):
    model = Matricula
    fields = ('admin_link', 'ingresso', 'status', 'dtdefesa', 'dtconclusao',)
    readonly_fields = ('admin_link', 'ingresso', 'status', 'dtdefesa', 'dtconclusao',)
    extra = 0

    @admin.display(description='Curso')
    def admin_link(self, instance):
        url = reverse('admin:nucleo_matricula_change', args=(instance.id,))
        return mark_safe(f'<a href="{url}">{instance.curso.descricao}</a>')

    admin_link.allow_tags = True

    def has_add_permission(self, request, obj=None):
        return False


class OrientadorInline(PowerTabularInline):
    model = Orientacao
    fk_name = 'aluno'
    fields = ('orientacao_link', 'coorientacao', 'status',)
    readonly_fields = ('orientacao_link',)
    extra = 0

    @admin.display(description='Orientação')
    def orientacao_link(self, obj):
        url = reverse('admin:nucleo_orientacao_change', args=(obj.id,))
        return mark_safe(f'<a href="{url}">{obj.orientador}</a>')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Aluno)
class AlunoAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    search_fields = ('nome',)
    list_filter = (AnoFilter, EgressoFilter, BolsaFilter, AtualizadoFilter, 'matricula_atual__status')
    list_display = ('nome', 'email', 'curso', 'ingresso', 'status_matricula', 'orientador',)
    list_report = ('nome:400px:left', 'email:200px', 'turma', 'status_matricula:100px', 'numero_matricula')
    list_csv = ('nome', 'email', 'programa', 'curso', 'ingresso', 'status_matricula', 'orientador',)
    fields = (
        'nome', ('email', 'email_alternativo'), 'telefones',
        ('sexo', 'raca', 'situacao'),
        ('CPF', 'id_cnpq', 'id_lattes'),
        ('orcid', 'id_funcional', 'atualizado'),
    )
    inlines = (MatriculaInline, OrientadorInline)
    readonly_fields = []
    form = AlunoForm
    field_styles = {
        'nome': 'width: 50em;',
        'email': 'width: 30em;',
        'CPF': 'width: 10em;',
        'telefones': 'height: 1em; width: 80em;',
        'id_lattes': 'width: 10em;',
        'id_cnpq': 'width: 10em;',
    }
    field_widgets = {
        'atualizado': forms.HiddenInput,
    }

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('matricula_atual__curso__programa')

    @admin.display(description='Ingresso', ordering='matricula_atual__ingresso')
    def ingresso(self, obj):
        if obj.matricula_atual:
            return obj.matricula_atual.ingresso

    @admin.display(description='Programa', ordering='matricula_atual__programa__descricao')
    def programa(self, obj):
        if obj.matricula_atual:
            return obj.matricula_atual.curso.programa.descricao

    @admin.display(description='Curso', ordering='matricula_atual__curso')
    def curso(self, obj):
        if obj.matricula_atual:
            return obj.matricula_atual.curso.descricao

    def get_readonly_fields(self, request, obj=None):
        if request.user.groups.filter(name='Representação Discente').exists():
            return list(self.readonly_fields) + \
                [field.name for field in obj._meta.fields] + \
                [field.name for field in obj._meta.many_to_many]

        return super(AlunoAdmin, self).get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        if request.user.groups.filter(name='Representação Discente').exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if request.user.groups.filter(name='Representação Discente').exists():
            return False
        return True

    def get_buttons(self, request, object_id=None):
        buttons = super(AlunoAdmin, self).get_buttons(request, object_id)
        if object_id:
            aluno = Aluno.objects.get(id=object_id)
            url = aluno.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes'))

            if aluno.id_cnpq:
                buttons.append(PowerButton(url=URL_CNPQ % aluno.id_cnpq, label='CNPQ'))
                buttons.append(PowerButton(url=f'/update_lattes/{aluno.id_cnpq}', label='Update Lattes'))

            buttons.append(PowerButton(
                url=f"{reverse('admin:nucleo_matricula_add')}?pesquisador={aluno.id}",
                label="Nova Matrícula"))

            # se for representação discente, os botões abaixo não podem estar habilitados
            if not request.user.groups.filter(name='Representação Discente').exists():
                if hasattr(aluno, 'alunoregistro'):
                    registro = aluno.alunoregistro
                else:
                    registro, _ = AlunoRegistro.objects.get_or_create(aluno=aluno)
                    registro.save()

                buttons.append(PowerButton(
                    url=reverse('admin:nucleo_alunoregistro_change', args=(registro.pk,)),
                    label="Dados Pessoais"))

                matricula = aluno.matricula_set.filter(status='A').first()
                if matricula:
                    buttons.append(PowerButton(
                        url=f"{reverse('admin:nucleo_orientacao_add')}?curso={matricula.curso.id}&aluno={aluno.id}",
                        label="Nova orientação"))

        return buttons


@admin.register(AlunoRegistro)
class AlunoRegistroAdmin(PowerModelAdmin):
    readonly_fields = ('aluno', 'dt_cadastro',)

    def has_delete_permission(self, request, obj=None):
        # Permite excluir o AlunoRegistro, se estiver excluindo Aluno pelo admin
        resolver_match = resolve(request.path_info)
        return resolver_match is not None and resolver_match.url_name == 'nucleo_aluno_delete'


class OrientandosInline(PowerTabularInline):
    model = Orientacao
    fields = ('aluno', 'turma', 'coorientacao', 'status',)
    readonly_fields = ('aluno', 'turma',)
    extra = 0
    can_delete = False
    verbose_name = 'Orientando'
    verbose_name_plural = 'Orientandos Ativos'

    def get_queryset(self, request):
        qs = super(OrientandosInline, self).get_queryset(request)
        return qs.filter(status='A')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Professor)
class ProfessorAdmin(PowerModelAdmin):
    search_fields = ('nome',)
    list_filter = (ProgramaFilter, ProfessorAtivoFilter,)
    list_display = ('nome', 'email', 'num_orientandos', 'num_projetos', 'status_lattes', 'atualizado')
    fields = ('nome', 'email', 'CPF', 'sexo', 'situacao', ('id_lattes', 'id_cnpq',),
              'num_projetos', 'num_orientandos_concluidos', 'mini_bio', 'fotografia', ('dtupdate', 'atualizado'),
              'user')
    readonly_fields = ('dtupdate', 'atualizado',
                       'num_orientandos_concluidos', 'num_projetos')
    list_csv = ('nome', 'email', 'sexo', 'id_cnpq')
    inlines = (LinhaProfessorInline, OrientandosInline)
    actions = ('verifica_lattes',)
    form = PesquisadorForm

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return 'dtupdate', 'num_orientandos_concluidos', 'num_projetos'
        else:
            return 'dtupdate', 'user', 'atualizado', 'num_orientandos_concluidos', 'num_projetos'

    def get_buttons(self, request, object_id=None):
        buttons = super(ProfessorAdmin, self).get_buttons(request, object_id)
        if object_id:
            professor = Professor.objects.get(id=object_id)
            url = professor.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes'))
            if professor.id_cnpq:
                buttons.append(PowerButton(url=URL_CNPQ %
                                               professor.id_cnpq, label='CNPQ'))
                buttons.append(PowerButton(url='/update_lattes/%s' % professor.id_cnpq, label='Update Lattes'))
            if professor.pesquisadorprojeto_set.count() > 0:
                buttons.append(
                    PowerButton(url='/producao_projeto/%s' % professor.id_lattes, label='Produção x Projetos'))

            buttons.append(
                PowerButton(url=f'/admin/nucleo/producao/?pesquisador={object_id}', label='Produções',
                            attr={'target': '_blank'})
            )

        return buttons

    def verifica_lattes(self, request, queryset):
        tot_reg = 0
        for reg in queryset:
            dt_cnpq = obtem_dt_cnpq(reg.id_cnpq)
            if dt_cnpq > reg.dtupdate:
                reg.atualizado = False
                reg.save()
                tot_reg += 1
        messages.info(request, u'%d pesquisadores atualizaram o currículo')
        return


class OrientadoresInline(PowerTabularInline):
    model = Orientacao
    fields = ('orientacao_url', 'coorientacao', 'dt_inicio', 'status',)
    readonly_fields = ('orientacao_url',)
    extra = 0
    can_delete = False
    verbose_name = 'Orientação'
    verbose_name_plural = 'Orientações'

    def has_add_permission(self, request, obj=None):
        return False


class EventosInline(PowerTabularInline):
    model = MatriculaEvento
    fields = ('get_admin_url', 'tipo', 'dtevento', 'dtinclusao', 'status')
    readonly_fields = ('get_admin_url', 'tipo', 'dtevento', 'dtinclusao', 'status')
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='ID')
    def get_admin_url(self, obj):
        reversed_url = reverse('admin:nucleo_matriculaevento_change', args=(obj.pk,))
        return mark_safe(f'<a href={reversed_url}>{obj.pk}</a>')


@admin.register(Matricula)
class MatriculaAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    search_fields = ('pesquisador__nome', 'pesquisador__email', 'numero')
    list_filter = ('curso', 'ingresso', 'status', 'status_bolsa')
    list_csv = ('pesquisador', 'pesquisador_email', 'curso__programa__descricao', 'curso__descricao', 'ingresso',
                'status', 'dtquali', 'dtdefesa',)
    list_display = ('pesquisador', 'curso', 'ingresso', 'status', 'status_bolsa',
                    'dtquali', 'dtdefesa', 'dtconclusao',)
    fields = (('pesquisador', 'numero_readonly'), ('curso', 'ingresso', 'status_bolsa', 'status',),
              ('dtmatricula', 'dtquali', 'dtprevista'),
              ('dtdefesa', 'dtconclusao',),
              'titulo', 'obs',
              )
    readonly_fields = ('numero_readonly',)
    inlines = (OrientadoresInline, EventosInline)
    list_select_related = ('curso__programa', 'curso__programa__instituicao', 'pesquisador')
    field_styles = {
        'titulo': 'height: 2em; width: 80em;',
        'obs': 'height: 2em; width: 80em;',
    }
    field_widgets = {
        'pesquisador': s2forms.ModelSelect2Widget(
            model=Pesquisador,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 3}),
    }

    def get_buttons(self, request, object_id=None):
        buttons = super(MatriculaAdmin, self).get_buttons(request, object_id)
        if object_id:
            matricula = Matricula.objects.get(id=object_id)
            buttons.append(
                PowerButton(url=reverse('admin:nucleo_aluno_change',
                                        args=(matricula.pesquisador.id,)), label=u'Aluno'))
            buttons.append(PowerButton(
                url=f"{reverse('admin:nucleo_orientacao_add')}?curso={matricula.curso.id}&aluno={matricula.pesquisador.id}",
                label="Nova orientação"))
            buttons.append(PowerButton(
                url=f"{reverse('admin:nucleo_matriculaevento_add')}?matricula={matricula.pk}",
                label='Nova ocorrência'))
            if ResumoAnual.objects.filter(status=STATUS_ATIVO):
                buttons.append(
                    PowerButton(url='/convite_individual/%d' % matricula.id,
                                label=u'Convite'))

            if matricula.curso.historico:
                buttons.append(
                    PowerButton(
                        url=reverse('historico') + f'?matricula={matricula.hash}',
                        label='Histórico Escolar'
                    )
                )
            buttons.append(
                PowerButton(
                    url=reverse('declaracao_matricula_pdf', args=(matricula.id,)),
                    label='Declaração'
                )
            )
        return buttons

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.pesquisador.CPF in EMPTY_VALUES:
            self.message_user(request, 'Discente sem CPF registrado. Faça o ajuste.', messages.WARNING)


class EventoDocumentoInline(GenericTabularInline):
    model = Documento
    fields = ('tipo', 'anexo')
    extra = 1


class EventoPesquisadorInline(PowerTabularInline):
    model = MatriculaEventoPesquisador
    autocomplete_fields = ('pesquisador',)
    fields = ('pesquisador', 'ordem', 'externo', 'suplente',)
    extra = 1


@admin.register(MatriculaEvento)
class MatriculaEventoAdmin(PowerModelAdmin):
    list_filter = ('tipo', 'status', 'ata_reuniao__descricao',)
    search_fields = ('id', 'descricao',)
    list_display = ('tipo', 'descricao', 'link_externo', 'dtinclusao', 'status', 'dtaprovacao',)
    readonly_fields = ('link_externo',)
    raw_id_fields = ('matricula', 'ata_reuniao')
    inlines = (EventoDocumentoInline, EventoPesquisadorInline,)
    actions = ('aprovado_na_cd', 'solicita_aprovacao_orientador', 'reenvia_email_orientador',)
    ordering = ('-id',)

    def save_formset(self, request, form, formset, change):
        """Registra log na ocorrência quando o admin altera os membros da banca."""
        super().save_formset(request, form, formset, change)

        # Só interessa o inline de membros da banca (MatriculaEventoPesquisador).
        if formset.model is not MatriculaEventoPesquisador:
            return

        ocorrencia = form.instance
        for membro in getattr(formset, 'new_objects', []):
            log_object(ocorrencia, f'Membro da banca incluído: {membro}')
        for membro, campos in getattr(formset, 'changed_objects', []):
            log_object(ocorrencia, f'Membro da banca alterado: {membro} (campos: {", ".join(campos)})')
        for membro in getattr(formset, 'deleted_objects', []):
            log_object(ocorrencia, f'Membro da banca removido: {membro}')

    @admin.action(description='Reenvia email para o orientador')
    def reenvia_email_orientador(self, request, queryset):
        count = 0
        for evento in queryset:
            if evento.tipo.id in [2, 3, 4, 5, 6, 7, 9, 10]:
                if evento.matricula:
                    orientacao = Orientacao.objects.filter(
                        matricula=evento.matricula,
                        status=Orientacao.Status.ATIVA,
                        coorientacao=False,
                    ).select_related('orientador').first()
                    orientador = orientacao.orientador if orientacao else None
                    if orientador:
                        evento.solicita_aprovacao_orientador(orientador)
                        count += 1
                    else:
                        self.message_user(request,
                                          f'Orientador não encontrado para o discente {evento.matricula.pesquisador}')
        self.message_user(request, f'{count} solicitações enviadas')

    @admin.action(description='Marcar como aprovado na CD')
    def aprovado_na_cd(self, request, queryset):
        count = 0
        for obj in queryset:
            if obj.status != MatriculaEvento.Status.APROVACAO_CD:
                obj.status = MatriculaEvento.Status.APROVACAO_CD
                obj.dtaprovacao = obj.ata_reuniao.dt
                obj.save()
                count += 1
        self.message_user(request, f'{count} solicitações aprovadas')

    def get_buttons(self, request, object_id=None):
        buttons = super(MatriculaEventoAdmin, self).get_buttons(request, object_id)
        if object_id:
            evento = MatriculaEvento.objects.filter(id=object_id).select_related(
                'matricula', 'matricula__curso').only('id',
                                                      'matricula', 'status',
                                                      'matricula__curso__historico').first()

            if evento.status == MatriculaEvento.Status.APROVACAO_ORIENTADOR:
                buttons.append(
                    PowerButton(url=reverse('reenvia_email_banca_agendada', args=[object_id]),
                                label='Reenviar e-mail da banca')
                )

            if evento.matricula.curso.historico:
                url = f'/historico?matricula={evento.matricula.hash}'
            else:
                ct = ContentType.objects.get_for_model(MatriculaEvento)
                doc = Documento.objects.filter(tipo__chave='HISTORICO', content_type=ct, object_id=evento.id).first()
                if doc:
                    url = doc.anexo.url
                else:
                    url = None

            if url:
                buttons.append(
                    PowerButton(url=url,
                                label='Histórico Escolar'))

        return buttons


class PesquisadorInstituicaoInline(PowerTabularInline):
    model = PesquisadorInstituicao
    fields = ('instituicao',)
    autocomplete_fields = ('instituicao',)
    extra = 1


class PesquisadorFormacaoInline(PowerTabularInline):
    model = PesquisadorFormacao
    fields = ('nivel', 'curso', 'nome_instituicao', 'ano_entrada', 'ano_conclusao')
    extra = 0


class ProgramaInline(admin.TabularInline):
    model = PesquisadorPrograma
    fields = ('programa', 'vinculo',)
    autocomplete_fields = ('programa',)
    extra = 0
    form = PesquisadorProgramaForm


@admin.register(Pesquisador)
class PesquisadorAdmin(PowerModelAdmin):
    search_fields = ('nome', 'id_cnpq')
    list_display = ('nome', 'email', 'id_cnpq')
    fields = ('nome', 'email', 'sexo', 'raca', 'situacao',
              'id_lattes', 'id_cnpq', 'orcid', 'CPF', 'pais', 'dtupdate', 'user')
    autocomplete_fields = ('pais',)
    inlines = (ProgramaInline, PesquisadorInstituicaoInline, PesquisadorFormacaoInline)
    form = PesquisadorForm
    actions = ('merge',)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return []
        else:
            return ['dtupdate', 'user']

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super(PesquisadorAdmin, self).get_search_results(
            request, queryset, search_term
        )
        # No autocomplete do inline de docentes da linha, oferece somente quem tem Lattes
        if (request.GET.get('app_label') == 'nucleo'
                and request.GET.get('model_name') == 'professorlinha'
                and request.GET.get('field_name') == 'professor'):
            queryset = queryset.com_lattes()
        return queryset, may_have_duplicates

    def get_buttons(self, request, object_id=None):
        buttons = super(PesquisadorAdmin, self).get_buttons(request, object_id)
        if object_id:
            pesquisador = Pesquisador.objects.get(id=object_id)
            url = pesquisador.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes', attrs={'target': '_blank'}))
            if pesquisador.orcid:
                buttons.append(
                    PowerButton(url=f'https://orcid.org/{pesquisador.orcid}', label='ORCID',
                                attrs={'target': '_blank'}))

            if pesquisador.id_cnpq:
                buttons.append(
                    PowerButton(url=URL_CNPQ % pesquisador.id_cnpq, label='CNPQ', attrs={'target': '_blank'}))
                buttons.append(
                    PowerButton(url=f'/update_lattes/{pesquisador.id_cnpq}', label='Update Lattes',
                                attrs={'target': '_blank'}))

                if request.user.is_superuser:
                    buttons.append(
                        PowerButton(url=reverse('baixar_xml_lattes', args=(object_id,)), label='Baixar XML Lattes', )
                    )
            buttons.append(
                PowerButton(url='/admin/nucleo/producao/?q2=%s' % pesquisador.nome.replace(' ', '+'),
                            label=u'Produção', attrs={'target': '_blank'}))
        return buttons

    def get_actions(self, request):
        actions = super(PesquisadorAdmin, self).get_actions(request)
        if not request.user.is_superuser:
            if 'merge' in actions:
                del actions['merge']
        return actions

    def merge(self, request, queryset):
        result = merge_pesquisadores(queryset)
        if result > 0:
            messages.info(request, f'{result} pesquisadores foram agrupados')
        else:
            messages.warning(request, 'Escolha ao menos 2 pesquisadores')


class AutoresInline(PowerTabularInline):
    model = ProducaoAutor
    extra = 1
    readonly_fields_linked = ('autor_link',)
    raw_id_fields = ('autor',)

    def get_readonly_fields(self, request, obj=None):
        fields = super(AutoresInline, self).get_readonly_fields(request, obj)
        if not self.has_add_permission(request, obj):
            fields += self.readonly_fields_linked
        return fields

    def get_fields(self, request, obj=None):
        fields = super(AutoresInline, self).get_fields(request, obj)
        if not self.has_add_permission(request, obj):
            for field in self.readonly_fields_linked:
                for field_clean in field.split('_'):
                    if field_clean in fields:
                        link_index = fields.index(field)
                        fields[fields.index(field_clean)] = field
                        del fields[link_index]
        return fields

    def autor_link(self, obj):
        return mark_safe('<a href="/admin/nucleo/pesquisador/%s/change">%s</a>' % (obj.autor.pk, obj.autor))

    autor_link.short_description = 'Autor'


class ProducaoAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    multi_search = (
        ('q1', 'Titulo', ['titulo']),
        ('q2', 'Pesquisador', ['producaoautor__autor__nome']),
        ('q3', 'ISBN', ['isbn']),
        ('q4', 'ISSN', ['periodico__issn'])
    )
    inlines = (AutoresInline,)
    list_filter = ('ano', 'tipo', 'pais',)
    list_display = ('titulo', 'pesquisador', 'tipo', 'ano', 'qualis',)
    list_csv = ('titulo', 'pesquisador', 'tipo', 'ano', 'qualis')
    raw_id_fields = ('periodico', 'projeto')
    list_per_page = 50
    field_styles = {
        'titulo': 'height: 1em; width: 80em;',
    }

    fields = ('tipo', 'titulo', 'descricao',
              ('doi', 'isbn', 'doi_validado',),
              ('periodico', 'ano', 'volume', 'serie'),
              ('natureza_obra', 'tipo_obra', 'meio',),
              ('tipo_editora', 'editora', 'conselho_editorial',),
              ('cidade', 'pais', 'idioma',),
              ('organizacao', 'natureza_texto',),
              ('area_impacto', 'nivel_impacto', 'abrangencia', 'complexidade'),
              ('setor', 'tipo_financiamento',),
              ('projeto_livre', 'projeto', 'sem_projeto', 'conta_sucupira'),
              ('comprovante', 'validacao', 'ident_unico', 'dt_inclusao'),
              )

    readonly_fields = ('ident_unico', 'dt_inclusao')

    def get_buttons(self, request, object_id=None):
        buttons = super(ProducaoAdmin, self).get_buttons(request, object_id)
        if object_id:
            producao = Producao.objects.get(id=object_id)

            if request.user.is_superuser:
                buttons.append(
                    PowerButton(url=reverse('visualizar_producao',
                                            kwargs={'hash_producao': object_id}), label='Visão do Usuário'))

            if producao.tipo.cod_externo == 'artigo':
                buttons.append(
                    PowerButton(url='/producao_analise/%s' % producao.id, label='Analisar'))

            if producao.periodico:
                buttons.append(
                    PowerButton(url='/admin/qualis/periodico/%s/change/' % producao.periodico.pk, label='Periodico',
                                attrs={'target': '_blank'})
                )

        return buttons

    class Media:
        css = {
            'all': ('css/custom_forms.css',)
        }

    @admin.display(description='Título', ordering='titulo')
    def producao(self, obj):
        """Link para o form de produção no modo readonly"""
        producao_url = reverse('visualizar_producao', kwargs={'hash_producao': obj.pk})
        return mark_safe(f'<a href="{producao_url}" target="_blank">{obj}</a>')

    def get_list_display(self, request):
        """Retorna o título com link para admin change_view ou link para o form de produção"""
        if request.user.is_superuser:
            list_display = ('titulo',)
        else:
            list_display = ('producao',)

        list_display += ('pesquisador', 'tipo', 'ano', 'qualis',)

        return list_display


class FomentoInline(admin.TabularInline):
    model = PesquisadorFomento
    fields = ('pesquisador', 'dtinicio', 'dtfim', 'obs')
    extra = 1


class FomentoAdmin(PowerModelAdmin):
    inlines = (FomentoInline,)


class ProducaoAutorAdmin(PowerModelAdmin):
    model = ProducaoAutor
    multi_search = (
        ('q1', 'Autor', ['nome']),
        ('q2', 'Produção', ['producao__titulo'])
    )
    list_filter = ('producao__ano', 'producao__tipo',
                   'producao__periodico__qualis')
    list_display = ('autor_link', 'producao_link', 'qualis', 'ano',)
    readonly_fields = ('autor', 'producao', 'nome', 'ordem',)

    def lookup_allowed(self, lookup, value):
        if lookup == 'producao__periodico__qualis':
            return True
        return super(ProducaoAutorAdmin, self).lookup_allowed(lookup, value)

    def get_buttons(self, request, object_id=None):
        buttons = super(ProducaoAutorAdmin, self).get_buttons(
            request, object_id)
        if object_id:
            producao_id = ProducaoAutor.objects.get(id=object_id).producao_id
            buttons.append(
                PowerButton(url=reverse('admin:nucleo_producao_change',
                                        args=(producao_id,)), label=u'Produção'))
        return buttons

    def producao_link(self, obj):
        return mark_safe('<a href="/admin/nucleo/producao/%s/change/">%s</a>' % (obj.producao.pk, obj.producao))

    producao_link.short_description = 'Produção'

    def autor_link(self, obj):
        if obj.autor:
            return mark_safe('<a href="/admin/nucleo/pesquisador/%s/change/">%s</a>' % (obj.autor.pk, obj.autor))
        else:
            return obj.nome

    autor_link.short_description = 'Nome do Autor'


class ResumoAnualAdmin(PowerModelAdmin):
    list_display = ('ano', 'total_pesquisadores',
                    'total_em_edicao', 'total_aguardando', 'total_avaliados')
    readonly_fields = ('total_pesquisadores', 'total_em_edicao',
                       'total_aguardando', 'total_avaliados')

    def get_buttons(self, request, object_id=None):
        buttons = super(ResumoAnualAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/convite_alunos/%s' % object_id, label='Enviar convites'))

        return buttons


class RelatorioAnualAdmin(PowerModelAdmin):
    list_display = ('pesquisador', 'pesquisador_email',
                    'orientador_email', 'ano', 'status')
    list_filter = ('ano', 'status',)
    search_fields = ('pesquisador__nome',)
    list_select_related = ('pesquisador', 'pesquisador__matricula_atual',)

    @admin.display(description='Email Orientador(a)')
    def orientador_email(self, obj):
        if obj.pesquisador.matricula_atual:
            orientacao = obj.pesquisador.matricula_atual.orientacao_set.filter(status=STATUS_ATIVO).first()
            if orientacao and orientacao.orientador:
                if orientacao.orientador.email:
                    return orientacao.orientador.email
                else:
                    return orientacao.orientador.nome
        return 'Sem orientador'

    @admin.display(ordering='pesquisador__email', description='Email')
    def pesquisador_email(self, obj):
        return obj.pesquisador.email


class BlogRawIdWidget(widgets.ForeignKeyRawIdWidget):
    def url_parameters(self):
        res = super().url_parameters()
        res['type__exact'] = 'PROJ'
        return res


@admin.register(Orientacao)
class OrientacaoAdmin(PowerModelAdmin):
    list_filter = ('status', 'coorientacao', 'matricula__curso', 'matricula__ingresso')
    list_display = ('orientador', 'aluno', 'curso', 'status', 'coorientacao', 'ano_ingresso')
    list_select_related = ('matricula', 'orientador', 'aluno')
    multi_search = (
        ('q1', 'Orientador', ['orientador__nome']),
        ('q2', 'Aluno', ['aluno__nome'])
    )
    form = OrientacaoAdminForm

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.attname in ('aluno_id', 'orientador_id'):
            formfield.widget.can_delete_related = False
            formfield.widget.can_change_related = False
            formfield.widget.can_add_related = False

        return formfield

    @admin.display(description='Ano de Ingresso', ordering='matricula__ingresso')
    def ano_ingresso(self, obj):
        if obj.matricula:
            return str(obj.matricula.ingresso)

    @admin.display(description='Curso', ordering='matricula__curso')
    def curso(self, obj):
        if obj.matricula:
            return str(obj.matricula.curso)

    def curso_related_fields(self, request, curso_id):
        data = {}
        if request.method == 'GET' and curso_id:
            alunos = Matricula.objects.filter(curso_id=curso_id).values(
                'pesquisador__id', 'pesquisador__nome')

            data['alunos'] = list(map(lambda x: dict(
                value=x['pesquisador__id'], label=x['pesquisador__nome']), alunos))

            data['professores'] = list(map(lambda x: dict(value=x['id'], label=x['nome']), Professor.objects.filter(
                pesquisadorprograma__programa__curso__id=curso_id).values('id', 'nome')))

        return HttpResponse(json.dumps(data), content_type='application/javascript')

    def get_urls(self):
        buttons_urls = [
            path('fields/curso/<int:curso_id>/chain/', self.wrap(self.curso_related_fields),
                 name="chain_fields"),
        ]
        return buttons_urls + super(OrientacaoAdmin, self).get_urls()

    def get_buttons(self, request, object_id=None):
        buttons = super(OrientacaoAdmin, self).get_buttons(request, object_id)
        if object_id:
            orientacao = Orientacao.objects.get(pk=object_id)
            if orientacao.matricula:
                buttons.append(PowerButton(url=orientacao.matricula_url, label='Matrícula associada'))
        return buttons

    def save_model(self, request, obj, form, change):
        obj.matricula = form.cleaned_data['matricula']
        if not change and obj.status == 'A':
            log_object(obj.aluno, f"Orientação registrada para o professor {obj.orientador}")
        else:
            if change and obj.status == 'X' and form.initial['status'] == 'A':
                log_object(obj.aluno, f"Orientação cancelada para o professor {obj.orientador}")

        return super().save_model(request, obj, form, change)


@admin.register(TipoProducao)
class TipoProducaoAdmin(PowerModelAdmin):
    list_display = ('descricao', 'categoria', 'edicao')


class PesquisadorGrupoInline(PowerTabularInline):
    model = PesquisadorGrupo
    fields = ('pesquisador', 'status')
    raw_id_fields = ('pesquisador',)
    extra = 0


@admin.register(GrupoPesquisa)
class GrupoPesquisaAdmin(PowerModelAdmin):
    search_fields = ('nome',)
    list_display = ('nome', 'id_cnpq', 'num_pesquisadores')
    inlines = (PesquisadorGrupoInline,)

    def get_buttons(self, request, object_id=None):
        buttons = super(GrupoPesquisaAdmin, self).get_buttons(
            request, object_id)
        if object_id:
            buttons.append(PowerButton(url=f'/exportar_grupo/{object_id}', label='Exportar CSV'))
            buttons.append(PowerButton(url=f'/exportar_grupo_lattes/{object_id}', label='Exportar Lattes'))
            buttons.append(PowerButton(url=f'/resumo_grupo/{object_id}', label='Dashboard'))

        return buttons


class PesquisadorGrupoAdmin(PowerModelAdmin):
    pass


class MatriculaEventoAtaInline(PowerTabularInline):
    model = MatriculaEvento
    fk_name = 'ata_reuniao'
    formset = MatriculaEventoAtaInlineFormSet
    form = MatriculaEventoAtaForm
    fields = ('selecionado', 'descricao', 'ocorrencia_url', 'dtevento', 'status')
    readonly_fields = ('descricao', 'ocorrencia_url', 'dtevento', 'status')
    can_delete = False
    extra = 0
    max_num = 0
    verbose_name_plural = 'Ocorrências (vincular/desvincular)'


@admin.register(AtaReuniao)
class AtaReuniaoAdmin(PowerModelAdmin):
    list_display = ('descricao', 'dt', 'arquivo')
    search_fields = ('descricao',)
    date_hierarchy = 'dt'
    inlines = (MatriculaEventoAtaInline,)

    def get_buttons(self, request, object_id=None):
        buttons = super(AtaReuniaoAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(
                    url=reverse('ata_ocorrencias_pdf', args=(object_id,)),
                    label='PDF das Ocorrências',
                    attrs={'target': '_blank'},
                )
            )
        return buttons

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)

        if not isinstance(formset, MatriculaEventoAtaInlineFormSet):
            return

        for instance, _ in formset.changed_objects:
            if instance.ata_reuniao_id:
                msg = f'Ocorrência {instance} vinculada à ata {form.instance}'
            else:
                msg = f'Ocorrência {instance} desvinculada da ata {form.instance}'
            self.log_change(request, form.instance, msg)


admin.site.register(Instituicao, InstituicaoAdmin)
admin.site.register(LinhaPesquisa, LinhaPesquisaAdmin)
admin.site.register(ProjetoPesquisa, ProjetoPesquisaAdmin)
admin.site.register(Fomento, FomentoAdmin)

admin.site.register(PesquisadorGrupo, PesquisadorGrupoAdmin)

admin.site.register(AreaImpacto)
admin.site.register(SetorEconomico)
admin.site.register(Producao, ProducaoAdmin)
admin.site.register(ProducaoAutor, ProducaoAutorAdmin)

admin.site.register(ResumoAnual, ResumoAnualAdmin)
admin.site.register(RelatorioAnual, RelatorioAnualAdmin)
