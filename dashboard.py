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
from django.conf import settings

from nucleo.models import Professor


class CustomIndexDashboard(Dashboard):

    columns = 2

    def init_with_context(self, context):
        request = context.get('request')
        importacao = []
        if request.user.has_perm('auth.importacao_lattes'):
            importacao = [{'title': u'Importação Lattes',
                           'change_url': reverse('importacao_lattes'),},
                          ]
        if request.user.is_superuser:
            importacao.append({'title': u'Importação de Periódicos',
                               'change_url': reverse('importacao_periodicos'),
                               })
        if hasattr(settings, 'ESCOLA'):
            importacao.append({'title': u'Importação de Pautas e Listas',
                               'change_url': reverse('importacao_pauta')
                               })

        eh_docente = Professor.objects.filter(user=request.user).only('id')
        if eh_docente:
            painel_docente = [{'title': u'Painel Docente',
                               'change_url': reverse('painel_docente')}]
        else:
            painel_docente = []

        self.children += [
            modules.ModelList(
                u'Matrículas',
                models=('nucleo.models.Aluno', 'nucleo.models.Matricula', 'nucleo.models.Orientacao',
                        'nucleo.models.Periodo',
                        'nucleo.models.Turma',
                        'nucleo.models.Inscricao',
                        'nucleo.models.MatriculaEvento',
                        'nucleo.models.AtaReuniao',
                        )
            ),
            modules.ModelList(
                u'Editais',
                models=('editais.models.TipoVaga', 'editais.models.Edital', 'editais.models.Inscricao',)
            ),
            modules.ModelList(
                u'Cadastro Geral',
                models=('nucleo.models.Instituicao', 'nucleo.models.Programa', 'nucleo.models.LinhaPesquisa',
                        'nucleo.models.Curso',
                        'nucleo.models.Curriculo', 'nucleo.models.Disciplina',
                        'nucleo.models.Professor',
                        'nucleo.models.GrupoPesquisa',
                        'nucleo.models.TipoCurso',
                        'nucleo.models.TipoOcorrencia',
                        )
            ),
            modules.ModelList(
                u'Produção Científica',
                models=('nucleo.models.ProjetoPesquisa', 'nucleo.models.Fomento',
                        'nucleo.models.Pesquisador',
                        'nucleo.models.Producao',
                        'nucleo.models.ProducaoAutor',
                        'nucleo.models.TipoProducao',
                        'nucleo.models.Fomento',
                        'nucleo.models.AreaImpacto',
                        'nucleo.models.SetorEconomico',
                        )
            ),
            modules.ModelList(
                'Relatórios Anuais',
                models=('nucleo.models.ResumoAnual', 'nucleo.models.RelatorioAnual', )
            ),
            modules.ModelList(
                'Rotinas de Importação', ['',], children=importacao,
            ),
            modules.ModelList(
                u'Qualis',
                models=('qualis.models.Schema', 'qualis.models.Assunto', 'qualis.models.Periodico',
                        'qualis.models.PeriodicoISSN',  'qualis.models.GrandeArea',
                        'qualis.models.AreaConhecimento', 'qualis.models.Pais'),
            ),
            modules.ModelList(
                u'Administração',
                models=('django.contrib.*',
                        'poweradmin.models.*',
                        'utils.models.EmailAgendado',
                        'utils.models.UserPerson',
                        'utils.models.TipoProcessamento',
                        'nucleo.models.TipoDocumento',
                        'admin_tools.dashboard.models.DashboardPreferences', ),
                children=painel_docente,
            ),
        ]

        if hasattr(settings, 'ESCOLA'):
            self.children.append(
                modules.ModelList(
                    'Escola', models=('escola.models.Modulo', 'escola.models.Curso', 'escola.models.CursoFormal',
                                      'escola.models.Inscricao',
                                      'escola.models.Docente',
                                      'escola.models.Discente',
                                      'escola.models.ModuloTrilha',
                                      'escola.models.TipoCurso',
                                      'escola.models.PalavraChave'
                                      )
                ))
            self.children.append(
                modules.ModelList(
                    'Comunicação', models=('escola.models.Contato', 'escola.models.ListaInteresse',
                                           'escola.models.Comunicado', 'escola.models.ModeloCertificado',
                                           'escola.models.ListaContato')
                ))

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
