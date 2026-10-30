import csv
from collections import Counter

from django.contrib import messages
from django.db import connection
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils.timezone import now

from nucleo.models import TipoProducao, ProducaoAutor, Producao, Pesquisador, PesquisadorNomeCitacao, \
    PesquisadorProjeto, PesquisadorPrograma, Programa, Matricula, Curso, GrupoPesquisa, PesquisadorGrupo
from utils.stdlib import nvl


def mapa_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="mapa.csv"'

    # obtem os pesquisadores que farão parte do relatório
    id = request.GET['id']
    programa = Programa.objects.filter(id=id)
    if not programa.exists():
        messages.error(request, 'Programa %d não encontrado' % id)
        return redirect('/admin')

    queryset = programa.values_list('pesquisadorprograma__pesquisador__nome', flat=True). \
        order_by('pesquisadorprograma__pesquisador__nome')

    fieldnames = ['id_lattes', 'tipo', 'titulo', 'doi', 'pais']
    csv_intl = csv.DictWriter(response, fieldnames=fieldnames, delimiter=',', quotechar='"',
                              quoting=csv.QUOTE_MINIMAL)
    csv_intl.writeheader()

    for pesq in queryset:
        for producao in Producao.objects.filter(pesquisador__nome__exact=pesq, ano__in=(2017, 2018, 2019, 2020),
                                                pais__isnull=False):
            csv_intl.writerow(
                {"id_lattes": producao.pesquisador.id_lattes, "tipo": producao.tipo, "titulo": producao.titulo,
                 'doi': producao.doi})
        for producao in Producao.objects.filter(pesquisador__nome__exact=pesq,
                                                ano__in=(2017, 2018, 2019, 2020),
                                                pais__isnull=False):
            csv_intl.writerow({"id_lattes": producao.pesquisador.id_lattes,
                               "tipo": producao.tipo,
                               "titulo": producao.titulo,
                               "doi": producao.doi,
                               "pais": producao.pais})
    return response


def normaliza_matriz(queryset):
    matriz_default = {'A1': 0, 'A2': 0, 'A3': 0, 'A4': 0, 'B1': 0, 'B2': 0, 'B3': 0, 'B4': 0, 'C': 0,
                      'ND': 0, 'NC': 0, 'TOTAL': 0}
    for rec in queryset:
        qualis = rec['producao__periodico__qualis']
        count = rec['cnt']
        if nvl(qualis, '*') in matriz_default:
            matriz_default[qualis] = count
        else:
            matriz_default['ND'] = count

        matriz_default['TOTAL'] += count

    return matriz_default


qualis_header = [
    {'value': 'Programa', 'style': '500px;'},
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


# Totalização por Programa
def view_resumo_qualis(modeladmin, request, queryset):
    quadrienio = [now().year - i for i in range(4)]
    tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
    context = {'values': [], 'soma': 0, 'totalizadores': [], 'labels': qualis_header}

    for programa in queryset:
        producoes = ProducaoAutor.objects.filter(autor__pesquisadorprograma__programa=programa,
                                                 producao__tipo=tipo_artigo, producao__ano__in=quadrienio). \
            values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))

        context['values'].append({
            'PROGRAMA': str(programa),
            **normaliza_matriz(producoes),
        })

    context['values'] = sorted(context['values'], key=lambda linha: linha['TOTAL'], reverse=True)
    context['titulo'] = 'Resumo Qualis dos Programas de %d a %d' % (quadrienio[0], quadrienio[-1])

    # calcula a totalização total de todos os programas
    totalizadores = context['values']
    count_total_geral = Counter()
    for totalizador in totalizadores:
        for qualis, count in totalizador.items():
            if not qualis == 'PROGRAMA':
                count_total_geral[qualis] += int(count)

    context['totalizadores'] = [{'TOTAL_PROGRAMAS': len(context['values']), **count_total_geral}]
    return render(request, 'resumo_programa_qualis.html', {'result': context})


# Totalização dos professores/discentes de um programa específico
def resumo_qualis(request, programa_id, curso_id=0):
    context = {}
    result = []
    context['labels'] = qualis_header
    context['labels'][0]['value'] = 'Pesquisador'
    quadrienio = [now().year - i for i in range(4)]
    tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
    total_pesquisadores = 0
    matriz = None
    try:
        # tipo:0-Docente, n-Curso
        if curso_id == 0:
            programa = Programa.objects.get(id=programa_id)
            descricao = programa.descricao
            for r in PesquisadorPrograma.objects.filter(programa=programa):
                total_pesquisadores += 1
                producoes = ProducaoAutor.objects.filter(autor=r.pesquisador, producao__tipo=tipo_artigo,
                                                         producao__ano__in=quadrienio). \
                    values('producao__periodico__qualis').annotate(cnt=Count('producao__id'))

                matriz = normaliza_matriz(producoes)
                result.append({
                    'Pesquisador': r.pesquisador.nome,
                    **matriz
                })
            producoes = ProducaoAutor.objects.filter(autor__pesquisadorprograma__programa=programa,
                                                     producao__tipo=tipo_artigo, producao__ano__in=quadrienio). \
                values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))
        else:
            curso = Curso.objects.get(id=curso_id)
            descricao = f'{curso.programa.descricao} - Curso {curso.descricao}'

            from django.db.models import Q
            limite = Q(dtconclusao__year__isnull=True) | Q(dtconclusao__year__lte=quadrienio[-1])
            for r in Matricula.objects.filter(limite, curso=curso_id):
                total_pesquisadores += 1
                producoes = ProducaoAutor.objects.filter(autor=r.pesquisador, producao__tipo=tipo_artigo,
                                                         producao__ano__in=quadrienio). \
                    values('producao__periodico__qualis').annotate(cnt=Count('producao__id'))

                matriz = normaliza_matriz(producoes)
                result.append({
                    'Pesquisador': r.pesquisador.nome,
                    **matriz
                })

            limite = (Q(autor__matricula__dtconclusao__year__isnull=True) |
                      Q(autor__matricula__dtconclusao__year__lte=quadrienio[-1]))
            producoes = ProducaoAutor.objects.filter(limite, autor__matricula__curso_id=curso_id,
                                                     producao__tipo=tipo_artigo, producao__ano__in=quadrienio). \
                values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))

        result = sorted(result, key=lambda i: i['Pesquisador'])

        context['values'] = result
        context['soma'] = total_pesquisadores
        tipo = 'Docentes' if curso_id == 0 else 'Discentes'

        context['titulo'] = 'Resumo Qualis de %d a %d - %s (%s)' % (quadrienio[-1], quadrienio[0],
                                                                    descricao, tipo)
        matriz = normaliza_matriz(producoes)
        context['totalizadores'] = [{
            'TOTAL_PESQUISADORES': context['soma'],
            **matriz
        }]

    except Programa.DoesNotExist:
        context['titulo'] = f'Programa {programa_id} não encontrado.'
        context['labels'] = []

    except Curso.DoesNotExist:
        context['titulo'] = f'Curso {curso_id} não encontrado.'
        context['labels'] = []

    if request.POST:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="resumo_qualis.csv"'
        header = list(map(lambda la: la['value'], context['labels']))
        csv_intl = csv.DictWriter(response, fieldnames=header, delimiter=',', quotechar='"',
                                  quoting=csv.QUOTE_MINIMAL)
        csv_intl.writeheader()

        for row in result:
            csv_intl.writerow(row)

        csv_intl.writerow(matriz)

        return response

    else:
        return render(request, 'resumo_qualis.html', {'result': context})


# Totalização dos pesquisadores de um grupo de pesquisa
def resumo_grupo(request, grupo_id, anos=4):
    context = {}
    result = []
    context['labels'] = qualis_header
    context['labels'][0]['value'] = 'Pesquisador'
    quadrienio = [now().year - i for i in range(anos)]
    tipo_artigo = TipoProducao.objects.get(cod_externo='artigo')
    total_pesquisadores = 0
    matriz = None
    try:
        grupo = GrupoPesquisa.objects.get(id=grupo_id)
        descricao = f'{grupo.nome}'

        from django.db.models import Q
        for r in PesquisadorGrupo.objects.filter(grupo=grupo):
            total_pesquisadores += 1
            producoes = ProducaoAutor.objects.filter(autor=r.pesquisador, producao__tipo=tipo_artigo,
                                                     producao__ano__in=quadrienio). \
                values('producao__periodico__qualis').annotate(cnt=Count('producao__id'))

            matriz = normaliza_matriz(producoes)
            result.append({
                'Pesquisador': r.pesquisador.nome,
                **matriz
            })

        limite = (Q(autor__matricula__dtconclusao__year__isnull=True) |
                  Q(autor__matricula__dtconclusao__year__lte=quadrienio[-1]))
        producoes = ProducaoAutor.objects.filter(limite, autor__pesquisadorgrupo__grupo_pesquisa__in=grupo_id,
                                                 producao__tipo=tipo_artigo, producao__ano__in=quadrienio). \
            values('producao__periodico__qualis').annotate(cnt=Count('producao__id', distinct=True))

        result = sorted(result, key=lambda i: i['Pesquisador'])

        context['values'] = result
        context['soma'] = total_pesquisadores
        tipo = 'Pesquisador'

        context['titulo'] = 'Resumo Qualis de %d a %d - %s (%s)' % (quadrienio[-1], quadrienio[0],
                                                                    descricao, tipo)
        matriz = normaliza_matriz(producoes)
        context['totalizadores'] = [{
            'TOTAL_PESQUISADORES': context['soma'],
            **matriz
        }]

    except GrupoPesquisa.DoesNotExist:
        context['titulo'] = f'Grupo {grupo_id} não encontrado.'
        context['labels'] = []

    if request.POST:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="resumo_qualis.csv"'
        header = list(map(lambda la: la['value'], context['labels']))
        csv_intl = csv.DictWriter(response, fieldnames=header, delimiter=',', quotechar='"',
                                  quoting=csv.QUOTE_MINIMAL)
        csv_intl.writeheader()

        for row in result:
            csv_intl.writerow(row)

        csv_intl.writerow(matriz)

        return response

    else:
        return render(request, 'resumo_qualis.html', {'result': context})


def exportar_grupo(request, grupo_id):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="resumo_qualis.csv"'
    dset = Producao.objects.filter(pesquisador__pesquisadorgrupo__grupo_pesquisa_id=grupo_id)
    header = list(dset.values()[0])
    csvw = csv.DictWriter(response, fieldnames=header, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csvw.writeheader()
    for row in dset:
        csvw.writerow(row)

    return response


def dashboard_grupo(request, grupo_id):
    area_data = [
        { "label": "Jan", "y": 10000 },
        { "label": "Feb", "y": 30162 },
        { "label": "Mar", "y": 26263 },
        { "label": "Apr", "y": 18394 },
        { "label": "May", "y": 18287 },
        { "label": "Jun", "y": 28682 },
        { "label": "Jul", "y": 31274 },
        { "label": "Aug", "y": 33259 },
        { "label": "Sep", "y": 25849 },
        { "label": "Oct", "y": 24159 },
        { "label": "Nov", "y": 32651 },
        { "label": "Dec", "y": 31984 }
    ]
    column_data = [
        {"label": "January", "y": 42150 },
        {"label": "February", "y": 53120 },
        {"label": "March", "y": 62510 },
        {"label": "April", "y": 78410 },
        {"label": "May", "y": 98210 },
        {"label": "June", "y": 149840 }
    ]
    pie_data = [
        {"y": 12.21, "name": "Blue", "color": "#007bff" },
        {"y": 15.58, "name": "Red", "color": "#dc3545" },
        {"y": 11.25, "name": "Yellow", "color": "#ffea00" },
        {"y": 8.32, "name": "Green", "color": "#28a745" }
    ]
    # icon: fa-comments, fa-list, fa-support, etc
    cards = [
        {"color": "blue", "icon": "fa-comments", "title": "TOTAL DE ALUNOS", "value": 160, 'link': "#"},
        {"color": "green", "icon": "fa-list", "title": "TOTAL DE ARTIGOS", "value": 230, 'link': "#"}
    ]
    return render(request, 'dashboard.html',
                  {"navbar": False,
                   "title": "Produção do Grupo de Pesquisa",
                   "cards": cards,
                   "area_data": area_data, "column_data": column_data, "pie_data": pie_data })


def dashboard_resumo(request, grupo_id):
    area_data = [
        { "label": "Jan", "y": 10000 },
        { "label": "Feb", "y": 30162 },
        { "label": "Mar", "y": 26263 },
        { "label": "Apr", "y": 18394 },
        { "label": "May", "y": 18287 },
        { "label": "Jun", "y": 28682 },
        { "label": "Jul", "y": 31274 },
        { "label": "Aug", "y": 33259 },
        { "label": "Sep", "y": 25849 },
        { "label": "Oct", "y": 24159 },
        { "label": "Nov", "y": 32651 },
        { "label": "Dec", "y": 31984 }
    ]
    column_data = [
        {"label": "January", "y": 42150 },
        {"label": "February", "y": 53120 },
        {"label": "March", "y": 62510 },
        {"label": "April", "y": 78410 },
        {"label": "May", "y": 98210 },
        {"label": "June", "y": 149840 }
    ]
    pie_data = [
        {"y": 12.21, "name": "Blue", "color": "#007bff" },
        {"y": 15.58, "name": "Red", "color": "#dc3545" },
        {"y": 11.25, "name": "Yellow", "color": "#ffea00" },
        {"y": 8.32, "name": "Green", "color": "#28a745" }
    ]
    return render(request, 'dashboard.html',
                  {"navbar": False,
                   "title": "Produção do Programa",
                   "area_data": area_data, "column_data": column_data, "pie_data": pie_data })


def resumo_teses(request, ano_base):
    texto = ''
    docente = ''
    with connection.cursor() as cursor:
        cursor.execute(
 "select po.nome, c.descricao, p.nome, m.titulo, m.id"
 " from nucleo_matricula m, nucleo_pesquisador p, nucleo_orientacao o, nucleo_pesquisador po, nucleo_curso c"
 " where m.pesquisador_id = p.id"
 "  and m.status = 'C'"
 "  and m.id = o.matricula_id"
 " and o.status = 'C' and coorientacao = 'F'"
 "  and o.orientador_id = po.id"
 "  and m.curso_id = c.id"
 "  and year(dtdefesa) >= %s"
 " order by po.nome, m.curso_id, dtdefesa", [ano_base])
        for matricula in cursor.fetchall():
            if matricula[0] != docente:
                docente = matricula[0]
                texto += '<br/><br/><b>'+docente.title()+'</b> orientou as/os seguintes discentes:<br/>'
            texto += matricula[2].title()+' ('+matricula[1]+') '
            if matricula[3]:
                texto += 'com o título "'+matricula[3]+'"; '
            else:
                texto += '<b><a href="/admin/nucleo/matricula/'+str(matricula[4])+'">(Sem título)</a></b>; '
    return HttpResponse(f'<html><body>{texto}</body></html>')