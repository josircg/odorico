from django.test import TestCase
from nucleo.apps import validate_issn_code, get_issn
from nucleo.models import Periodico
from nucleo.views import find_key_by_value, dict_livros_e_capitulos

class TestISSN(TestCase):
    def setUp(self) -> None:
        self.issn_valid = list(Periodico.objects.all().values_list('issn', flat=True))
        self.issn_invalid = ['0032-147X', '0015-551A', '0001-1', '', None]

    def test_issn_valid_local(self):
        for issn in self.issn_valid:
            self.assertIsNotNone(validate_issn_code(issn), '%s é inválido' % issn)

    def test_get_issn_valid(self):
        for issn in self.issn_valid:
            self.assertIsInstance(get_issn(issn, extended=True), tuple, '%s é inválido' % issn)

    def test_valid_issn_invalid(self):
        for issn in self.issn_invalid:
            self.assertEqual(get_issn(issn), 'NF')

class find_key_by_value_function_TestCase(TestCase):

    def setUp(self):

        self.testValues = [
            ("TEXTO_INTEGRAL", "O"),
            ("COLETANEA", "L"),
            ("DIGITAL", "D"),
            ("CD", "D"),
            ("FILME", "F"),
            ("HIPERTEXTO", "H"),
            ("APRESENTACAO", "A"),
            ("INTRODUCAO", "I"),
            ("PREFACIO", "P"),
            ("POSFACIO", "O"),
            ("LIVRO_PUBLICADO", "L"),
            ("COMPLETO", "T"),
            ("RESUMO", "R"),
            ("RESUMOX", "X"),
            ("NAO_EXISTE", None),
        ]


    def test_find_key_by_value_testing_testValues(self):

        for value, expected in self.testValues:
            result = find_key_by_value(dict_livros_e_capitulos, value)
            self.assertEqual(result, expected)

        #caso erro
        self.assertFalse(find_key_by_value(dict_livros_e_capitulos, "CASO_ERRO"), "C")

