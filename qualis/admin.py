from django.contrib import admin, messages
from django.http import JsonResponse
from django.utils.translation import ungettext

from .models import *

from poweradmin.admin import PowerModelAdmin, PowerButton


class SchemaAdmin(PowerModelAdmin):
    model = Schema
    search_fields = ('descricao', 'sigla')
    list_display = ('descricao', 'sigla', 'ano_inicial', 'tot_classes')
    actions = ['equalizar_assuntos', 'exportacao_json']

    @admin.action(description='Exportar JSON')
    def exportacao_json(self, request, queryset):
        result = []
        for obj in queryset:
            schema = {"descricao": obj.descricao, "sigla": obj.sigla, "nota": obj.nota, 'assuntos': []}
            for item in obj.assunto_set.all().order_by('id'):
                assunto = {"descricao": item.descricao, "cod_externo": item.cod_externo}
                if item.parent:
                    assunto["parent_cod"] = item.parent.cod_externo
                    assunto['parent_schema'] = item.parent.schema.sigla
                schema['assuntos'].append(assunto)
            result.append(schema)
        return JsonResponse(result, safe=False)

    @admin.action(description='Equalizar assuntos')
    def equalizar_assuntos(self, request, queryset):
        count = queryset.count()

        if count != 2:
            self.message_user(request, 'Selecione dois esquemas de classificação', messages.ERROR)
        else:
            schema_1 = queryset[0]
            schema_2 = queryset[1]

            if schema_1.assunto_set.count() > schema_2.assunto_set.count():
                count = self._copiar_assuntos(schema_1, schema_2)
            elif schema_1.assunto_set.count() < schema_2.assunto_set.count():
                count = self._copiar_assuntos(schema_2, schema_1)
            else:
                count = 0

            msg = ungettext('{0} assunto equalizado.', '{0} assuntos equalizados.', count)

            self.message_user(request, msg.format(count))

    @staticmethod
    def _copiar_assuntos(origem, destino):
        count = 0

        for assunto in origem.assunto_set.exclude(cod_externo__in=destino.assunto_set.values_list('cod_externo')):
            destino.assunto_set.create(descricao=assunto.descricao, parent=assunto.parent)
            count += 1

        return count



class AssuntoChild(admin.TabularInline):
    model = Assunto
    fields = ('cod_externo', 'descricao',)
    fk_name = 'parent'
    extra = 0


class AssuntoAdmin(PowerModelAdmin):
    model = Assunto
    search_fields = ('descricao', 'cod_externo',)
    list_filter = ('schema',)
    list_display = ('descricao', 'schema', 'cod_externo', 'tot_periodicos')
    raw_id_fields = ('parent',)
    inlines = (AssuntoChild,)

    def get_buttons(self, request, object_id=None):
        buttons = super(AssuntoAdmin, self).get_buttons(request, object_id)
        if object_id:
            assunto = Assunto.objects.get(id=object_id)
            if assunto.parent:
                buttons.append(
                    PowerButton(url='/admin/qualis/assunto/%d/change/' % assunto.parent_id, label='Nível superior',
                                attrs={'target': '_blank'})
                )
        return buttons


class AreaAdmin(PowerModelAdmin):
    list_display = ('nome', 'tot_periodicos', )


class PeriodicoIndicadorInline(admin.TabularInline):
    model = PeriodicoIndicador
    extra = 0


class PeriodicoAssuntoInline(admin.TabularInline):
    model = PeriodicoAssunto
    extra = 0

class ISSNInline(admin.TabularInline):
    model = PeriodicoISSN
    extra = 0

class PeriodicoAdmin(PowerModelAdmin):
    list_filter = ('area', 'qualis',)
    search_fields = ('nome', 'issn', 'eissn', 'scopus_code')
    list_display = ('nome', 'issn', 'eissn', 'area', 'oalex_h5', 'qualis', 'status')
    inlines = (PeriodicoIndicadorInline, PeriodicoAssuntoInline, ISSNInline)
    list_csv = [f.name for f in Periodico._meta.concrete_fields]

    def get_buttons(self, request, object_id=None):
        buttons = super(PeriodicoAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/admin/nucleo/producao/?periodico=%s' % object_id, label='Publicações',
                            attrs={'target': '_blank'})
            )

            periodico = Periodico.objects.get(id=object_id)
            if periodico.scopus_code:
                buttons.append(
                    PowerButton(url='https://www.scopus.com/sourceid/%s' % periodico.scopus_code,
                                label='Scopus', attrs={'target': '_blank'})
                )

            if periodico.oalex_code:
                buttons.append(
                    PowerButton(url=f'https://openalex.org/sources/{periodico.oalex_code}',
                                label='OpenAlex', attrs={'target': '_blank'})
                )

            if periodico.google_code:
                code = periodico.google_code.split('.')[0]
                buttons.append(
                    PowerButton(url=f'https://scholar.google.com/citations?hl=pt-BR&vq=en&view_op=list_hcore&venue={code}.2023',
                                label='Google', attrs={'target': '_blank'})
                )

        return buttons


class PeriodicoISSNAdmin(PowerModelAdmin):
    list_display = ('issn', 'periodico', 'meio', 'valido',)
    search_fields = ('issn', 'periodico__nome',)
    list_filter = ('meio', 'valido',)
    autocomplete_fields = ('periodico',)


class PaisAdmin(PowerModelAdmin):
    list_display = ('iso2', 'iso3', 'nome', 'name', 'tld')
    search_fields = ('nome', 'name', 'nombre')


admin.site.register(Schema, SchemaAdmin)
admin.site.register(Assunto, AssuntoAdmin)
admin.site.register(AreaConhecimento, AreaAdmin)
admin.site.register(Pais, PaisAdmin)
admin.site.register(Periodico, PeriodicoAdmin)
admin.site.register(PeriodicoISSN, PeriodicoISSNAdmin)
