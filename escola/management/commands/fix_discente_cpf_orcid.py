from django.core.management import BaseCommand

from escola.models import Discente


class Command(BaseCommand):
    help = 'Remove CPF e ORCID duplicados'

    def handle(self, *args, **options):
        print('Atualizando ORCID em branco para nulo em Discente')

        total = Discente.objects.filter(orcid='').update(orcid=None)

        print(f'Registros atualizados: {total}')

        print('Atualizando CPF em branco para nulo em Discente')

        total = Discente.objects.filter(cpf='').update(cpf=None)

        print(f'Registros atualizados: {total}')
