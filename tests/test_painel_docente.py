"""
Testes das views do painel do docente — spec painel-docente.

Cobrem:
- ``painel_docente``: acesso restrito a docentes do programa e listagem de
  turmas ativas (sem duplicatas).
- ``bancas_docente``: acesso restrito a docentes do programa (pesquisador
  externo, mesmo sendo membro de banca, recebe acesso negado) e listagem das
  bancas (tipos 2–5) do docente, ordenadas por data.

Usa TestCase (com banco) por envolver criação de registros do domínio.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, LinhaPesquisa, Pesquisador, Professor,
    PesquisadorPrograma, Curso, TipoCurso, Curriculo, Disciplina, Periodo,
    Turma, TurmaProfessor, Matricula, TipoOcorrencia, MatriculaEvento,
    MatriculaEventoPesquisador, STATUS_ATIVO,
)


def cria_docente(nome, username, programa):
    """Cria um Pesquisador vinculado a um programa (reconhecido como Professor)."""
    user = User.objects.create_user(username=username, password='x')
    pesq = Pesquisador.objects.create(nome=nome, user=user)
    PesquisadorPrograma.objects.create(pesquisador=pesq, programa=programa)
    return user, pesq


class PainelDocenteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')
        cls.linha = LinhaPesquisa.objects.create(descricao='Linha', programa=cls.programa)

        cls.user, cls.docente = cria_docente('Docente Um', 'docente1', cls.programa)

        cls.curriculo = Curriculo.objects.create(descricao='Curr', ano=2024)
        cls.disciplina = Disciplina.objects.create(titulo='Disc A', curriculo=cls.curriculo)
        cls.periodo_ativo = Periodo.objects.create(ano=2024, status=Periodo.Status.ATIVO)
        cls.periodo_fechado = Periodo.objects.create(ano=2023, status=Periodo.Status.FECHADO)

        cls.turma_ativa = Turma.objects.create(
            periodo=cls.periodo_ativo, disciplina=cls.disciplina, num_alunos_max=30)
        TurmaProfessor.objects.create(turma=cls.turma_ativa, professor=cls.docente)

        cls.turma_fechada = Turma.objects.create(
            periodo=cls.periodo_fechado, disciplina=cls.disciplina, num_alunos_max=30)
        TurmaProfessor.objects.create(turma=cls.turma_fechada, professor=cls.docente)

    def setUp(self):
        self.client = Client()

    def test_login_required(self):
        resp = self.client.get(reverse('painel_docente'))
        self.assertEqual(resp.status_code, 302)  # redireciona para login

    def test_acesso_negado_para_nao_docente(self):
        user = User.objects.create_user(username='comum', password='x')
        self.client.force_login(user)
        resp = self.client.get(reverse('painel_docente'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Acesso Negado')

    def test_lista_apenas_turmas_ativas(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('painel_docente'))
        self.assertEqual(resp.status_code, 200)
        turmas = list(resp.context['turmas'])
        self.assertIn(self.turma_ativa, turmas)
        self.assertNotIn(self.turma_fechada, turmas)

    def test_turmas_sem_duplicatas(self):
        # Segundo vínculo do mesmo docente na mesma turma não deve duplicar
        TurmaProfessor.objects.create(turma=self.turma_ativa, professor=self.docente)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('painel_docente'))
        turmas = list(resp.context['turmas'])
        self.assertEqual(turmas.count(self.turma_ativa), 1)


class BancasDocenteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inst = Instituicao.objects.create(nome='Inst', sigla='INST')
        cls.programa = Programa.objects.create(instituicao=cls.inst, descricao='PPG')
        cls.linha = LinhaPesquisa.objects.create(descricao='Linha', programa=cls.programa)

        cls.user, cls.docente = cria_docente('Docente Banca', 'docbanca', cls.programa)

        cls.tipo_curso = TipoCurso.objects.create(descricao='Doutorado')
        cls.curso = Curso.objects.create(descricao='DO', programa=cls.programa, tipo_curso=cls.tipo_curso)

        # Discente (dono da banca)
        cls.discente = Pesquisador.objects.create(nome='Discente X')
        cls.matricula = Matricula.objects.create(
            pesquisador=cls.discente, curso=cls.curso, ingresso=2024,
            dtmatricula=date(2024, 3, 1), status=STATUS_ATIVO)

        # Tipos de ocorrência de banca (2–5) — usa get_or_create pela PK fixa do fluxo
        cls.tipo_defesa_do = TipoOcorrencia.objects.create(id=2, descricao='Defesa de Tese de Doutorado')

        # Banca em que o docente é membro
        cls.evento = MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo_defesa_do, dtevento=date(2025, 6, 1))
        MatriculaEventoPesquisador.objects.create(
            evento=cls.evento, pesquisador=cls.docente, externo=False, suplente=False, ordem=2)

    def setUp(self):
        self.client = Client()

    def test_login_required(self):
        resp = self.client.get(reverse('bancas_docente'))
        self.assertEqual(resp.status_code, 302)

    def test_docente_ve_suas_bancas(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('bancas_docente'))
        self.assertEqual(resp.status_code, 200)
        bancas = resp.context['bancas']
        self.assertEqual(len(bancas), 1)
        self.assertEqual(bancas[0]['tipo'], 'Defesa de Tese de Doutorado')
        self.assertEqual(bancas[0]['discente'], self.discente)
        self.assertEqual(bancas[0]['dt'], date(2025, 6, 1))

    def test_pesquisador_externo_nao_tem_acesso(self):
        # Pesquisador sem vínculo de programa, mas membro de uma banca.
        user_ext = User.objects.create_user(username='externo', password='x')
        externo = Pesquisador.objects.create(nome='Membro Externo', user=user_ext)
        evento2 = MatriculaEvento.objects.create(
            matricula=self.matricula, tipo=self.tipo_defesa_do, dtevento=date(2025, 7, 1))
        MatriculaEventoPesquisador.objects.create(
            evento=evento2, pesquisador=externo, externo=True, suplente=False, ordem=3)

        self.client.force_login(user_ext)
        resp = self.client.get(reverse('bancas_docente'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Acesso Negado')
        self.assertNotIn('bancas', resp.context or {})

    def test_bancas_ordenadas_por_data(self):
        # Adiciona uma banca anterior; deve vir primeiro
        evento_antes = MatriculaEvento.objects.create(
            matricula=self.matricula, tipo=self.tipo_defesa_do, dtevento=date(2025, 1, 1))
        MatriculaEventoPesquisador.objects.create(
            evento=evento_antes, pesquisador=self.docente, externo=False, suplente=False, ordem=2)

        self.client.force_login(self.user)
        resp = self.client.get(reverse('bancas_docente'))
        datas = [b['dt'] for b in resp.context['bancas']]
        self.assertEqual(datas, sorted(datas))
