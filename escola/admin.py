import re

from ckeditor.widgets import CKEditorWidget
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.utils import flatten_fieldsets
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django_select2 import forms as s2forms
from poweradmin.admin import PowerModelAdmin, PowerTabularInline, PowerButton, PowerStackedInline

from nucleo.apps import log_object, URL_CNPQ
from nucleo.forms import PesquisadorForm
from nucleo.models import Pesquisador
from nucleo.models import PesquisadorInstituicao
from utils.admin_mixins import WidgetCustomAdminMixin
from utils.email import sendmail
from .forms import DocenteAddForm, ListaInteresseForm
from .interfaces import registro_moodle

from .management.commands.gera_certificados import processa_inscricao_unica
from .models import (Comunicado, Contato, Curso, CursoDocente, CursoFormal, Discente, Docente, Inscricao, ListaContato,
                     ListaInteresse, ModeloCertificado, Modulo, ModuloSessao, ModuloTrilha, PalavraChave, TipoCurso, )

LISTA_INTERESSE_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')


@admin.register(TipoCurso)
class TipoCursoAdmin(PowerModelAdmin):
    list_display = ('descricao',)


@admin.register(ModeloCertificado)
class ModeloCertificadoAdmin(PowerModelAdmin):
    list_display = ('descricao', 'font_name')


@admin.register(PalavraChave)
class PalavraChaveAdmin(PowerModelAdmin):
    list_display = ('termo', 'contador')


class ModuloCursosInline(PowerTabularInline):
    model = Curso
    fields = ('nome', 'tipo', 'cod_externo', 'dt_inicio', 'num_max_alunos', 'edit_link')
    readonly_fields = ('edit_link',)
    ordering = ('cod_externo',)


@admin.register(Modulo)
class ModuloAdmin(PowerModelAdmin):
    list_display = ('nome', 'dt_inicio', 'slug')
    inlines = (ModuloCursosInline,)

    def get_buttons(self, request, object_id=None):
        buttons = super().get_buttons(request, object_id)
        if object_id:
            modulo = self.get_object(request, object_id)
            buttons.append(
                PowerButton(url=reverse('modulo_dash_resultados', args=(object_id,)),
                            label='Painel de Resultados')
            )
            buttons.append(
                PowerButton(url=reverse('modulo_exportacao_csv', args=(object_id,)),
                            label='Exportação CSV'))
            if modulo.slug:
                buttons.append(PowerButton(url=modulo.url(), label='Visualizar'))

            if modulo.url_tema:
                buttons.append(
                    PowerButton(url=reverse('execute_deploy_tema'), label='Atualiza Tema'))

        return buttons


class SessaoInlineForm(forms.ModelForm):
    class Meta:
        widgets = {
            'sessao': CKEditorWidget(),
            'trabalhos': CKEditorWidget()
        }


class ModuloSessaoInline(PowerStackedInline):
    model = ModuloSessao
    fields = ('dia', 'titulo', 'sessao', 'hora_inicial', 'hora_final', 'trabalhos')
    extra = 0
    form = SessaoInlineForm


@admin.register(ModuloTrilha)
class ModuloTrilhaAdmin(PowerModelAdmin):
    list_filter = ('modulo',)
    list_display = ('modulo', 'nome', 'descricao',)
    inlines = (ModuloSessaoInline,)
    actions = ['estatisticas', 'planilha']

    @admin.action(description="Estatísticas")
    def estatisticas(self, request, queryset):
        modulo_ids = queryset.values_list('id', flat=True).distinct()
        query_params = '&'.join([f"trilha={id}" for id in modulo_ids])
        url = reverse('modulo_dash_checkin') + '?' + query_params
        return redirect(url)

    @admin.action(description="Planilha das Sessões")
    def planilha(self, request, queryset):
        modulo_ids = queryset.values_list('id', flat=True).distinct()
        query_params = '&'.join([f"trilha={id}" for id in modulo_ids])
        url = reverse('trilha_planilha') + '?' + query_params
        return redirect(url)

    def get_buttons(self, request, object_id=None):
        buttons = super().get_buttons(request, object_id)
        if object_id:
            trilha = self.get_object(request, object_id)
            buttons.append(
                PowerButton(url=f"{reverse('importacao_sessoes')}?modulo={trilha.modulo.id}",
                            label='Importação')
            )
        return buttons


class CursoDocenteInline(PowerTabularInline):
    model = CursoDocente
    fields = ('docente', 'ordem')
    autocomplete_fields = ('docente',)
    extra = 0


@admin.register(CursoFormal)
class CursoFormalAdmin(PowerModelAdmin):
    list_display = ('nome', 'cod_externo', 'dt_inicio', 'lista_docentes',
                    'status', 'tot_alunos',)
    multi_search = (
        ('q1', 'Curso', ['nome']),
        ('q2', 'Docente', ['cursodocente__docente__nome']),
    )
    fields = ('nome', 'tipo', ('modulo', 'cod_externo'), ('dt_inicio', 'online', 'duracao', 'num_aulas'),
              'ementa', 'imagem', 'banner',
              ('dt_matricula', 'dt_fim_matricula', 'num_max_alunos'),
              ('status', 'dt_limite_presenca', 'envio_certificado'),)
    readonly_fields = ('envio_certificado',)
    inlines = (CursoDocenteInline,)

    def get_buttons(self, request, object_id=None):
        buttons = super(CursoFormalAdmin, self).get_buttons(request, object_id)
        if object_id:
            curso = self.get_object(request, object_id)
            buttons.append(
                PowerButton(url=f'/admin/escola/inscricao/?curso={curso.id}', label="Inscrições"))

            if curso.modulo:
                buttons.append(
                    PowerButton(url=reverse('admin:escola_modulo_change', args=(curso.modulo.id,)), label="Módulo"))

            if curso.dt_limite_presenca:
                buttons.append(
                    PowerButton(url=f'/qrcode/{object_id}', label="Link para Presença"))

            if ((curso.status == Curso.Status.FINALIZADO and curso.envio_certificado == 'N') or
                    request.user.is_superuser):
                buttons.append(
                    PowerButton(url='/agenda_certificado/%d' % object_id, label='Envia Certificados'))

        return buttons


@admin.register(Curso)
class CursoAdmin(WidgetCustomAdminMixin, PowerModelAdmin):
    list_display = ('nome', 'cod_externo', 'dt_inicio', 'lista_docentes',
                    'status', 'tot_alunos', 'tot_alunos_fila', 'slug')
    list_filter = ('status', 'envio_certificado', 'modulo__nome', 'online')
    multi_search = (
        ('q1', 'Curso', ['nome', 'slug']),
        ('q2', 'Docente', ['cursodocente__docente__nome']),
    )
    fields = ('nome', 'tipo', ('modulo', 'cod_externo'), ('dt_inicio', 'online', 'duracao', 'num_aulas'),
              'ementa', 'programacao', 'imagem', 'banner', 'espelho_pdf', 'moodle_id',
              ('dt_matricula', 'dt_fim_matricula', 'num_max_alunos'),
              ('certificado', 'modelo',),
              ('status', 'dt_limite_presenca', 'envio_certificado'),)
    search_fields = ('nome',)
    readonly_fields = ('envio_certificado',)
    inlines = (CursoDocenteInline,)
    list_per_page = 10
    field_styles = {
        'nome': 'width: 80em;',
    }
    field_widgets = {
        'modulo': s2forms.ModelSelect2Widget(
            model=Pesquisador,
            search_fields=['nome__icontains'],
            attrs={'data-minimum-input-length': 3}
        ),
    }

    @admin.display(description='Alunos Matriculados')
    def tot_alunos(self, obj):
        return obj.inscricao_set.filter(status=Inscricao.Status.ATIVA).count()

    @admin.display(description='Fila de Espera')
    def tot_alunos_fila(self, obj):
        return obj.inscricao_set.filter(status=Inscricao.Status.LISTA_ESPERA).count()

    def get_buttons(self, request, object_id=None):
        buttons = super(CursoAdmin, self).get_buttons(request, object_id)
        if object_id:
            curso = self.get_object(request, object_id)

            buttons.append(
                PowerButton(url=curso.external_url(), label="Visualizar no site"))

            buttons.append(
                PowerButton(url=f'/admin/escola/inscricao/?curso={curso.id}', label="Inscrições"))

            if curso.modulo:
                buttons.append(
                    PowerButton(url=reverse('admin:escola_modulo_change', args=(curso.modulo.id,)), label="Módulo"))

            if curso.dt_limite_presenca:
                buttons.append(
                    PowerButton(url=f'/qrcode/{object_id}', label="Link para Presença"))
            else:
                if curso.status == Curso.Status.ATIVO:
                    self.message_user(request,
                                      'A data limite para a confirmação da presença deve estar preechida',
                                      messages.WARNING)

            if ((curso.status == Curso.Status.FINALIZADO and curso.envio_certificado == 'N') or
                    request.user.is_superuser):
                buttons.append(
                    PowerButton(url='/agenda_certificado/%d' % object_id, label='Envia Certificados'))
        return buttons

    def save_model(self, request, obj, form, change):
        if obj.num_max_alunos == 0 and not obj.tipo.evento:
            self.message_user(request,
                              'O número máximo de alunos não foi especificado. Sem isso o curso aceitará qualquer número de alunos',
                              messages.WARNING)

        return super().save_model(request, obj, form, change)


class InscricaoInline(PowerTabularInline):
    model = Inscricao
    fields = ('curso', 'dt_inscricao', 'status', 'presenca')
    extra = 0
    readonly_fields = ('curso', 'dt_inscricao',)


@admin.register(Discente)
class DiscenteAdmin(PowerModelAdmin):
    search_fields = ('nome', 'email', 'cpf')
    list_display = ('email', 'nome', 'cpf', 'validado',)
    list_filter = ('validado',)
    inlines = [InscricaoInline, ]

    def get_buttons(self, request, object_id=None):
        buttons = super().get_buttons(request, object_id)
        if object_id:
            discente = self.get_object(request, object_id)
            if discente.contato:
                hash_key = discente.contato.hash_key()
                buttons.append(
                    PowerButton(url=reverse('cadastra_discente', args=[hash_key, ]),
                                label='URL Externa'))
        return buttons


@admin.register(Inscricao)
class InscricaoAdmin(PowerModelAdmin):
    list_filter = ('status', 'presenca')
    list_display = ('curso', 'discente_nome', 'dt_inscricao', 'status', 'presenca')
    multi_search = (('q1', 'Discente', ['discente__nome', 'discente__email']),
                    ('q2', 'Curso/Módulo', ['curso__nome', 'curso__modulo__nome']))
    actions = ["marcar_presenca", "reenvia_verificacao", "enviar_certificado", "marcar_confirmacao", "inscricao_moodle"]
    raw_id_fields = ('curso', 'discente')
    readonly_fields = ('hash_certificado',)
    list_select_related = ('curso', 'discente',)
    list_csv = ('curso__nome', 'discente__nome', 'discente__email', 'discente__cpf', 'discente__telefone',
                'status', 'presenca_str')
    list_report = ('discente__nome', 'discente__email',)
    list_per_page = 30

    @admin.action(description="Marcar presença")
    def marcar_presenca(self, request, queryset):
        result = queryset.update(presenca=True)
        if result > 0:
            self.message_user(request, f'{result} inscrições atualizadas')

    @admin.action(description="Inscrição no Moodle")
    def inscricao_moodle(self, request, queryset):
        tot_criados = 0
        tot_lidos = 0
        tot_invalidos = 0
        for obj in queryset:
            discente = obj.discente
            tot_lidos += 1
            if obj.curso.moodle_id and not obj.inscrito_curso_moodle:
                try:
                    registro_moodle(obj)
                    tot_criados += 1

                except Exception as e:
                    self.log_change(request, obj, f'Erro na inscrição do moodle: {e}')

                    tot_invalidos += 1
            else:
                tot_invalidos += 1
        if tot_invalidos == tot_lidos:
            self.message_user(request, f'Nenhuma inscrição com moodle habilitado')
        if tot_criados > 0:
            self.message_user(request, f'{tot_criados} inscrições criadas')

    @admin.action(description="Reenvia email de Verificação")
    def reenvia_verificacao(self, request, queryset):
        tot_registros = 0
        for inscricao in queryset.filter(status__in=(Inscricao.Status.ABERTO, Inscricao.Status.LISTA_ESPERA)):
            inscricao.send_email_verificacao()
            tot_registros += 1
        self.message_user(request, f'{tot_registros} confirmações enviadas')

    @admin.action(description="Confirma inscrição")
    def marcar_confirmacao(self, request, queryset):
        tot_registros = 0
        for inscricao in queryset.filter(status__in=(Inscricao.Status.ABERTO, Inscricao.Status.LISTA_ESPERA)):
            inscricao.status = Inscricao.Status.ATIVA
            inscricao.save()
            inscricao.email_confirmacao()
            tot_registros += 1
        self.message_user(request, f'{tot_registros} inscrições confirmadas')

    @admin.display(description='Presença')
    def presenca_str(self, obj):
        return 'Sim' if obj.presenca else 'Não'

    @admin.display(description='Nome do Discente', ordering='discente__nome')
    def discente_nome(self, obj):
        return obj.discente.nome

    @admin.action(description="Enviar Certificado")
    def enviar_certificado(self, request, queryset):
        result = 0
        if queryset.count() > 5:
            self.message_user(request, f'Esta rotina não deve ser utilizada para muitos casos')
        try:
            for inscricao in queryset.all():
                processa_inscricao_unica(inscricao)
                result += 1
            self.message_user(request, f'{result} certificados enviados')
        except ValueError as e:
            self.message_user(request, f'{e}', level=messages.ERROR)


class CursosInline(PowerTabularInline):
    model = CursoDocente
    readonly_fields = ('curso', 'ordem')
    extra = 0


@admin.register(Docente)
class DocenteAdmin(PowerModelAdmin):
    search_fields = ('nome',)
    list_display = ('nome', 'email', 'num_cursos',)
    fields = ('nome', 'email', 'sexo', 'situacao', 'id_cnpq', 'orcid', 'mini_bio', 'fotografia')
    list_csv = ('nome', 'email', 'sexo', 'id_cnpq', 'orcid',)
    inlines = (CursosInline,)
    actions = ('verifica_lattes',)
    form = PesquisadorForm
    add_form = DocenteAddForm

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("nome", "orcid"),
            },
        ),
    )

    def get_buttons(self, request, object_id=None):
        buttons = super(DocenteAdmin, self).get_buttons(request, object_id)
        if object_id:
            professor = Docente.objects.get(id=object_id)
            url = professor.url_lattes()
            if url:
                buttons.append(PowerButton(url=url, label='Lattes'))
            if professor.id_cnpq:
                buttons.append(PowerButton(url=URL_CNPQ % professor.id_cnpq, label='CNPQ'))
        return buttons

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_deleted_objects(self, objs, request):
        return [], {}, set(), []

    def delete_model(self, request, obj):
        PesquisadorInstituicao.objects.get(
            instituicao=settings.ESCOLA, pesquisador=obj).delete()
        log_object(obj, f'Professor removido da instituição')

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form during creation
        """
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_inlines(self, request, obj):
        if obj is None:
            return []
        return super().get_inlines(request, obj)

    def add_view(self, request, form_url='', extra_context=None):
        if request.method == 'POST':
            if not self.has_add_permission(request):
                raise PermissionDenied

            fieldsets = self.get_fieldsets(request, None)
            ModelForm = self.get_form(
                request, None, change=False, fields=flatten_fieldsets(fieldsets)
            )

            form = ModelForm(request.POST, request.FILES, instance=None)
            form_validated = form.is_valid()
            if form_validated:
                obj = self.save_form(request, form, change=False)
                if obj.orcid:
                    pesq_by_orcid = Pesquisador.objects.filter(
                        orcid=obj.orcid).values('id').last()

                    if pesq_by_orcid:
                        PesquisadorInstituicao.objects.get_or_create(
                            instituicao_id=settings.ESCOLA, pesquisador_id=pesq_by_orcid['id'])
                        return redirect(reverse('admin:escola_docente_change', args=[pesq_by_orcid['id']]))

                pesq_by_name = Pesquisador.objects.filter(
                    nome=obj.nome).values('id').last()
                if pesq_by_name:
                    PesquisadorInstituicao.objects.get_or_create(
                        instituicao_id=settings.ESCOLA, pesquisador_id=pesq_by_name['id'])

                    return redirect(reverse('admin:escola_docente_change', args=[pesq_by_name['id']]))

        return super().add_view(request, form_url, extra_context)


@admin.register(Contato)
class ContatoAdmin(PowerModelAdmin):
    search_fields = ('email', 'nome', 'origem',)
    list_display = ('email', 'nome', 'origem', 'utm_source', 'dtcontato')
    list_select_related = ('curso_origem',)
    readonly_fields = ('curso_origem',)

    @admin.display(description='Curso', ordering='curso_origem__name')
    def curso_nome(self, obj):
        return obj.curso_origem.nome


class ComunicadoForm(forms.ModelForm):
    class Meta:
        widgets = {
            'titulo': forms.TextInput(attrs={'width': 100}),
        }


@admin.register(Comunicado)
class ComunicadoAdmin(PowerModelAdmin):
    list_display = ('tipo', 'titulo', 'dt_criacao', 'status')
    form = ComunicadoForm
    fields = ('tipo', 'email_teste', 'modulo', 'curso', 'lista', 'titulo', 'texto', 'dt_criacao', 'status')
    readonly_fields = ('dt_criacao', 'status',)
    autocomplete_fields = ('curso', 'lista',)

    def get_buttons(self, request, object_id=None):
        buttons = super(ComunicadoAdmin, self).get_buttons(request, object_id)
        if object_id:
            comunicado = self.get_object(request, object_id)
            if comunicado:
                buttons.append(
                    PowerButton(url=f'/agenda_comunicado/{object_id}', label="Envia comunicado"))
        return buttons


@admin.register(ListaInteresse)
class ListaInteresseAdmin(PowerModelAdmin):
    form = ListaInteresseForm
    list_display = ('titulo', 'tot_contatos',)
    fields = ('titulo', 'descricao', 'emails', 'modelo', 'arquivo', 'tot_contatos',)
    readonly_fields = ('tot_contatos',)
    search_fields = ('titulo',)

    @admin.display(description='Contatos')
    def tot_contatos(self, obj):
        total = obj.listacontato_set.count()

        if not total:
            return '0'

        lista_contato_changelist = f'{reverse("admin:escola_listacontato_changelist")}?lista__pk={obj.pk}'

        return mark_safe(f'<a href="{lista_contato_changelist}" target="_blank" rel="noopener noreferrer">{total}</a>')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        texto = form.cleaned_data.get('emails')
        if texto:
            criados, vinculados = self._processar_emails(obj, texto)
            messages.info(request, f'{criados} contato(s) criado(s), {vinculados} vinculado(s) à lista.')

    def _processar_emails(self, lista, texto):
        criados = vinculados = 0
        for entrada in texto.split(','):
            entrada = entrada.strip()
            if not entrada:
                continue
            achado = LISTA_INTERESSE_EMAIL_RE.search(entrada)
            if not achado:
                continue
            email = achado.group(0)
            nome = entrada.replace(email, '').strip(' <>') or email.split('@')[0]
            contato, criado = Contato.objects.get_or_create(
                email=email.lower(), defaults={'nome': nome, 'origem': 'Lista'}
            )
            if criado:
                criados += 1
            if not lista.listacontato_set.filter(contato=contato).exists():
                lista.listacontato_set.create(contato=contato)
                vinculados += 1
        return criados, vinculados

    def get_buttons(self, request, object_id=None):
        buttons = super(ListaInteresseAdmin, self).get_buttons(request, object_id)
        if object_id:
            lista_contato_change_list = f'{reverse("admin:escola_listacontato_changelist")}?lista__pk={object_id}'
            buttons.append(PowerButton(url=lista_contato_change_list, label='Ver Contatos'))
            lista = self.get_object(request, object_id)
            if lista and lista.arquivo:
                buttons.append(PowerButton(url='/agenda_certificado_lista/%d' % object_id, label='Envia Certificados'))
        return buttons


@admin.register(ListaContato)
class ListaContatoAdmin(PowerModelAdmin):
    list_display = ('contato_nome', 'lista',)
    list_select_related = ('contato', 'lista')
    multi_search = (
        ('q1', 'Contato', ['contato__nome']),
        ('q2', 'Lista', ['lista__titulo']),
    )

    @admin.display(description='Nome do Contato', ordering='contato__nome')
    def contato_nome(self, obj):
        return obj.contato.nome
