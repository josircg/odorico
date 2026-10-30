"""
Testes da view pública `defesa` — spec homologacao-defesa.

Cobrem a exibição da ocorrência de banca e a nova regra: quando a ocorrência
acessada está CANCELADA, a view redireciona para uma ocorrência de banca válida
(não cancelada, tipos 2–5) do mesmo discente — a mais recente por data.

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from datetime import date

from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, Pesquisador, Curso, TipoCurso, Matricula,
    TipoOcorrencia, MatriculaEvento, STATUS_ATIVO,
)


class DefesaViewTest(TestCase):
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

        cls.tipo_defesa = TipoOcorrencia.objects.create(id=2, descricao='Defesa de Tese de Doutorado')

        # Status válido qualquer (!= CANCELADO e != NAO_APROVADO). Usa-se
        # FINALIZADO por não disparar o efeito de APROVACAO_CD no save(),
        # que exigiria horario preenchido.
        cls.evento_valido = MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo_defesa, dtevento=date(2025, 6, 1),
            status=MatriculaEvento.Status.FINALIZADO)

    def setUp(self):
        self.client = Client()

    def test_exibe_ocorrencia_valida(self):
        url = reverse('defesa', args=[self.discente.id, self.evento_valido.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['matricula_evento'], self.evento_valido)

    def test_discente_divergente_404(self):
        url = reverse('defesa', args=[99999, self.evento_valido.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_cancelada_redireciona_para_valida(self):
        cancelada = MatriculaEvento.objects.create(
            matricula=self.matricula, tipo=self.tipo_defesa, dtevento=date(2025, 3, 1),
            status=MatriculaEvento.Status.CANCELADO)
        url = reverse('defesa', args=[self.discente.id, cancelada.id])
        resp = self.client.get(url)
        destino = reverse('defesa', args=[self.discente.id, self.evento_valido.id])
        self.assertRedirects(resp, destino, status_code=302, target_status_code=200)

    def test_cancelada_redireciona_para_mais_recente(self):
        # Duas válidas: o redirecionamento deve ir para a de data mais recente.
        mais_recente = MatriculaEvento.objects.create(
            matricula=self.matricula, tipo=self.tipo_defesa, dtevento=date(2025, 12, 1),
            status=MatriculaEvento.Status.FINALIZADO)
        cancelada = MatriculaEvento.objects.create(
            matricula=self.matricula, tipo=self.tipo_defesa, dtevento=date(2025, 1, 1),
            status=MatriculaEvento.Status.CANCELADO)
        url = reverse('defesa', args=[self.discente.id, cancelada.id])
        resp = self.client.get(url)
        destino = reverse('defesa', args=[self.discente.id, mais_recente.id])
        self.assertRedirects(resp, destino, status_code=302, target_status_code=200)

    def test_cancelada_sem_valida_404(self):
        # Discente cujo único evento de banca está cancelado → 404.
        outro = Pesquisador.objects.create(nome='Discente Y')
        matricula2 = Matricula.objects.create(
            pesquisador=outro, curso=self.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)
        cancelada = MatriculaEvento.objects.create(
            matricula=matricula2, tipo=self.tipo_defesa, dtevento=date(2025, 3, 1),
            status=MatriculaEvento.Status.CANCELADO)
        url = reverse('defesa', args=[outro.id, cancelada.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_nao_aprovado_nao_e_destino_valido(self):
        # Discente cujas outras ocorrências são canceladas ou não aprovadas → 404
        # (NAO_APROVADO não conta como destino válido).
        outro = Pesquisador.objects.create(nome='Discente Z')
        matricula3 = Matricula.objects.create(
            pesquisador=outro, curso=self.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)
        MatriculaEvento.objects.create(
            matricula=matricula3, tipo=self.tipo_defesa, dtevento=date(2025, 5, 1),
            status=MatriculaEvento.Status.NAO_APROVADO)
        cancelada = MatriculaEvento.objects.create(
            matricula=matricula3, tipo=self.tipo_defesa, dtevento=date(2025, 3, 1),
            status=MatriculaEvento.Status.CANCELADO)
        url = reverse('defesa', args=[outro.id, cancelada.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
