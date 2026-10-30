"""
Testes de resiliência da confirmação de inscrição à falha da integração Moodle.

Regressão: um 502 do Moodle em registro_moodle propagava HTTPError e virava
Internal Server Error (500) para o discente. Agora efetiva_inscricao isola a
falha: a inscrição é confirmada mesmo assim, a falha vai para um log separado
e o discente recebe mensagem amigável.

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from datetime import date
from unittest import mock

from django.test import TestCase

from escola import views
from escola.models import Curso, TipoCurso, Discente, Inscricao


class EfetivaInscricaoMoodleResilienciaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tipo = TipoCurso.objects.create(descricao='Curso Livre')
        cls.curso = Curso.objects.create(
            nome='Curso EAD', tipo=cls.tipo, num_max_alunos=10,
            moodle_id=123, dt_inicio=date(2025, 1, 1))
        cls.discente = Discente.objects.create(
            nome='Fulano de Tal', email='fulano@example.com', cpf='08283667130')
        cls.inscricao = Inscricao.objects.create(
            curso=cls.curso, discente=cls.discente, status=Inscricao.Status.ABERTO)

    def test_falha_moodle_nao_quebra_e_confirma_inscricao(self):
        with mock.patch('escola.views.registro_moodle',
                        side_effect=Exception('502 Bad Gateway')):
            with mock.patch.object(views.moodle_falhas_logger, 'info') as mock_log:
                resultado = views.efetiva_inscricao(self.inscricao, envia_email=False)

        # A inscrição é confirmada apesar da falha no Moodle
        self.assertEqual(resultado['tipo'], 'sucesso')
        self.inscricao.refresh_from_db()
        self.assertEqual(self.inscricao.status, Inscricao.Status.ATIVA)
        # A falha foi registrada no log separado, com a URL de confirmação
        self.assertTrue(mock_log.called)
        args = mock_log.call_args[0]
        self.assertIn('FALHA MOODLE', args[0])
        self.assertIn('confirma_inscricao', ' '.join(str(a) for a in args))

    def test_sucesso_moodle_mantem_mensagem_padrao(self):
        with mock.patch('escola.views.registro_moodle') as mock_reg:
            resultado = views.efetiva_inscricao(self.inscricao, envia_email=False)
            mock_reg.assert_called_once()
        self.assertEqual(resultado['tipo'], 'sucesso')
        self.assertIn('acessar o curso', resultado['mensagem'].lower())
