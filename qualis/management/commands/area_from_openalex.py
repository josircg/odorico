# Rotina que importa a estrtura de tópicos do OpenAlex através da API
#

import requests

from django.conf import settings
from django.core.management import BaseCommand

from qualis.models import Schema, Assunto


class Command(BaseCommand):

    def handle(self, *args, **options):

        tot_incluidos = 0
        etiquette_header = {'from': settings.DEFAULT_FROM_EMAIL}
        domain_schema, _ = Schema.objects.get_or_create(sigla='OALEXD',defaults={'descricao':'OpenAlex Domains'})
        response = requests.get('https://api.openalex.org/domains', headers=etiquette_header)
        for domain in response.json()['results']:
            key = domain['id'].split('/')[-1]
            assunto, included = Assunto.objects.get_or_create(schema=domain_schema, cod_externo=key,
                                                    defaults={'descricao': domain['display_name']})
            assunto.nota = domain['description']
            assunto.save()
            if included:
                tot_incluidos += 1
        print(f'Total de Domínios incluídos: {tot_incluidos}')

        tot_incluidos = 0
        field_schema, _ = Schema.objects.get_or_create(sigla='OALEXF',defaults={'descricao':'OpenAlex Fields'})
        subfield_schema, _ = Schema.objects.get_or_create(sigla='OALEXS',defaults={'descricao':'OpenAlex Subfields'})
        for domain in Assunto.objects.filter(schema=domain_schema):
            response = requests.get(
                f'https://api.openalex.org/topics?group_by=field.id&filter=domain.id:{domain.cod_externo}',
                headers=etiquette_header
            )
            if response.status_code == 200:
                topics = response.json()['group_by']
                for topic in topics:
                    key = topic['key'].split('/')[-1]
                    assunto, insert = Assunto.objects.get_or_create(schema=field_schema, cod_externo=key, parent=domain,
                                                                    defaults={'descricao': topic['key_display_name']})
                    if insert:
                        tot_incluidos += 1
                    response = requests.get(
                        f'https://api.openalex.org/topics?group_by=subfield.id&filter=field.id:{key}',
                        headers = etiquette_header
                    )
                    # verifica se o resultado tem mais de uma página
                    # nesse caso, deve-se alterar o algoritmo que assume que só existe uma página
                    subtopics = response.json()
                    if subtopics["meta"]["groups_count"] > subtopics["meta"]["per_page"]:
                        print(f'Mais de uma página {key}')
                    for subtopic in subtopics['group_by']:
                        key = subtopic['key'].split('/')[-1]
                        _, insert = Assunto.objects.get_or_create(
                            schema=subfield_schema, cod_externo=key,
                            parent=assunto,
                            defaults={'descricao': subtopic['key_display_name']})
                        if insert:
                            tot_incluidos += 1

        print(f'{tot_incluidos} registros incluídos')
