# Rotina que marca periódicos como Comunicação caso eles tenham menos de 3 assuntos associados.
from django.core.management import BaseCommand

from qualis.models import Periodico, PeriodicoAssunto, Assunto, AreaConhecimento


class Command(BaseCommand):

    def handle(self, *args, **options):

        # Marca todos os periódicos com área INDEFINIDA para NULO
        area = AreaConhecimento.objects.filter(nome='INDEFINIDO').first()
        if area:
            tot_registros = Periodico.objects.filter(area=area).update(area=None)
            print(f'{tot_registros} desmarcados')

        # Ajusta o qualis NC para ND (Não disponível)
        Periodico.objects.filter(qualis='NC').update(qualis='ND')

        assunto = Assunto.objects.get(schema__sigla='ASJC', cod_externo='3315')
        area = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')

        # se o periódico tiver menos de 3 assuntos e um deles for Comunicação, marcar a área como Comunicação
        tot_registros = 0
        for record in Periodico.objects.filter(area__isnull=True,periodicoassunto__assunto=assunto):
            tot_areas_periodico = PeriodicoAssunto.objects.filter(periodico=record).count()
            if tot_areas_periodico < 3:
                print(record.issn)
                # tot_registros += Periodico.objects.filter(id=record.id,area__isnull=True).update(area=area)

        print(f'{tot_registros} alterados')
