from datetime import datetime, timedelta
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

from nucleo.apps import validate_24hash, generate_24hash

class NoDbTestRunner(DiscoverRunner):
    """ A test runner to test without database creation/deletion """

    def setup_databases(self, **kwargs):
        pass

    def teardown_databases(self, old_config, **kwargs):
        pass

class Test(SimpleTestCase):
    def test_validate_24hash(self):
        r_base = generate_24hash('Odorico')
        r_igual = generate_24hash('Odorico')
        r_case = generate_24hash('odorico')
        self.assertEqual(r_base, r_igual, 'Igualdade')
        self.assertEqual(r_base, r_case, 'Teste Case')
        ontem = datetime.today() - timedelta(days=1)
        r_ontem = generate_24hash('Odorico',ontem)
        self.assertTrue(validate_24hash('Odorico',r_ontem),'Ontem')
        print('All tests passed')