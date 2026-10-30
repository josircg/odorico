from django.urls import path

from .interfaces import importacao_pauta, importacao_sessoes
from .relatorios import modulo_dash_resultados, modulo_exportacao_csv, modulo_dash_checkin, trilha_planilha
from .views import *

urlpatterns = [
    path('cursos/', cursos, name='cursos'),
    path('cursos_historico/', cursos_historico, name='cursos_historico'),
    path('eventos/', eventos, name='eventos'),
    path('curso/<int:curso_id>/', curso, name='curso'),
    path('evento/<str:slug>/', evento, name='evento'),
    path('checkin/<str:slug>/', checkin, name='checkin'),
    path('modulo/<str:slug>/', modulo, name='modulo_externo'),
    path('sessions/save/<str:slug>', save_schedule, name='save_schedule'),
    path('sessions/set/<int:session_id>/<str:token>', save_session, name='save_session'),
    path('sessions/<str:slug>/<str:token>', sessions, name='sessions_with_token'),
    path('sessions/<str:slug>/', sessions, name='sessions'),
    path('importacao_pauta/', importacao_pauta, name='importacao_pauta'),
    path('importacao_sessoes/', importacao_sessoes, name='importacao_sessoes'),
    path('agenda_certificado/<int:curso_id>/', agenda_certificado, name='agenda_certificado'),
    path('agenda_certificado_lista/<int:lista_id>/', agenda_certificado_lista, name='agenda_certificado_lista'),
    path('agenda_comunicado/<int:comunicado_id>/', agenda_comunicado, name='agenda_comunicado'),
    path('teste/<int:curso_id>/', teste_template, name='verificar_email_inscricao'),
    path('inscricao/<int:curso_id>/', inicia_inscricao, name='verificar_email_inscricao'),
    path('tela-consentimento/<int:curso_id>/<int:contato_id>', tela_consentimento, name='tela_consentimento'),
    path('discente/<str:hash_auth>/', cadastra_discente, name='cadastra_discente'),
    path('discente/<str:hash_auth>/<int:curso_id>/', cadastra_discente, name='cadastra_discente'),
    path('confirma_inscricao/<str:hash_auth>/', confirma_inscricao, name='confirma_inscricao'),
    path('confirma_presenca/<str:hash_auth>/', confirma_presenca, name='confirma_presenca'),
    path('inscricao_logout/', inscricao_logout, name='inscricao_logout'),
    path('meuscursos/', meuscursos, name='meus_cursos'),
    path('qrcode/<int:curso_id>/', curso_qrcode_view, name='curso_qrcode'),
    path('modulo_dash_resultados/<int:modulo_id>', modulo_dash_resultados, name='modulo_dash_resultados'),
    path('modulo_dash_checkin', modulo_dash_checkin, name='modulo_dash_checkin'),
    path('trilha_planilha', trilha_planilha, name='trilha_planilha'),
    path('modulo_exportacao_csv/<int:modulo_id>', modulo_exportacao_csv, name='modulo_exportacao_csv'),
    path('evento/presenca/<int:id_curso>', presenca_evento, name='presenca_evento'),

    path('cursos_ativos/', api_cursos_abertos, name='api_cursos'), # deprecated
    path('api/cursos_ativos/', api_cursos_abertos, name='api_cursos'),
    path('api/cursos_fechados/', api_cursos_fechados, name='api_cursos'),
    path('api/modulos/', api_modulos, name='api_modulos'),
    path('api/curso/<int:curso_id>/', api_curso, name='api_curso'),
    path('api/docentes/', docentes_ativos, name='docentes_ativos'),
    path('api/docente/<int:docente_id>', docente, name='docente'),
]
