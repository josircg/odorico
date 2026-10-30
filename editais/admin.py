from django.contrib import admin
from django.contrib.contenttypes.admin import GenericStackedInline

from poweradmin.admin import PowerModelAdmin, PowerButton, PowerTabularInline, PowerStackedInline

from nucleo.apps import URL_CNPQ
from nucleo.models import Documento, PesquisadorFormacao

from .models import Edital, EditalTipoDocumento, EditalVaga, Inscricao, TipoVaga


@admin.register(TipoVaga)
class TipoVagaAdmin(PowerModelAdmin):
    list_display = ('descricao', 'ativa')


class VagasInline(PowerTabularInline):
    model = EditalVaga
    fields = ('tipo_vaga', 'num_vagas', 'num_inscritos')
    readonly_fields = ('num_inscritos', )
    extra = 0

    @admin.display(description='Inscrições')
    def num_inscritos(self, instance):
        return instance.edital.inscricao_set.filter(tipo_vaga=instance).count()


class DocumentoInline(PowerTabularInline):
    model = EditalTipoDocumento
    fields = ('tipo', 'descricao', 'tipo_vaga', 'obrigatorio')
    extra = 0


@admin.register(Edital)
class EditalAdmin(PowerModelAdmin):
    list_filter = ('descricao',)
    list_display = ('descricao', 'dt_inicio', 'dt_fim', 'num_inscricoes', 'status')
    inlines = (VagasInline, DocumentoInline )

    @admin.display(description='Inscrições')
    def num_inscricoes(self, instance):
        return instance.num_inscricoes

    def get_buttons(self, request, object_id=None):
        buttons = super(EditalAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url=f'/nova_inscricao_edital/{object_id}',
                            label='Formulário'))
            buttons.append(
                PowerButton(url=f'/admin/editais/inscricao/?edital_id={object_id}',
                            label='Inscrições')),

        return buttons


class DocumentoInscricaoInline(GenericStackedInline):
    model = Documento
    fields = ('tipo', 'anexo')
    extra = 0


class FormacaoInline(PowerStackedInline):
    model = PesquisadorFormacao
    fields = ('nivel', 'curso', 'nome_instituicao', 'instituicao', 'ano_entrada', 'ano_conclusao')
    raw_id_fields = ('instituicao',)
    extra = 0


@admin.register(Inscricao)
class InscricaoAdmin(PowerModelAdmin):
    list_filter = ('edital__descricao', 'status', 'status_cnpq')
    list_display = ('nome', 'CPF', 'email', 'status', 'status_cnpq', 'numero')
    list_csv = ('edital__descricao', 'nome', 'CPF', 'email', 'id_cnpq', 'linha', 'numero', 'status', )
    autocomplete_fields = ('tema', 'candidato', )
    inlines = (DocumentoInscricaoInline, )

    def get_buttons(self, request, object_id=None):
        buttons = super(InscricaoAdmin, self).get_buttons(request, object_id)
        if object_id:
            inscricao = Inscricao.objects.filter(id=object_id).select_related('candidato').first()
            pesquisador = inscricao.candidato
            if pesquisador:
                url = pesquisador.url_lattes()
                if url:
                    buttons.append(PowerButton(url=url, label='Lattes', attrs={'target': '_blank'}))

                if pesquisador.id_cnpq:
                    buttons.append(
                        PowerButton(url=URL_CNPQ % pesquisador.id_cnpq, label='CNPQ', attrs={'target': '_blank'}))
                    buttons.append(
                        PowerButton(url=f'/edital_lattes/{inscricao.id}', label='Update Lattes',
                                    attrs={'target': '_blank'}))
                buttons.append(
                    PowerButton(url=f'/admin/nucleo/pesquisador/{pesquisador.id}',
                                label=u'Pesquisador', attrs={'target': '_blank'}))
        return buttons

