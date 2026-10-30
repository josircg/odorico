from django.core.management import BaseCommand
from django.db.models import Count

from nucleo.models import Pesquisador


class Command(BaseCommand):
    help = 'Remove CPF e ORCID duplicados'

    def handle(self, *args, **options):
        print('Removendo ORCID duplicado dos Pesquisadores')

        ocrid_duplicados = (
            Pesquisador.objects.exclude(orcid__isnull=True).values('orcid')
            .annotate(total=Count('id')).filter(total__gt=1).values_list('orcid')
        )

        total = 0

        for pesquisador in  Pesquisador.objects.filter(dtupdate__isnull=True, orcid__in=ocrid_duplicados):
            print(f'Pesquisador: {pesquisador} - ID: {pesquisador.pk} - ORCID: {pesquisador.orcid}')

            pesquisador.orcid = None
            pesquisador.save()

            total += 1

        print(f'Registros atualizados: {total}')

        print('Removendo CPF duplicado dos Pesquisadores')

        cpf_duplicados = (
            Pesquisador.objects.exclude(CPF__isnull=True).values('CPF')
            .annotate(total=Count('id')).filter(total__gt=1).values_list('CPF')
        )

        total = 0
        for pesquisador in  Pesquisador.objects.filter(dtupdate__isnull=True, CPF__in=cpf_duplicados):
            print(f'Pesquisador: {pesquisador} - ID: {pesquisador.pk} - CPF: {pesquisador.CPF}')

            pesquisador.CPF = None
            pesquisador.save()

            total += 1

        print(f'Registros atualizados: {total}')

        print('Fim do processamento')