"""
Testes do log de alteração de membros da banca no admin — spec homologacao-defesa.

Verificam que MatriculaEventoAdmin.save_formset registra LogEntry (via log_object)
quando membros da banca (MatriculaEventoPesquisador) são incluídos, alterados ou
removidos ao editar a ocorrência no admin.

O save_formset só lê formset.model e as listas new_objects/changed_objects/
deleted_objects, então o teste as simula com um formset falso — exercitando a
lógica de log sem montar o POST completo do admin.

Testes com banco via tests/settings_test.py (SQLite em memória).
"""
from datetime import date

from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory

from nucleo.admin import MatriculaEventoAdmin
from nucleo.models import (
    Instituicao, Programa, Pesquisador, Curso, TipoCurso, Matricula,
    TipoOcorrencia, MatriculaEvento, MatriculaEventoPesquisador, Documento,
    STATUS_ATIVO,
)


class _FakeForm:
    def __init__(self, instance):
        self.instance = instance


class _FakeFormSet:
    """Simula o formset de inline do admin após o save()."""
    def __init__(self, model, new=None, changed=None, deleted=None):
        self.model = model
        self.new_objects = new or []
        self.changed_objects = changed or []
        self.deleted_objects = deleted or []

    # save_formset chama super().save_formset(...), que por sua vez chama
    # formset.save(). Para o inline de membros, não precisamos persistir nada
    # além do que o teste já criou; devolve as listas simuladas.
    def save(self, commit=True):
        return self.new_objects


class AdminBancaLogTest(TestCase):
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
        cls.ocorrencia = MatriculaEvento.objects.create(
            matricula=cls.matricula, tipo=cls.tipo, dtevento=date(2025, 6, 1),
            status=MatriculaEvento.Status.EM_EDICAO)
        cls.membro_pesq = Pesquisador.objects.create(nome='Membro Banca')
        cls.membro = MatriculaEventoPesquisador.objects.create(
            evento=cls.ocorrencia, pesquisador=cls.membro_pesq,
            externo=False, suplente=False, ordem=2)

    def setUp(self):
        self.admin = MatriculaEventoAdmin(MatriculaEvento, AdminSite())
        self.request = RequestFactory().post('/')
        self.ct_evento = ContentType.objects.get_for_model(MatriculaEvento)

    def _logs_da_ocorrencia(self):
        return LogEntry.objects.filter(
            content_type=self.ct_evento, object_id=self.ocorrencia.id)

    def test_log_membro_incluido(self):
        formset = _FakeFormSet(MatriculaEventoPesquisador, new=[self.membro])
        self.admin.save_formset(self.request, _FakeForm(self.ocorrencia), formset, change=True)
        logs = self._logs_da_ocorrencia().filter(change_message__contains='incluído')
        self.assertEqual(logs.count(), 1)
        self.assertIn(str(self.membro), logs.first().change_message)

    def test_log_membro_alterado(self):
        formset = _FakeFormSet(
            MatriculaEventoPesquisador, changed=[(self.membro, ['ordem'])])
        self.admin.save_formset(self.request, _FakeForm(self.ocorrencia), formset, change=True)
        logs = self._logs_da_ocorrencia().filter(change_message__contains='alterado')
        self.assertEqual(logs.count(), 1)
        self.assertIn('ordem', logs.first().change_message)

    def test_log_membro_removido(self):
        formset = _FakeFormSet(MatriculaEventoPesquisador, deleted=[self.membro])
        self.admin.save_formset(self.request, _FakeForm(self.ocorrencia), formset, change=True)
        logs = self._logs_da_ocorrencia().filter(change_message__contains='removido')
        self.assertEqual(logs.count(), 1)

    def test_outro_inline_nao_gera_log_de_membro(self):
        # Formset de outro model (ex.: Documento) não deve gerar log de membro.
        formset = _FakeFormSet(Documento, new=['x'])
        self.admin.save_formset(self.request, _FakeForm(self.ocorrencia), formset, change=True)
        self.assertEqual(self._logs_da_ocorrencia().count(), 0)
