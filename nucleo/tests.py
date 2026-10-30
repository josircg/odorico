import urllib3

from django.test import SimpleTestCase
from nucleo.apps import validate_issn_code, get_issn


class TestISSN(SimpleTestCase):
    def setUp(self) -> None:
        self.issn_valid = ['0020-0255','0953-1513','1852-4710', '1852-4729']
        self.issn_invalid = ['0032-147X', '0015-551A', '0001-1', '', None]
        urllib3.disable_warnings()

    def test_issn_valid_local(self):
        for issn in self.issn_valid:
            self.assertIsNotNone(validate_issn_code(issn), '%s é inválido' % issn)

    def test_get_issn_valid(self):
        for issn in self.issn_valid:
            self.assertIsInstance(get_issn(issn), dict, '%s é inválido' % issn)

    def test_invalid_issn(self):
        for issn in self.issn_invalid:
            self.assertIsInstance(get_issn(issn), str, 'Validação negativa')

