"""
Testes dos endpoints solicita_trancamento e solicita_reativacao.

Correcao preventiva (mesma classe do bug da prorrogacao): template.format usava
locals(), quebrando com {ocorrencia.id} / {orientador.nome}. Ambas passaram a
exigir orientador ativo e a gerar a descricao com contexto explicito apos criar
o evento.

Testes com banco via tests/settings_test.py (SQLite em memoria).
"""
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, Curso, TipoCurso, Pesquisador, Matricula,
    TipoOcorrencia, MatriculaEvento, TipoDocumento, Orientacao, STATUS_ATIVO,
)


def _arquivo(nome='h.pdf'):
    return SimpleUploadedFile(nome, b'conteudo', content_type='application/pdf')


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')
        cls.tipo_curso = TipoCurso.objects.create(descricao='Doutorado')
        cls.curso = Curso.objects.create(descricao='DO', programa=cls.programa, tipo_curso=cls.tipo_curso)
        cls.user = User.objects.create_user(username='disc', password='x')
        cls.pesq = Pesquisador.objects.create(nome='Discente X', user=cls.user, email='d@x.com')
        TipoDocumento.objects.create(descricao='Historico', chave='HISTORICO')

    def _add_orientador(self):
        orientador = Pesquisador.objects.create(nome='Prof Orientador')
        Orientacao.objects.create(
            orientador=orientador, aluno=self.pesq, matricula=self.matricula,
            coorientacao=False, dt_inicio=date(2024, 3, 1), status=Orientacao.Status.ATIVA)
        return orientador


class TrancamentoTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.matricula = Matricula.objects.create(
            pesquisador=cls.pesq, curso=cls.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)
        cls.tipo8 = TipoOcorrencia.objects.create(
            id=8, descricao='Trancamento',
            template='Trancamento PDD-{ocorrencia.id} de {aluno.nome} orientado por {orientador.nome}',
            status=TipoOcorrencia.Status.ATIVO)
        cls.tipo8.cursos.add(cls.curso)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('solicita_trancamento')

    def _post(self):
        return self.client.post(self.url, {
            'justificativa': 'Justificativa suficientemente longa.',
            'historico': _arquivo(),
            'comentarios_adicionais': 'obs',
        })

    def test_sem_orientador_bloqueia(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(MatriculaEvento.objects.filter(tipo=self.tipo8).count(), 0)

    @mock.patch('nucleo.views.sendmail')
    def test_com_orientador_cria_e_renderiza_template(self, _m):
        self._add_orientador()
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        evento = MatriculaEvento.objects.get(tipo=self.tipo8)
        self.assertIn(f'PDD-{evento.id}', evento.descricao)
        self.assertIn('PROF ORIENTADOR', evento.descricao)


class ReativacaoTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Matricula trancada (reativacao exige status 'T')
        cls.matricula = Matricula.objects.create(
            pesquisador=cls.pesq, curso=cls.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status='T')
        cls.tipo10 = TipoOcorrencia.objects.create(
            id=10, descricao='Reativacao',
            template='Reativacao PDD-{ocorrencia.id} de {aluno.nome} orientado por {orientador.nome}',
            status=TipoOcorrencia.Status.ATIVO)
        cls.tipo10.cursos.add(cls.curso)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('solicita_reativacao')

    def _post(self):
        # Form de reativacao usa 'justificativa' (obrigatoria, min 10 chars).
        return self.client.post(self.url, {
            'justificativa': 'Motivo da reativacao suficientemente longo.',
        })

    def test_sem_orientador_bloqueia(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(MatriculaEvento.objects.filter(tipo=self.tipo10).count(), 0)

    @mock.patch('nucleo.views.sendmail')
    def test_com_orientador_cria_e_renderiza_template(self, _m):
        self._add_orientador()
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        evento = MatriculaEvento.objects.get(tipo=self.tipo10)
        self.assertIn(f'PDD-{evento.id}', evento.descricao)
        self.assertIn('PROF ORIENTADOR', evento.descricao)
