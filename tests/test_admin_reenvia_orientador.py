"""
Testes da action reenvia_email_orientador do MatriculaEventoAdmin.

Regressão: a action acessava evento.matricula.aluno (inexistente), quebrando
com AttributeError. Agora busca a Orientacao ativa pela matrícula.

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from datetime import date
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import TestCase, RequestFactory

from nucleo.admin import MatriculaEventoAdmin
from nucleo.models import (
    Instituicao, Programa, Pesquisador, Curso, TipoCurso, Matricula,
    TipoOcorrencia, MatriculaEvento, Orientacao, STATUS_ATIVO,
)


class ReenviaEmailOrientadorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')
        cls.tipo_curso = TipoCurso.objects.create(descricao='Doutorado')
        cls.curso = Curso.objects.create(descricao='DO', programa=cls.programa, tipo_curso=cls.tipo_curso)
        cls.discente = Pesquisador.objects.create(nome='Discente X')
        cls.matricula = Matricula.objects.create(
            pesquisador=cls.discente, curso=cls.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)
        cls.tipo = TipoOcorrencia.objects.create(id=2, descricao='Defesa de Tese de Doutorado')
        cls.evento = MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo, dtevento=date(2025, 6, 1),
            status=MatriculaEvento.Status.EM_EDICAO)
        cls.orientador = Pesquisador.objects.create(nome='Orientador Y', email='o@x.com')

    def setUp(self):
        self.admin = MatriculaEventoAdmin(MatriculaEvento, AdminSite())
        self.request = RequestFactory().post('/')
        # message_user precisa do middleware de mensagens; mocka para isolar.
        self.admin.message_user = mock.Mock()

    def test_com_orientacao_ativa_envia(self):
        Orientacao.objects.create(
            orientador=self.orientador, aluno=self.discente, matricula=self.matricula,
            coorientacao=False, dt_inicio=date(2024, 3, 1), status=Orientacao.Status.ATIVA)
        qs = MatriculaEvento.objects.filter(id=self.evento.id)
        with mock.patch.object(MatriculaEvento, 'solicita_aprovacao_orientador') as m:
            self.admin.reenvia_email_orientador(self.request, qs)
            m.assert_called_once_with(self.orientador)

    def test_sem_orientacao_nao_quebra(self):
        qs = MatriculaEvento.objects.filter(id=self.evento.id)
        with mock.patch.object(MatriculaEvento, 'solicita_aprovacao_orientador') as m:
            # Nao deve lancar AttributeError
            self.admin.reenvia_email_orientador(self.request, qs)
            m.assert_not_called()
        # Deve ter avisado que nao encontrou orientador
        self.assertTrue(self.admin.message_user.called)
