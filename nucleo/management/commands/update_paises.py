from django.core.management.base import BaseCommand
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType

from nucleo.models import Producao
from chupalattes import obtem_dt_cnpq, url_cnpq, get_lista_paises, find_pais


class Command(BaseCommand):
    label = 'Atualiza o status de atualização do Lattes via CNPQ'

    def add_arguments(self, parser):
        parser.add_argument('id', type=int, help='Id da Produção', nargs='?', default=None)

    # Corrige o status de conclusão do curso dos alunos
    def handle(self, *args, **options):
        tot_reg = 0
        tot_semcnpq = 0
        tot_lidos = 0
        loguser = User.objects.get_or_create(username='sys')[0]
        type_id = ContentType.objects.get(model='Producao').id

        id = options['id']
        if id:
            dset = Producao.objects.filter(id=id)
        else:
            dset = Producao.objects.filter(pais__isnull=True)

        paises = get_lista_paises()

        for producao in dset:
            tot_lidos += 1
            pais = find_pais(producao.titulo, paises)
            if pais:
                producao.pais = pais
                producao.save()
                tot_reg += 1
            else:
                producao.pais = None
                producao.save()

        print('Produções lidas: %d' % tot_lidos)
        print('Produções atualizadas: %d' % tot_reg)
