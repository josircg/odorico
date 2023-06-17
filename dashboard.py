# -*- coding: utf-8 -*-
"""
This file was generated with the customdashboard management command, it
contains the two classes for the main dashboard and app index dashboard.
You can customize these classes as you want.

To activate your index dashboard add the following to your settings.py::
    ADMIN_TOOLS_INDEX_DASHBOARD = 'radix.dashboard.CustomIndexDashboard'

And to activate the app index dashboard::
    ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'radix.dashboard.CustomAppIndexDashboard'
"""

from django.utils.translation import ugettext_lazy as _
from admin_tools.dashboard import modules, Dashboard, AppIndexDashboard
from admin_tools.utils import get_admin_site_name
from django.urls import reverse


class CustomIndexDashboard(Dashboard):

    columns = 2

    def init_with_context(self, context):
        site_name = get_admin_site_name(context)
        request = context.get('request')
        importacao = []
        if request.user.has_perm('auth.importacao_lattes'):
            importacao = [
                {
                    'title': u'Importação Lattes',
                    'change_url': reverse('importacao_lattes'),
                },
                {
                    'title': u'Importação de Periódicos',
                    'change_url': reverse('importacao_periodicos'),
                },
            ]

        self.children += [
            modules.ModelList(
                u'Matrículas',
                models=('nucleo.models.Aluno', 'nucleo.models.Matricula', )
            ),
            modules.ModelList(
                u'Cadastro',
                models=('nucleo.models.Instituicao', 'nucleo.models.Programa', 'nucleo.models.LinhaPesquisa',
                        'nucleo.models.ProjetoPesquisa', 'nucleo.models.Curso', 'nucleo.models.Fomento',
                        'nucleo.models.Professor', 'nucleo.models.Pesquisador',
                        'nucleo.models.TipoProducao',
                        'nucleo.models.Producao',
                        'nucleo.models.ProducaoAutor',
                        )
            ),
            modules.ModelList(
                u'Relatórios Anuais',
                models=('nucleo.models.ResumoAnual', 'nucleo.models.RelatorioAnual', )
            ),
            modules.ModelList(
                'Rotinas de Importação', [
                    '',
                ], children=importacao,
            ),
            modules.ModelList(
                u'Qualis',
                models=('qualis.models.*',),
            ),
            modules.ModelList(
                u'Adminstração',
                models=('django.contrib.*',
                        'utils.models.EmailAgendado',
                        'utils.models.TipoProcessamento',
                        'admin_tools.dashboard.models.DashboardPreferences', ),
            ),
        ]


class CustomAppIndexDashboard(AppIndexDashboard):

    # we disable title because its redundant with the model list module
    title = ''

    def __init__(self, *args, **kwargs):
        AppIndexDashboard.__init__(self, *args, **kwargs)

        # append a model list module and a recent actions module
        self.children += [
            modules.ModelList(self.app_title, self.models),
            modules.RecentActions(
                _('Recent Actions'),
                include_list=self.get_app_content_types(),
                limit=5
            )
        ]

    def init_with_context(self, context):
        """
        Use this method if you need to access the request context.
        """
        return super(CustomAppIndexDashboard, self).init_with_context(context)
