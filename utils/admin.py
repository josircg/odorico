# -*- coding: utf-8 -*-
from django.contrib import admin
from django.contrib.admin.models import LogEntry

from poweradmin.admin import PowerModelAdmin

from .models import EmailAgendado, TipoProcessamento


class EmailAgendadoAdmin(PowerModelAdmin):
    list_display = ('subject', 'to', 'status', 'date')
    list_filter = ('status', 'date', )
    multi_search = (
        ('q1', u'Subject', ['subject']),
        ('q2', u'To', ['to']),
    )
    fieldsets = (
        (None, {'fields': ('subject', 'to', 'status', 'date', )}),
        (None, {'fields': ('html', )}),
    )
    readonly_fields = ('subject', 'to', 'status', 'date')
    actions = ('renviar', )

    def renviar(self, request, queryset):
        for q in queryset:
            q.send()


class TipoProcessamentoAdmin(PowerModelAdmin):
    list_display = ('tipo', )


class LogEntryAdmin(PowerModelAdmin):
    list_filter = ('action_time', 'content_type', 'action_flag',)
    list_display = ('action_time', 'user', 'content_type', 'tipo', 'object_repr', 'change_message', )
    fields = ('action_time', 'user', 'content_type', 'object_id', 'object_repr', 'action_flag', 'tipo',
              'change_message', )
    readonly_fields = ('action_time', 'user', 'content_type', 'object_id', 'object_repr', 'action_flag', 'tipo',
                       'change_message', )
    multi_search = (
        ('q1', u'Repr. do Objeto', ['object_repr', ]),
        ('q2', u'Mensagem', ['change_message', ]),
        ('q3', u'User', ['user__username', ]),
    )

    def tipo(self, obj):
        if obj.is_addition():
            return u"1-Adicionado"
        elif obj.is_change():
            return u"2-Modificado"
        elif obj.is_deletion():
            return u"3-Deletado"


admin.site.register(LogEntry, LogEntryAdmin)
admin.site.register(EmailAgendado, EmailAgendadoAdmin)
admin.site.register(TipoProcessamento, TipoProcessamentoAdmin)
