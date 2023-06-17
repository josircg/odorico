from django.contrib import admin

from .models import *

from poweradmin.admin import PowerModelAdmin, PowerButton


class SchemaAdmin(PowerModelAdmin):
    model = Schema
    list_display = ('descricao', 'sigla', 'tot_classes')


class AssuntoAdmin(PowerModelAdmin):
    model = Assunto
    search_fields = ('descricao', 'cod_externo',)
    list_filter = ('schema',)
    list_display = ('descricao', 'schema', 'cod_externo', 'tot_periodicos')


class AreaConhecimentoInline(admin.TabularInline):
    model = AreaConhecimento
    fields = ('nome',)
    extra = 1


class AreaAdmin(PowerModelAdmin):
    list_filter = ('grande_area',)
    list_display = ('nome', 'grande_area', 'cod_capes')
    inlines = (AreaConhecimentoInline,)


class AreaFilter(admin.SimpleListFilter):
    title = 'Area'
    parameter_name = 'area'
    default_value = None

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(AreaFilter, self).value()
        if value is None:
            if self.default_value is None:
                area = PeriodicoArea.objects.first()
                value = None if area is None else area.id
                self.default_value = value
            else:
                value = self.default_value
        return str(value)

    def value(self):
        """
        Overriding this method will allow us to always have a default value.
        """
        value = super(AreaFilter, self).value()
        if value is None:
            if self.default_value is None:
                programa = PeriodicoArea.objects.first()
                value = None if programa is None else programa.id
                self.default_value = value
            else:
                value = self.default_value
        return str(value)

    def lookups(self, request, model_admin):
        q = PeriodicoArea.objects.all().values('area', 'area__nome').distinct()
        programas = []
        for ano in q:
            programas.append((ano['area'], ano['area__nome']))
        return tuple(programas)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(pesquisaarea__area_id=value)
        else:
            return queryset.all()


class PeriodicoIndicadorInline(admin.TabularInline):
    model = PeriodicoIndicador
    extra = 0


class PeriodicoAssuntoInline(admin.TabularInline):
    model = PeriodicoAssunto
    extra = 0


class PeriodicoAdmin(PowerModelAdmin):
    list_filter = ('area', 'qualis', )
    search_fields = ('nome', 'issn', 'eissn', 'scopus_code')
    list_display = ('nome', 'issn', 'eissn', 'citescore', 'qualis', 'status')
    inlines = (PeriodicoIndicadorInline, PeriodicoAssuntoInline)
    list_csv = [f.name for f in Periodico._meta.concrete_fields]

    def get_buttons(self, request, object_id=None):
        buttons = super(PeriodicoAdmin, self).get_buttons(request, object_id)
        if object_id:
            buttons.append(
                PowerButton(url='/admin/nucleo/producao/?periodico=%s' % object_id, label='Publicações', attrs={'target': '_blank'})
            )

            periodico = Periodico.objects.get(id=object_id)
            if periodico.scopus_code:
                buttons.append(
                    PowerButton(url='https://www.scopus.com/sourceid/%s' % periodico.scopus_code,
                                label='Scopus', attrs={'target': '_blank'})
                )
        return buttons


admin.site.register(Schema, SchemaAdmin)
admin.site.register(Assunto, AssuntoAdmin)
admin.site.register(GrandeArea)
admin.site.register(Area, AreaAdmin)
admin.site.register(AreaConhecimento)
admin.site.register(Periodico, PeriodicoAdmin)
