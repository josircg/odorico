# Rotina que importa os países a partir do Portal ISSN
#
# Como esta rotina é muito custosa em termos de tráfego de rede, ela é realizada para determinadas áreas
# Josir 03/2024
#
# Executado em 03/2024 e 05/2025
# Substituido pelo atualizacao_portal_issn
# Depois da execução, deve-se rodar a limpeza dos Estados americanos, canadenses e australianos via SQL
#
from datetime import datetime, timedelta

from django.db import transaction
from django.core.management import BaseCommand

from qualis.models import Periodico, PeriodicoAssunto, Assunto, AreaConhecimento, PeriodicoISSN
from nucleo.apps import get_issn, validate_issn_code, log_object


class Command(BaseCommand):

    def normalize_issn_list(self, periodico, issn, meio):
        # Para cada item da lista, atualizar a classe PeriodicoISSN
        record, inserted = PeriodicoISSN.objects.get_or_create(periodico=periodico, issn=issn)
        record.meio = meio or record.meio or 'O'
        record.save()
        return

    def duplicado(self, issn):
        periodico = Periodico.objects.filter(issn=issn)
        if periodico:
            return True
        else:
            return False

    def handle(self, *args, **options):

        # Obtem os períodicos de uma determinada área que estão sem país
        assunto = Assunto.objects.get(schema__sigla='ASJC', cod_externo='3315')
        area = AreaConhecimento.objects.get(nome='COMUNICAÇÃO')
        transaction.set_autocommit(False)

        tot_registros = 0
        tot_gravados = 0
        tot_eissn = 0
        tot_issn_fixed = 0
        dtupdate = datetime.today() - timedelta(days=1)
        for periodico in Periodico.objects.filter(area=area, dtupdate__lt=dtupdate, pais__isnull=True):
            tot_registros += 1
            updated = False
            issn_record = get_issn(periodico.issn)
            if isinstance(issn_record, dict):
                issn_candidato = issn_record['issn']
                if issn_candidato != periodico.issn:
                    if self.duplicado(issn_candidato):
                        print(f'Duplicidade encontrada: {periodico.issn} / {issn_candidato}')
                        continue

                    periodico.eissn = periodico.issn
                    periodico.issn = issn_candidato
                    log_object(periodico, f'ISSN-L corrigido: Antigo ISSN-L {periodico.eissn}')
                    self.normalize_issn_list(periodico, periodico.issn, 'L')
                    meio = 'E' # Assume que o primeiro item da lista é o Eletrônico
                    for issn in issn_record['eissn_list']:
                        if issn != periodico.issn:
                            self.normalize_issn_list(periodico, issn, meio)
                        meio = None
                    updated = True
                    tot_issn_fixed += 1

                if issn_record['country'] and not periodico.pais:
                    periodico.pais = issn_record['country']
                    if not periodico.url and issn_record['url']:
                        periodico.url = issn_record['url']
                    updated = True
                    log_object(periodico, f'Country updated from ISSN Portal: {periodico.pais}')
                    tot_gravados += 1

                if not periodico.eissn and len(issn_record['eissn_list']):
                    issn = issn_record['eissn_list'][0]
                    if self.duplicado(issn):
                        print(f'Duplicidade encontrada! {issn_candidato} {issn}')
                        continue
                    else:
                        periodico.eissn = issn
                        log_object(periodico, f'EISSN encontrado: {issn}')
                        self.normalize_issn_list(periodico, issn, 'E')
                        tot_eissn += 1
                        updated = True
            else:
                print(f'ISSN not found {periodico.issn}')

            if updated:
                periodico.save()
                transaction.commit()

        print(f'{tot_registros} lidos')
        print(f'{tot_gravados} países alterados')
        print(f'{tot_issn_fixed} ISSNs corrigidos')
        print(f'{tot_eissn} EISSNs encontrados')
