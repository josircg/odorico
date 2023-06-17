from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from poweradmin.admin import PowerModelAdmin, PowerButton, PowerTabularInline

from chupalattes import obtem_dt_cnpq, url_cnpq
from nucleo.actions import view_resumo_qualis
from nucleo.forms import ProjetoPesquisaForm, PesquisadorForm, PesquisadorProgramaForm, ProfessorLinhaForm
from nucleo.models import *


class InstituicaoAdmin(PowerModelAdmin):
    list_display = ('nome', 'sigla',)

    def get_form(self, request, obj=None, **kwargs):
        form = super(InstituicaoAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['nome'].widget.attrs['style'] = 'width: 40em;'
        form.base_fields['sigla'].widget.attrs['style'] = 'width: 10em;'
        return form


class LinhaPesquisaInline(admin.TabularInline):
    model = LinhaPesquisa
    fields = ('descricao',)
    extra = 0


class LinhaProfessorInline(admin.TabularInline):
    model = ProfessorLinha
    fields = ('linha', 'permanente', 'dtentrada', 'dtsaida',)
    extra = 0
    form = ProfessorLinhaForm


class CursoInline(admin.TabularInline):
    model = Curso
    fields = ('descricao', 'nivel',)
    extra = 0


class ProgramaAdmin(PowerModelAdmin):
    list_filter = ('instituicao', 'area',)
    list_display = ('instituicao', 'descricao', 'num_pesquisadores', 'num_alunos', 'num_artigos')
    inlines = (LinhaPesquisaInline, CursoInline)

    def get_buttons(self, request, object_id):
        buttons = super(ProgramaAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/resumo_qualis/%d' % object_id,
                            label='Resumo Qualis'))
            buttons.append(
                PowerButton(url='/mapa_paises?id=%d' % object_id,
                            label='Presença no Mundo'))

        return buttons

    def get_actions(self, request):
        actions = super(ProgramaAdmin, self).get_actions(request)
        actions['resumo_qualis'] = (view_resumo_qualis, 'resumo_qualis', 'Resumo Qualis')

        return actions


class CursoAdmin(PowerModelAdmin):
    list_display = ('programa', 'descricao', 'num_alunos')


class ProfessorInline(admin.TabularInline):
    model = ProfessorLinha
    fields = ('professor', 'linha', 'permanente', 'dtentrada', 'dtsaida')
    extra = 0
    form = ProfessorLinhaForm

class LinhaPesquisaAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'programa')
    inlines = (
        ProfessorInline,
    )


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
    list_display = ('nome', 'proponente', 'num_pesquisadores', 'num_producao', 'num_artigos', 'status')
    inlines = (ProjetoInline,)

    def save_related(self, request, form, formsets, change):
        super(ProjetoPesquisaAdmin, self).save_related(request, form, formsets, change)
        projeto = form.instance
        PesquisadorProjeto.objects.get_or_create(projeto=projeto, pesquisador=projeto.proponente)


class MatriculaInline(admin.TabularInline):
    model = Matricula
    fields = ('curso', 'ingresso', 'status', 'status_bolsa', 'dtdefesa', 'dtconclusao', 'admin_link')
    readonly_fields = ('admin_link',)
    extra = 0

    def admin_link(self, instance):
        url = reverse('admin:nucleo_matricula_change', args=(instance.id,))
        return mark_safe(f'<a href="{url}">Matrícula</a>')

    admin_link.allow_tags = True


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
        q = PesquisadorPrograma.objects.all().values('programa', 'programa__descricao').distinct()
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
        q = Matricula.objects.values('ingresso').distinct().order_by('ingresso')
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
            return queryset.filter(matricula__status='A')
        return queryset


class OrientadorInline(admin.TabularInline):
    model = Orientacao
    fields = ('orientador', 'coorientacao', 'status',)
    extra = 0


class AlunoAdmin(PowerModelAdmin):
    search_fields = ('nome',)
    list_filter = (AnoFilter, EgressoFilter, BolsaFilter,)
    list_display = ('nome', 'email', 'situacao', 'turma', 'status_matricula', 'orientador',)
    list_report = ('nome:400px:left', 'email:200px', 'turma', 'status_matricula:100px')
    fields = (
        'nome', 'email', 'email_alternativo', 'CPF', ('sexo', 'raca', 'situacao'), ('id_lattes', 'id_cnpq', 'id_funcional'),)
    inlines = (MatriculaInline, OrientadorInline)
    readonly_fields = []

    def get_form(self, request, obj=None, **kwargs):
        form = super(AlunoAdmin, self).get_form(request, obj, **kwargs)
        try:
            form.base_fields['nome'].widget.attrs['style'] = 'width: 50em;'
            form.base_fields['email'].widget.attrs['style'] = 'width: 30em;'
            form.base_fields['CPF'].widget.attrs['style'] = 'width: 10em;'
            form.base_fields['id_lattes'].widget.attrs['style'] = 'width: 10em;'

        except:
            None

        return form

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

    def get_buttons(self, request, object_id):
        buttons = super(AlunoAdmin, self).get_buttons(request, object_id)
        if object_id:
            aluno = Aluno.objects.get(id=object_id)
            url = aluno.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes'))
        return buttons


class OrientandosInline(admin.TabularInline):
    model = Orientacao
    fields = ('aluno', 'turma', 'coorientacao', 'status',)
    raw_id_fields = ('aluno',)
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


class ProfessorAdmin(PowerModelAdmin):
    search_fields = ('nome',)
    list_filter = (ProgramaFilter, ProfessorAtivoFilter,)
    list_display = ('nome', 'email', 'num_orientandos', 'num_projetos', 'status_lattes', 'atualizado')
    fields = ('nome', 'email', 'CPF', 'sexo', 'situacao', ('id_lattes', 'id_cnpq',),
              'num_projetos', 'num_orientandos_concluidos', ('dtupdate', 'atualizado'),)
    readonly_fields = ('dtupdate', 'atualizado', 'num_orientandos_concluidos', 'num_projetos')
    inlines = (LinhaProfessorInline, OrientandosInline)
    actions = ('verifica_lattes',)
    form = PesquisadorForm

    def get_buttons(self, request, object_id):
        buttons = super(ProfessorAdmin, self).get_buttons(request, object_id)
        if object_id:
            professor = Professor.objects.get(id=object_id)
            url = professor.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes'))
            if professor.id_cnpq:
                buttons.append(PowerButton(url=url_cnpq % professor.id_cnpq, label='CNPQ'))
            if professor.pesquisadorprojeto_set.count() > 0:
                buttons.append(
                    PowerButton(url='/producao_projeto/%s' % professor.id_lattes, label='Produção x Projetos'))

            buttons.append(
                PowerButton(url='/admin/nucleo/producao/?pesquisador=%s' % object_id, label='Produções',
                            attr={'target': '_blank'})
            )

        return buttons

    def verifica_lattes(self, request, queryset):
        tot_reg = 0
        for reg in queryset:
            dt_cnpq = obtem_dt_cnpq(url_cnpq % reg.id_cnpq)
            if dt_cnpq > reg.dtupdate:
                reg.atualizado = False
                reg.save()
                tot_reg += 1
        messages.info(request, u'%d pesquisadores atualizaram o currículo')
        return


class MatriculaAdmin(PowerModelAdmin):
    search_fields = ('pesquisador__nome', 'pesquisador__email',)
    list_filter = ('curso', 'ingresso', 'status', 'status_bolsa')
    list_csv = ('pesquisador', 'pesquisador_email', 'curso', 'status', 'dtquali', 'dtdefesa',)
    list_display = ('pesquisador', 'curso', 'ingresso', 'status', 'status_bolsa',
                    'dtquali', 'dtdefesa', 'trancamento', 'dtconclusao',)
    fields = ('pesquisador', ('curso', 'ingresso', 'status_bolsa', 'status',),
              ('dtquali', 'dtaprovacao', 'dtdefesa', 'dtconclusao'),
              ('trancamento', 'meses_previstos',),
              'titulo', 'obs',
              )

    def get_buttons(self, request, object_id):
        buttons = super(MatriculaAdmin, self).get_buttons(request, object_id)
        if object_id:
            matricula = Matricula.objects.get(id=object_id)
            buttons.append(
                PowerButton(url=reverse('admin:nucleo_aluno_change',
                                        args=(matricula.pesquisador.id,)), label=u'Aluno'))
        return buttons


class ProgramaInline(admin.TabularInline):
    model = PesquisadorPrograma
    fields = ('programa',)
    extra = 0
    form = PesquisadorProgramaForm


class PesquisadorAdmin(PowerModelAdmin):
    search_fields = ('nome', 'id_cnpq')
    list_display = ('nome', 'email',)
    fields = ('nome', 'email', 'sexo', 'raca', 'situacao', 'id_lattes', 'id_cnpq', 'orcid', 'dtupdate')
    readonly_fields = ('dtupdate',)
    inlines = (ProgramaInline,)
    form = PesquisadorForm

    def get_buttons(self, request, object_id):
        buttons = super(PesquisadorAdmin, self).get_buttons(request, object_id)
        if object_id:
            pesquisador = Pesquisador.objects.get(id=object_id)
            url = pesquisador.url_lattes()
            if url:
                buttons.append(
                    PowerButton(url=url, label='Lattes'))
            if pesquisador.orcid:
                buttons.append(
                    PowerButton(url=f'http://orcid.org/{pesquisador.orcid}', label='ORCID'))

            if pesquisador.id_cnpq:
                buttons.append(
                    PowerButton(url=url_cnpq % pesquisador.id_cnpq, label='CNPQ'))
            buttons.append(
                PowerButton(url='/admin/nucleo/producao/?q2=%s' % pesquisador.nome.replace(' ', '+'),
                            label=u'Produção'))
        return buttons


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


class ProducaoAdmin(PowerModelAdmin):
    multi_search = (
        ('q1', 'Titulo', ['titulo']),
        ('q2', 'Pesquisador', ['pesquisador__nome'])
    )
    inlines = (AutoresInline,)
    list_filter = ('ano', 'tipo', 'pais',)
    list_display = ('titulo', 'pesquisador', 'tipo', 'ano', 'qualis',)
    list_csv = ('titulo', 'pesquisador', 'tipo', 'ano',)
    raw_id_fields = ('periodico', 'projeto')
    list_per_page = 50

    fields = ('tipo', 'titulo', 'descricao', ('doi', 'isbn', 'pais', 'idioma'),
              ('periodico', 'ano', 'volume', 'serie'), ('projeto', 'sem_projeto', 'conta_sucupira'), 'ident_unico',
              )

    def get_buttons(self, request, object_id):
        buttons = super(ProducaoAdmin, self).get_buttons(request, object_id)
        if object_id:
            producao = Producao.objects.get(id=object_id)

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
    list_filter = ('producao__ano', 'producao__tipo', 'producao__periodico__qualis')
    list_display = ('autor_link', 'producao_link', 'qualis', 'ano',)
    readonly_fields = ('autor', 'producao', 'nome', 'ordem',)

    def lookup_allowed(self, lookup, value):
        if lookup == 'producao__periodico__qualis':            return True
        return super(ProducaoAutorAdmin, self).lookup_allowed(lookup, value)

    def get_buttons(self, request, object_id):
        buttons = super(ProducaoAutorAdmin, self).get_buttons(request, object_id)
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
    list_display = ('ano', 'total_pesquisadores', 'total_em_edicao', 'total_aguardando', 'total_avaliados')
    readonly_fields = ('total_pesquisadores', 'total_em_edicao', 'total_aguardando', 'total_avaliados')

    def get_buttons(self, request, object_id):
        buttons = super(ResumoAnualAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/convite_alunos/%s' % object_id, label='Enviar convites'))

        return buttons


class RelatorioAnualAdmin(PowerModelAdmin):
    list_display = ('pesquisador', 'status')
    list_filter = ('ano',)


admin.site.register(Instituicao, InstituicaoAdmin)
admin.site.register(Programa, ProgramaAdmin)
admin.site.register(LinhaPesquisa, LinhaPesquisaAdmin)
admin.site.register(ProjetoPesquisa, ProjetoPesquisaAdmin)
admin.site.register(Curso, CursoAdmin)
admin.site.register(Fomento, FomentoAdmin)

admin.site.register(Aluno, AlunoAdmin)
admin.site.register(Professor, ProfessorAdmin)
admin.site.register(Pesquisador, PesquisadorAdmin)
admin.site.register(Matricula, MatriculaAdmin)

admin.site.register(TipoProducao)
admin.site.register(Producao, ProducaoAdmin)
admin.site.register(ProducaoAutor, ProducaoAutorAdmin)

admin.site.register(ResumoAnual, ResumoAnualAdmin)
admin.site.register(RelatorioAnual, RelatorioAnualAdmin)
