"""
Testes da view turma_avaliacao (lançamento de conceitos) — spec turma-avaliacao.

Após a mudança de regra, a view é acessada por `/turma/avaliacao/<turma_id>/`,
exige login e só o professor da turma acessa (sem hash, sem fluxo de e-mail).

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, Pesquisador, PesquisadorPrograma,
    Curriculo, Disciplina, Periodo, Turma, TurmaProfessor, Inscricao,
)


class TurmaAvaliacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')

        # Professor da turma
        cls.user_prof = User.objects.create_user(username='prof', password='x')
        cls.prof = Pesquisador.objects.create(nome='Prof Titular', user=cls.user_prof)
        PesquisadorPrograma.objects.create(pesquisador=cls.prof, programa=cls.programa)

        cls.curriculo = Curriculo.objects.create(descricao='Curr', ano=2024)
        cls.disciplina = Disciplina.objects.create(titulo='Disc A', curriculo=cls.curriculo)
        cls.periodo = Periodo.objects.create(ano=2024, status=Periodo.Status.ATIVO)
        cls.turma = Turma.objects.create(periodo=cls.periodo, disciplina=cls.disciplina, num_alunos_max=30)
        TurmaProfessor.objects.create(turma=cls.turma, professor=cls.prof)

        # Discentes com inscrições: avaliável (M) e não avaliável (Dispensa)
        cls.aluno1 = Pesquisador.objects.create(nome='Aluno Um')
        cls.aluno2 = Pesquisador.objects.create(nome='Aluno Dois')
        cls.insc_avaliavel = Inscricao.objects.create(
            turma=cls.turma, aluno=cls.aluno1, status=Inscricao.Status.MATRICULADO)
        cls.insc_dispensa = Inscricao.objects.create(
            turma=cls.turma, aluno=cls.aluno2, status=Inscricao.Status.DISPENSA)

    def setUp(self):
        self.client = Client()
        self.url = reverse('turma_avaliacao', args=[self.turma.id])

    def test_login_required(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_turma_inexistente_404(self):
        self.client.force_login(self.user_prof)
        resp = self.client.get(reverse('turma_avaliacao', args=[99999]))
        self.assertEqual(resp.status_code, 404)

    def test_nao_professor_da_turma_recebe_acesso_negado(self):
        outro = User.objects.create_user(username='outro', password='x')
        pesq = Pesquisador.objects.create(nome='Outro Docente', user=outro)
        PesquisadorPrograma.objects.create(pesquisador=pesq, programa=self.programa)
        self.client.force_login(outro)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Acesso Negado')

    def test_professor_ve_apenas_inscricoes_avaliaveis(self):
        self.client.force_login(self.user_prof)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        inscricoes = [item['inscricao'] for item in resp.context['items']]
        self.assertIn(self.insc_avaliavel, inscricoes)
        self.assertNotIn(self.insc_dispensa, inscricoes)

    def test_gravacao_deriva_status_do_conceito(self):
        self.client.force_login(self.user_prof)
        resp_get = self.client.get(self.url)
        formset = resp_get.context['formset']
        prefix = formset.prefix

        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '1',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-0-inscricao_id': str(self.insc_avaliavel.id),
            f'{prefix}-0-conceito': 'A',
        }
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 200)

        self.insc_avaliavel.refresh_from_db()
        self.assertEqual(self.insc_avaliavel.conceito, 'A')
        # conceito A/B/C → status APROVADO (regra de Inscricao.save)
        self.assertEqual(self.insc_avaliavel.status, Inscricao.Status.APROVADO)

    def test_gravacao_conceito_d_reprova(self):
        self.client.force_login(self.user_prof)
        resp_get = self.client.get(self.url)
        prefix = resp_get.context['formset'].prefix
        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '1',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-0-inscricao_id': str(self.insc_avaliavel.id),
            f'{prefix}-0-conceito': 'D',
        }
        self.client.post(self.url, data)
        self.insc_avaliavel.refresh_from_db()
        self.assertEqual(self.insc_avaliavel.conceito, 'D')
        self.assertEqual(self.insc_avaliavel.status, Inscricao.Status.REPROVADO)

    def test_gravacao_conceito_f_reprova_por_falta(self):
        self.client.force_login(self.user_prof)
        resp_get = self.client.get(self.url)
        prefix = resp_get.context['formset'].prefix
        data = {
            f'{prefix}-TOTAL_FORMS': '1',
            f'{prefix}-INITIAL_FORMS': '1',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
            f'{prefix}-0-inscricao_id': str(self.insc_avaliavel.id),
            f'{prefix}-0-conceito': 'F',
        }
        self.client.post(self.url, data)
        self.insc_avaliavel.refresh_from_db()
        self.assertEqual(self.insc_avaliavel.conceito, 'F')
        self.assertEqual(self.insc_avaliavel.status, Inscricao.Status.REP_FALTA)
