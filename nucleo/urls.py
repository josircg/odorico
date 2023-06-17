from django.conf.urls import url
from django.urls import path

from .views import *

urlpatterns = [
    url(r'^$', home, name='home'),
    url(r'^importacao_lattes/(?:(?P<hash>[0-9A-Za-z_\-]+)/)?$', importacao_lattes, name='importacao_lattes'),
    url(r'^importacao_dummy/', importacao_dummy, name='importacao_dummy'),
    url(r'^agenda_defesas/', agenda_defesas, name='agenda_defesas'),
    url(r'^defesas_realizadas/', defesas_realizadas, name='defesas_realizadas'),
    url(r'^resumo_qualis/(?P<id>\w+)$', resumo_qualis, name='resumo_qualis'),
    url(r'^mapa_paises', mapa_paises, name='mapa_paises'),
    url(r'^mapa_csv', mapa_csv, name='mapa_csv'),
    url(r'^error', error, name='error'),
    path('doi_record/<path:doi>', doi_record, name='doi_record'),
    url(r'^producao_projeto/(?P<id_lattes>\w+)$', producao_projeto, name='producao_projeto'),
    url(r'^producao_analise/(?P<id_producao>\w+)', producao_analise, name='producao_projeto'),
    url(r'^producao_edit/(?P<id>\d+)$', producao_edit, name='producao_edit'),
    url(r'^linha_professor/(?P<id_linha>\d+)$', linha_professor, name='linha_professor'),
    url(r'^novo_projeto/(?P<id_lattes>\w+)$', novo_projeto, name='novo_projeto'),
    url(r'^qualis_resumo/(?P<programa_ids>[\w\-]+)/$', qualis_resumo, name='qualis_resmo'),
    url(r'^lattes-resumo/$', lattes_resumo, name='lattes-resumo'),
    url(r'^lattes-resumo/(?P<id_lattes_params>\w+)/$', lattes_resumo, name='lattes-resumo_params'),
    url(r'^avaliacao-anual/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_anual, name='avaliacao_anual'),
    url(r'^avaliacao-cadastro/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_cadastro, name='avaliacao_cadastro'),
    url(r'^avaliacao-resumo/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_resumo, name='avaliacao_resumo'),
    url(r'^avaliacao-sandwich/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_sandwich, name='avaliacao_sandwich'),
    url(r'^avaliacao-validacao/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_validacao, name='avaliacao_validacao'),
    url(r'^avaliacao-aprovacao/(?P<hash>[0-9A-Za-z_\-]+)/$', avaliacao_aprovacao, name='avaliacao_aprovacao'),
    path('editar-producao/<str:hash>/<str:hash_producao>/', editar_producao, name='editar_producao'),
    url(r'^convite_alunos/(?P<id_resumo>\d+)/$', convite_alunos, name='convite_alunos'),
    path('selecionar-nova-producao/<str:hash_auth>/', selecionar_nova_producao, name='selecionar_nova_producao'),
    path('nova-producao/<str:hash_auth>/<int:tipo_id>/', nova_producao, name='nova_producao'),
]
