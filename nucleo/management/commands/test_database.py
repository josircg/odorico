from django.core.management.base import BaseCommand
import unittest

from nucleo.tests import TestISSN


class Command(BaseCommand):
    help = """
    If you need Arguments, please check other modules in 
    django/core/management/commands.
    """

    def handle(self, **options):
        suite = unittest.TestLoader().loadTestsFromTestCase(TestISSN)
        unittest.TextTestRunner().run(suite)