from django.core.management import BaseCommand
from django.db.models import Count

from nucleo.models import Producao, ProducaoAutor


class Command(BaseCommand):
    label = 'Verifica as produções com hashs duplicados'

    def handle(self, *args, **options):
        total_prod_duplicadas, total_autores_associados, total_items_lidos = 0, 0, 0
        for dup in Producao.objects.all().values('ident_unico').annotate(cnt=Count('ident_unico')).filter(cnt__gte=2):
            dset = Producao.objects.filter(ident_unico=dup['ident_unico'])
            pub_base = None
            for pub in dset:
                if pub.ano:  # critério para saber qual é a publicação base.
                    pub_base = pub
                    break

            # Merge
            if pub_base:
                for pub_duplicada in dset.exclude(id=pub_base.id):
                    # move os autores para a publicação base (testando se já não existe)
                    if not ProducaoAutor.objects.filter(autor=pub_duplicada.pesquisador, producao=pub_base).exists():
                        ProducaoAutor.objects.create(
                            autor=pub_duplicada.pesquisador,
                            producao=pub_base,
                        )
                        total_autores_associados += 1
                    pub_duplicada.delete()
                    total_prod_duplicadas += 1

            total_items_lidos += 1

        print('Total de produções duplicadas: ', total_prod_duplicadas)
        print('Total de produções lidas: ', total_items_lidos)
        print('Total de produções excluidas: ', total_prod_duplicadas)
        print('Total de autores associados a produções: ', total_autores_associados)