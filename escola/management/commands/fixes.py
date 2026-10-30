from django.conf import settings
from django.core.management.base import BaseCommand

from escola.models import Discente, Contato

class Command(BaseCommand):
    label = 'Fixes'

    def handle(self, *args, **options):
        total = 0
        for discente in Discente.objects.filter(contato__isnull=True):
             contato = Contato.objects.filter(email=discente.email).first()
             if not contato:
                 contato = Contato()
             contato.email=discente.email
             contato.nome=discente.nome
             contato.utm_source = contato.utm_source or 'Interno'
             contato.save()
             discente.contato = contato
             discente.save()
             total += 1
        print(f'Total de Registros alterados: {total}')