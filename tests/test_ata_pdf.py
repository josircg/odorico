"""
Testes da geração de PDF das ocorrências de uma ata — view ata_ocorrencias_pdf.

Verificam acesso restrito a staff, geração do PDF (status/content type) e 404
para ata inexistente. O conteúdo do PDF é binário (weasyprint); validar que
write_pdf() não quebra com o contexto real já cobre a renderização do template.

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from nucleo.models import (
    Instituicao, Programa, Pesquisador, Curso, TipoCurso, Matricula,
    TipoOcorrencia, MatriculaEvento, AtaReuniao, STATUS_ATIVO,
)


class AtaOcorrenciasPdfTest(TestCase):
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

        cls.ata = AtaReuniao.objects.create(descricao='CD 2025/01', dt=date(2025, 3, 10))
        # Ocorrências associadas à ata
        MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo, dtevento=date(2025, 2, 1),
            status=MatriculaEvento.Status.EM_EDICAO, ata_reuniao=cls.ata,
            descricao='Homologação de defesa do discente X')
        MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo, dtevento=date(2025, 2, 2),
            status=MatriculaEvento.Status.EM_EDICAO, ata_reuniao=cls.ata,
            descricao='Homologação de qualificação do discente Y')

        cls.staff = User.objects.create_user(username='staff', password='x', is_staff=True)
        cls.comum = User.objects.create_user(username='comum', password='x', is_staff=False)

    def setUp(self):
        self.client = Client()
        self.url = reverse('ata_ocorrencias_pdf', args=[self.ata.id])

    def test_nao_staff_sem_acesso(self):
        self.client.force_login(self.comum)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)  # redireciona para login do admin

    def test_staff_gera_pdf(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content[:4] == b'%PDF')

    def test_download_disposition(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url + '?download=1')
        self.assertIn('attachment', resp['Content-Disposition'])

    def test_ata_inexistente_404(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('ata_ocorrencias_pdf', args=[99999]))
        self.assertEqual(resp.status_code, 404)

    def test_ata_sem_ocorrencias_gera_pdf(self):
        ata_vazia = AtaReuniao.objects.create(descricao='CD vazia', dt=date(2025, 4, 1))
        self.client.force_login(self.staff)
        resp = self.client.get(reverse('ata_ocorrencias_pdf', args=[ata_vazia.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
