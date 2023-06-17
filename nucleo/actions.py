from collections import Counter

from django.db.models import Count
from django.shortcuts import render
from django.utils.timezone import now

from nucleo.models import TipoProducao, ProducaoAutor
from nucleo.views import normaliza_matriz


def view_resumo_qualis(modeladmin, request, queryset):
    ultimos_anos = [now().year - i for i in range(4)]
    tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
    context = {}

    context['values'] = []
    context['soma'] = 0
    context['totalizadores'] = []
    context['labels'] = \
        [{'value': 'Programa', 'style': '500px;'},
         {'value': 'A1', 'style': '50px;'},
         {'value': 'A2', 'style': '50px;'},
         {'value': 'A3', 'style': '50px;'},
         {'value': 'A4', 'style': '50px;'},
         {'value': 'B1', 'style': '50px;'},
         {'value': 'B2', 'style': '50px;'},
         {'value': 'B3', 'style': '50px;'},
         {'value': 'B4', 'style': '50px;'},
         {'value': 'C', 'style': '50px;'},
         {'value': 'ND', 'style': '50px;'},
         {'value': 'NC', 'style': '50px;'},
         {'value': 'TOTAL', 'style': '50px;'},
         ]

    for programa in queryset:
        producoes = ProducaoAutor.objects.filter(autor__pesquisadorprograma__programa=programa,
                                                 producao__tipo=tipo_artigo, producao__ano__in=ultimos_anos). \
            values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))

        context['values'].append({
            'PROGRAMA': str(programa),
            **normaliza_matriz(producoes),
        })

    context['values'] = sorted(context['values'], key=lambda linha: linha['TOTAL'], reverse=True)
    context['titulo'] = 'Resumo Qualis dos Programas de %d a %d' % (ultimos_anos[-1], ultimos_anos[0])

    # calcula a totalização total de todos os programas
    totalizadores = context['values']
    count_total_geral = Counter()
    for totalizador in totalizadores:
        for qualis, count in totalizador.items():
            if not qualis == 'PROGRAMA':
                count_total_geral[qualis] += int(count)

    context['totalizadores'] = [{'TOTAL_PROGRAMAS': len(context['values']), **count_total_geral}]
    return render(request, 'resumo_programa_qualis.html', {'result': context})