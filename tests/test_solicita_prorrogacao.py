"""
Testes do endpoint solicita_prorrogacao (nucleo/views.py) — spec requerimento-prorrogacao.

Cobrem acesso/pre-condicoes, validacao do formulario e gravacao da ocorrencia
com anexos. sendmail e mockado; testes com banco via tests/settings_test.py.
"""
from datetime import date, datetime
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, Curso, TipoCurso, Pesquisador, Matricula,
    TipoOcorrencia, MatriculaEvento, TipoDocumento, Documento, Orientacao, STATUS_ATIVO,
)


def _arquivo(nome='a.pdf'):
    return SimpleUploadedFile(nome, b'conteudo', content_type='application/pdf')


class SolicitaProrrogacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')
        cls.tipo_curso = TipoCurso.objects.create(descricao='Doutorado')
        cls.curso = Curso.objects.create(descricao='DO', programa=cls.programa, tipo_curso=cls.tipo_curso)

        cls.user = User.objects.create_user(username='disc', password='x')
        cls.pesq = Pesquisador.objects.create(nome='Discente X', user=cls.user, email='d@x.com')
        # Matricula ativa (define matricula_atual no save)
        cls.matricula = Matricula.objects.create(
            pesquisador=cls.pesq, curso=cls.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)

        # Tipos 6 (prorrogacao defesa) e 7 (prorrogacao qualificacao)
        cls.tipo6 = TipoOcorrencia.objects.create(
            id=6, descricao='Prorrogacao de Defesa', template='Prorrogacao de {aluno}',
            status=TipoOcorrencia.Status.ATIVO)
        cls.tipo6.cursos.add(cls.curso)
        cls.tipo7 = TipoOcorrencia.objects.create(
            id=7, descricao='Prorrogacao de Qualificacao', template='Prorrogacao de {aluno}',
            status=TipoOcorrencia.Status.ATIVO)
        cls.tipo7.cursos.add(cls.curso)

        TipoDocumento.objects.create(descricao='Cronograma', chave='CRONOGRAMA')
        TipoDocumento.objects.create(descricao='Historico', chave='HISTORICO')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('solicita_prorrogacao')

    # ---- acesso / pre-condicoes ----

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(self.url + '?tipo=6')
        self.assertEqual(resp.status_code, 302)

    def test_sem_tipo_redireciona(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_tipo_inexistente_404(self):
        resp = self.client.get(self.url + '?tipo=999')
        self.assertEqual(resp.status_code, 404)

    def test_tipo6_sem_qualificacao_bloqueia(self):
        # matricula sem dtquali -> prorrogacao de defesa bloqueada
        resp = self.client.get(self.url + '?tipo=6')
        self.assertEqual(resp.status_code, 302)  # redirect painel

    def test_tipo7_com_qualificacao_bloqueia(self):
        self.matricula.dtquali = datetime(2025, 1, 10, 10, 0)
        self.matricula.save()
        resp = self.client.get(self.url + '?tipo=7')
        self.assertEqual(resp.status_code, 302)

    def test_tipo7_sem_qualificacao_exibe_form(self):
        resp = self.client.get(self.url + '?tipo=7')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)

    # ---- form ----

    def test_justificativa_curta_invalida(self):
        resp = self.client.post(self.url + '?tipo=7', {
            'justificativa': 'curta',
            'novo_cronograma': _arquivo('c.pdf'),
            'historico': _arquivo('h.pdf'),
        })
        self.assertEqual(resp.status_code, 200)  # reexibe com erro
        self.assertEqual(MatriculaEvento.objects.count(), 0)

    # ---- gravacao ----

    @mock.patch('nucleo.views.sendmail')
    def test_post_valido_cria_ocorrencia_e_anexos(self, _mock_sendmail):
        # Prorrogacao exige orientador ativo.
        orientador = Pesquisador.objects.create(nome='Orientador Ativo')
        Orientacao.objects.create(
            orientador=orientador, aluno=self.pesq, matricula=self.matricula,
            coorientacao=False, dt_inicio=date(2024, 3, 1), status=Orientacao.Status.ATIVA)
        resp = self.client.post(self.url + '?tipo=7', {
            'justificativa': 'Justificativa suficientemente longa para passar.',
            'novo_cronograma': _arquivo('c.pdf'),
            'historico': _arquivo('h.pdf'),
            'comentarios_adicionais': 'obs',
        })
        self.assertEqual(resp.status_code, 302)  # sucesso -> painel
        evento = MatriculaEvento.objects.get(matricula=self.matricula, tipo=self.tipo7)
        self.assertEqual(evento.status, MatriculaEvento.Status.AGUARDANDO_CD)
        self.assertEqual(Documento.objects.filter(object_id=evento.id).count(), 2)

    @mock.patch('nucleo.views.sendmail')
    def test_regressao_template_usa_ocorrencia_e_orientador(self, _mock_sendmail):
        # Reproduz o cenario de producao: template referencia {ocorrencia.id} e
        # {orientador.nome}. Antes da correcao, format(**locals()) lancava KeyError.
        orientador = Pesquisador.objects.create(nome='Prof Orientador')
        Orientacao.objects.create(
            orientador=orientador, aluno=self.pesq, matricula=self.matricula,
            coorientacao=False, dt_inicio=date(2024, 3, 1), status=Orientacao.Status.ATIVA)
        self.tipo7.template = ('Prorrogacao (#{ocorrencia.id}) de {aluno.nome}, '
                               'orientado por {orientador.nome}')
        self.tipo7.save()

        resp = self.client.post(self.url + '?tipo=7', {
            'justificativa': 'Justificativa suficientemente longa para passar.',
            'novo_cronograma': _arquivo('c.pdf'),
            'historico': _arquivo('h.pdf'),
        })
        self.assertEqual(resp.status_code, 302)
        evento = MatriculaEvento.objects.get(matricula=self.matricula, tipo=self.tipo7)
        self.assertIn(f'#{evento.id}', evento.descricao)
        self.assertIn('PROF ORIENTADOR', evento.descricao)  # Pesquisador.save() faz upper()

    @mock.patch('nucleo.views.sendmail')
    def test_sem_orientador_bloqueia_sem_attributeerror(self, _mock_sendmail):
        # Discente sem Orientacao ativa: o template usa {orientador.nome}, e
        # aluno.orientador e None. Deve bloquear com mensagem, nao quebrar.
        self.tipo7.template = 'Prorrogacao de {aluno.nome} orientado por {orientador.nome}'
        self.tipo7.save()
        resp = self.client.post(self.url + '?tipo=7', {
            'justificativa': 'Justificativa suficientemente longa para passar.',
            'novo_cronograma': _arquivo('c.pdf'),
            'historico': _arquivo('h.pdf'),
        })
        self.assertEqual(resp.status_code, 302)  # redirect painel, sem 500
        self.assertEqual(MatriculaEvento.objects.filter(tipo=self.tipo7).count(), 0)

