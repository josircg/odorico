import datetime

from django.core.management.base import BaseCommand

from nucleo.models import *


class Command(BaseCommand):
    label = 'Cria estrutura de professores do ENACIN'

    def add_arguments(self, parser):
        parser.add_argument('--programa', type=str, help='ID do Programa')

    # Corrige produções sem autor original
    def handle(self, *args, **options):

        if hasattr(settings, 'ESCOLA'):
            print('A variável ESCOLA já está definida no settings. Verifique')

        escola, nova = Instituicao.objects.get_or_create(nome='Escola Nacional de Ciência da Informação',
                                                         sigla='ENACIN')
        escola.save()
        if nova:
            print(f'Adicione no local.py a variável ESCOLA={escola.id}')

        if options['programa']:
            programa = Programa.objects.filter(id=options['programa']).first()
            if programa:
                print(f'Programa {programa.descricao}')
            else:
                print('Programa não encontrado')
                return

            tot_professores = 0
            for record in PesquisadorPrograma.objects.filter(programa_id=options['programa']):
                today = datetime.date.today()
                p, novo = PesquisadorInstituicao.objects.get_or_create(
                            pesquisador=record.pesquisador, instituicao=escola, defaults={'dt_entrada': today})
                p.save()
                if novo:
                    tot_professores += 1

            print(f'Total de professores incluidos: {tot_professores}')



