from django.core.management.base import BaseCommand
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType

from nucleo.models import Pesquisador
from chupalattes import obtem_dt_cnpq, url_cnpq


class Command(BaseCommand):
    label = 'Atualiza o status de atualização do Lattes via CNPQ'

    def add_arguments(self, parser):
        parser.add_argument('id', type=int, help='Id do Pesquisador', nargs='?', default=None)

    # Corrige o status de conclusão do curso dos alunos
    def handle(self, *args, **options):
        tot_reg = 0
        tot_semcnpq = 0
        tot_lidos = 0
        loguser = User.objects.get_or_create(username='sys')[0]
        type_id = ContentType.objects.get(model='Pesquisador').id

        id = options['id']
        if id:
            dset = Pesquisador.objects.filter(id=id)
        else:
            dset = Pesquisador.objects.filter(status='A')

        for pesquisador in dset:
            tot_lidos += 1
            if pesquisador.id_cnpq:
                dt_cnpq = obtem_dt_cnpq(url_cnpq % pesquisador.id_cnpq)
                if dt_cnpq and dt_cnpq > pesquisador.dtupdate:
                    pesquisador.atualizado = False
                    pesquisador.save()
                    tot_reg += 1
            else:
                tot_semcnpq += 1
        print('Pesquisadores analisados: %d' % tot_lidos)
        print('Pesquisadores sem ID CNPQ que não foram atualizados: %d' % tot_semcnpq)
        print('Pesquisadores atualizados: %d' % tot_reg)
