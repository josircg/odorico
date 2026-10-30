"""
Testes do fluxo de deploy local (Opção B) — spec deploy-automatico, tarefa 6.

Cobrem a view ``system_update`` / ``execute_deploy_tema`` em ``utils/views.py``:
invocação do script versionado, exigência de staff, montagem do log em sucesso
e falha, gate de DEBUG (SKIP_RESTART) e regressão do bug de concatenação de
``None`` que existia quando a view usava ``call_command`` diretamente.

Nenhum teste executa git pull/migrate/collectstatic/restart reais: ``os_run`` é
sempre mockado. Não há acesso a banco (SimpleTestCase).
"""
import os
from unittest import mock

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, RequestFactory

from utils import views


def _staff_request(factory, method='get'):
    """Monta um request com usuário staff e storage de mensagens anexado."""
    request = getattr(factory, method)('/system_update/')
    request.user = mock.Mock(is_staff=True, is_active=True, is_authenticated=True)
    # RequestFactory não passa pelo middleware; anexa o storage de mensagens.
    setattr(request, 'session', {})
    setattr(request, '_messages', FallbackStorage(request))
    return request


class SystemUpdateViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @mock.patch('utils.views.os_run', return_value='saida\nok')
    def test_invoca_script_na_raiz_do_projeto(self, mock_os_run):
        """A view deve invocar deploy.sh via os_run com cwd=BASE_DIR."""
        request = _staff_request(self.factory)
        response = views.system_update(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_os_run.called)
        args, kwargs = mock_os_run.call_args
        comando = args[0]
        self.assertEqual(comando[0], 'bash')
        self.assertEqual(comando[1], os.path.join(settings.BASE_DIR, 'deploy.sh'))
        self.assertEqual(kwargs.get('cwd'), settings.BASE_DIR)

    @mock.patch('utils.views.os_run', return_value='linha1\nlinha2')
    def test_sucesso_monta_log_com_quebras_em_br(self, mock_os_run):
        """Em sucesso, a saída do script vira o log (com <br/> no lugar de \\n)."""
        request = _staff_request(self.factory)
        response = views.system_update(request)
        self.assertIn('linha1<br/>linha2', response.content.decode())

    @mock.patch('utils.views.os_run', return_value='qualquer saida de texto')
    def test_regressao_sem_typeerror_de_concatenacao(self, mock_os_run):
        """
        Regressão: o fluxo antigo concatenava o retorno (None) de call_command
        e lançava TypeError. Agora a saída é string e não deve haver exceção.
        """
        request = _staff_request(self.factory)
        try:
            response = views.system_update(request)
        except TypeError as e:
            self.fail(f'system_update não deve lançar TypeError: {e}')
        self.assertEqual(response.status_code, 200)

    @mock.patch('utils.views.os_run', side_effect=ValidationError('falha no git pull'))
    def test_falha_trata_excecao_e_exibe_log(self, mock_os_run):
        """Em falha, a view trata a exceção e inclui a mensagem no log."""
        request = _staff_request(self.factory)
        response = views.system_update(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('falha no git pull', response.content.decode())

    @mock.patch('utils.views.os_run', return_value='ok')
    def test_debug_injeta_skip_restart(self, mock_os_run):
        """Em DEBUG, o script é chamado com SKIP_RESTART=1 no ambiente."""
        with self.settings(DEBUG=True):
            request = _staff_request(self.factory)
            views.system_update(request)
        _, kwargs = mock_os_run.call_args
        self.assertEqual(kwargs.get('env', {}).get('SKIP_RESTART'), '1')

    @mock.patch('utils.views.os_run', return_value='ok')
    def test_sem_debug_nao_injeta_skip_restart(self, mock_os_run):
        """Fora de DEBUG, SKIP_RESTART não é forçado (restart ocorre no script)."""
        with self.settings(DEBUG=False):
            request = _staff_request(self.factory)
            views.system_update(request)
        _, kwargs = mock_os_run.call_args
        self.assertIsNone(kwargs.get('env', {}).get('SKIP_RESTART'))


class DeployTemaViewTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @mock.patch('utils.views.os_run', return_value='deploy ok')
    def test_get_nao_executa_deploy(self, mock_os_run):
        """GET apenas renderiza o formulário, sem invocar o script."""
        request = _staff_request(self.factory, method='get')
        response = views.execute_deploy_tema(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(mock_os_run.called)

    @mock.patch('utils.views.os_run', return_value='deploy ok')
    def test_post_reutiliza_o_mesmo_script(self, mock_os_run):
        """POST reutiliza deploy.sh (fonte única de verdade dos passos)."""
        request = _staff_request(self.factory, method='post')
        views.execute_deploy_tema(request)
        self.assertTrue(mock_os_run.called)
        comando = mock_os_run.call_args[0][0]
        self.assertEqual(comando[1], os.path.join(settings.BASE_DIR, 'deploy.sh'))


class StaffRequiredTest(SimpleTestCase):
    """A URL de deploy só pode ser disparada por usuário de staff."""

    def setUp(self):
        self.factory = RequestFactory()

    @mock.patch('utils.views.os_run', return_value='ok')
    def test_nao_staff_recebe_redirect(self, mock_os_run):
        request = self.factory.get('/system_update/')
        request.user = mock.Mock(is_staff=False, is_active=True, is_authenticated=True)
        response = views.system_update(request)
        # staff_member_required redireciona para o login do admin
        self.assertEqual(response.status_code, 302)
        self.assertFalse(mock_os_run.called)
