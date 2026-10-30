from django.core.management.base import BaseCommand
from nucleo.models import Matricula, CursoControle


def gera_numero_matricula():
    count = 0
    for matricula in Matricula.objects.filter(numero__startswith='-').order_by('id'):
        if matricula.curso.controle_matricula:
            controle, _ = CursoControle.objects.get_or_create(ano=matricula.ingresso, controle=matricula.curso.controle_matricula)
            controle.sequencial += 1
            controle.save()
            matricula.numero = controle.numero()
            matricula.save()
            print(matricula.numero)
            count += 1
    print(f'Novas matrículas geradas: {count}')



class Command(BaseCommand):
    label = 'Agendamentos diários'

    def handle(self, *args, **options):
        gera_numero_matricula()
