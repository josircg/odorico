from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth import login, logout
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.conf.urls import url

from poweradmin.admin import PowerModelAdmin, PowerButton

from .models import EmailAgendado, TipoProcessamento, UserPerson


@admin.register(UserPerson)
class UserAdmin(PowerModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_active', )
    list_filter = ('is_active', 'groups', )
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)
    readonly_fields = ('username', 'password', 'first_name', 'last_name', 'email', 'is_active', 'groups', 'user_permissions', 'last_login', 'date_joined')

    fieldsets = (
        (u'Informações pessoais', {'fields': ('username', 'first_name', 'email', )}),
        (u'Permissões', {'fields': ('is_active', 'groups', 'user_permissions')}),
        (u'Datas importantes', {'fields': ('last_login', 'date_joined')}),
    )

    def get_queryset(self, request):
        if request.user.is_superuser:
            return super().get_queryset(request).all()
        else:
            return super().get_queryset(request).filter(is_superuser=False)

    def personificar(self, request, user_id):
        user = get_object_or_404(UserPerson, pk=user_id)
        if not (request.user.groups.filter(name='QA') or request.user.is_superuser):
            raise PermissionDenied()

        LogEntry.objects.log_action(
            user_id = request.user.pk,
            content_type_id = ContentType.objects.get_for_model(request.user).pk,
            object_id = request.user.pk,
            object_repr = u"%s" % request.user,
            action_flag = CHANGE,
            change_message = f'Usuário {request.user} personificou-se como {user.username}'
        )
        logout(request)
        user.backend='django.contrib.auth.backends.ModelBackend'
        login(request, user)
        messages.info(request, u'Você está logado agora como %s!' % user)
        return HttpResponseRedirect(reverse('login'))

    def get_urls(self):
        urls_originais = super(UserAdmin, self).get_urls()

        buttons_urls = [
            url(r'^personificar/(?P<user_id>\d+)/$', self.wrap(self.personificar),
                name='utils_userperson_personificar'),
        ]
        return buttons_urls + urls_originais

    def get_buttons(self, request, object_id=None):
        buttons = super(UserAdmin, self).get_buttons(request, object_id)
        if object_id and (request.user.groups.filter(name='QA') or request.user.is_superuser):
            obj = self.get_object(request, object_id)
            if obj and obj.is_active:
                buttons.append(PowerButton(url=reverse('admin:utils_userperson_personificar', kwargs={'user_id': object_id, }),
                                           label=u'Personificar'))
        return buttons


@admin.register(EmailAgendado)
class EmailAgendadoAdmin(PowerModelAdmin):
    list_display = ('subject', 'to', 'status', 'date')
    list_filter = ('status', 'date', )
    search_fields = ('subject', 'to')
    fieldsets = (
        (None, {'fields': ('subject', 'to', 'status', 'date', )}),
        (None, {'fields': ('html', )}),
    )
    actions = ('renviar', )

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return ('date',)
        else:
            return 'subject', 'to', 'status', 'date'

    def renviar(self, request, queryset):
        count = 0
        for record in queryset:
            record.send()
            count += 1
        messages.info(request, f'Total de emails enviados:{count}')


@admin.register(TipoProcessamento)
class TipoProcessamentoAdmin(PowerModelAdmin):
    list_display = ('tipo', 'documentacao')


@admin.register(LogEntry)
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

