import csv
import json

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from escola.models import Inscricao, Modulo, Curso, Discente, Contato, ContatoAgenda, ModuloSessao
from escola.views import somente_os_maiores, transform_dataset_display
from utils.stdlib import get_display_str


def build_grouped_dashboards(dashboards):
    """
    Gerador de dashboards agrupados
    Espera uma lista de dicionários contendo os dashboards no formato {
    """

    data = []
    for dash in dashboards:
        grouped_queryset = dash['queryset']
        mapper = {
            'title': dash['title'],
            'x': list(item[dash['field']] for item in grouped_queryset),
            'y': list(item['quantidade'] for item in grouped_queryset)
        }
        data.append(mapper)
    return data


def modulo_dash_resultados(request, modulo_id):
    modulo = Modulo.objects.get(id=modulo_id)
    context = {'title': f'{modulo} - Resultados'}
    inscricoes_count = Inscricao.objects.filter(curso__modulo_id=modulo_id, status=Inscricao.Status.ATIVA).exclude(
        curso__tipo__descricao='Evento').count()
    cursos = Curso.objects.filter(modulo_id=modulo_id)
    min_curso = cursos.order_by('id').first()
    cursos_count = cursos.exclude(tipo__descricao='Evento').count()

    alunos = Discente.objects.filter(inscricao__curso__modulo_id=modulo_id,
                                     inscricao__status=Inscricao.Status.ATIVA).select_related()
    alunos_count = alunos.distinct().count()

    # Conta primeiro os alunos que se registraram pela primeira vez neste módulo
    novos_alunos = Discente.objects.filter(inscricao__curso__modulo_id=modulo_id,
                                           contato__curso_origem__gte=min_curso,
                                           inscricao__status=Inscricao.Status.ATIVA
                                           ).values('contato__origem').annotate(
        quantidade=Count('id', distinct=True)).order_by('-quantidade')
    novos_alunos = list(novos_alunos)
    novos_count = sum(item['quantidade'] for item in novos_alunos)
    # adiciona os que já são alunos
    novos_alunos.append({'contato__origem': 'Já Discentes', 'quantidade': alunos_count - novos_count})
    total_por_origem = somente_os_maiores(novos_alunos, 'contato__origem', 'quantidade')

    novos_alunos = Discente.objects.filter(inscricao__curso__modulo_id=modulo_id,
                                           contato__curso_origem__gte=min_curso,
                                           inscricao__status=Inscricao.Status.ATIVA
                                           ).values('contato__utm_source').annotate(
        quantidade=Count('id', distinct=True))
    novos_alunos = list(novos_alunos)
    novos_count = sum(item['quantidade'] for item in novos_alunos)
    novos_alunos.append({'contato__utm_source': 'Já discentes', 'quantidade': alunos_count - novos_count})
    total_por_utm = somente_os_maiores(novos_alunos, 'contato__utm_source', 'quantidade')

    total_por_curso = list(alunos.values('inscricao__curso__nome').annotate(
        quantidade=Count('id', distinct=True)))

    total_por_localidade = list(alunos.filter(localidade__isnull=False).values('localidade').annotate(
        quantidade=Count('id', distinct=True)))
    total_por_localidade = somente_os_maiores(total_por_localidade, 'localidade', 'quantidade')

    total_por_formacao = list(alunos.filter(formacao__isnull=False).values('formacao').annotate(
        quantidade=Count('id', distinct=True)))
    total_por_formacao = transform_dataset_display(total_por_formacao, Discente, ['formacao', ])
    total_por_formacao = somente_os_maiores(total_por_formacao, 'formacao', 'quantidade')

    dashboards = [
        {
            'title': 'Total de Alunos pro Curso',
            'field': 'inscricao__curso__nome',
            'queryset': total_por_curso,
        },
        {
            'title': 'Total de Alunos pela Origem',
            'field': 'contato__origem',
            'queryset': total_por_origem,
        },
        {
            'title': 'Origem via URL',
            'queryset': total_por_utm,
            'field': 'contato__utm_source',
        },
        {
            'title': 'Total por Cidade',
            'queryset': total_por_localidade,
            'field': 'localidade',
        },
        {
            'title': 'Total por Formação',
            'queryset': total_por_formacao,
            'field': 'formacao',
        }
    ]

    context['dashboards'] = json.dumps(build_grouped_dashboards(dashboards))

    context['counters'] = [
        {'title': 'Total de Cursos/Trilhas', 'value': cursos_count},
        {'title': 'Total de Inscrições', 'value': inscricoes_count},
        {'title': 'Total de Alunos', 'value': alunos_count},
        {'title': 'Média de Alunos por curso',
         'value': inscricoes_count / cursos_count if cursos_count > 0 else 0},
    ]

    return render(request, 'dashboard_resultados.html', context=context)


def modulo_exportacao_csv(request, modulo_id):
    menor_curso = Curso.objects.filter(modulo_id=modulo_id).order_by('id').first()
    if menor_curso:
        menor_curso = menor_curso.id
    else:
        messages.error(request, 'Nenhum curso cadastrado para este módulo')
        return HttpResponseRedirect(reverse('admin:escola_modulo_change', args=(modulo_id,)))

    fieldnames = ['curso__nome', 'discente__nome', 'discente__email', 'discente__sexo', 'discente__cep',
                  'discente__UF', 'discente__localidade',
                  'discente__formacao', 'discente__id_cnpq', 'discente__validado', 'discente__id', 'presenca',
                  ]
    dataset = Inscricao.objects.filter(curso__modulo_id=modulo_id,
                                       status=Inscricao.Status.ATIVA).select_related('curso', 'discente').values(
        *fieldnames
    )
    fieldnames += ['utm_source', 'origem']
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inscricoes.csv"'
    csv_intl = csv.writer(response, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_intl.writerow(fieldnames)
    tot_registros = 0
    for inscricao in dataset:
        contato = Contato.objects.filter(discente=inscricao['discente__id']).first()
        record = dict(inscricao)
        record['discente__formacao'] = get_display_str(record['discente__formacao'], Discente, 'formacao')
        fields = list(record.values())
        if contato.curso_origem.id >= menor_curso:
            fields += [contato.utm_source, contato.origem]
        else:
            fields += [contato.utm_source, 'Discente']
        csv_intl.writerow(fields)
        tot_registros += 1

    messages.info(request, f'{tot_registros} inscrições exportadas')
    return response


def trilha_planilha(request):
    trilhas_ids = request.GET.getlist('trilha')
    fieldnames = ['trilha__nome', 'dia', 'hora_inicial', 'titulo', 'trabalhos', 'busca']

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="trilhas.csv"'
    csv_intl = csv.writer(response, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    csv_intl.writerow(fieldnames)
    tot_registros = 0
    for trilha in ModuloSessao.objects.filter(trilha__id__in=trilhas_ids).values(*fieldnames).order_by('trilha__nome', 'dia', 'hora_inicial'):
        record = dict(trilha)
        fields = list(record.values())
        csv_intl.writerow(fields)
        tot_registros += 1

    messages.info(request, f'{tot_registros} trilhas exportadas')
    return response


def modulo_dash_checkin(request):
    context = {'title': 'Estatísticas de Check-in'}
    trilhas_ids = request.GET.getlist('trilha')

    contato_agenda = ContatoAgenda.objects.all()

    # ====== GRÁFICO 1: Total por Trilha ======
    total_por_trilha = (
        contato_agenda.filter(sessao__trilha_id__in=trilhas_ids)
        .values('sessao__trilha__id', 'sessao__trilha__nome')
        .annotate(total=Count('id'))
        .order_by('sessao__trilha__nome')
    )

    # ====== GRÁFICO 2: Total por Dia ======
    total_por_dia = (
        contato_agenda
        .values('sessao__dia')
        .annotate(total=Count('id'))
        .order_by('sessao__dia')
    )

    dashboards = [
        {
            'title': 'Contatos por Trilha',
            'x': [item['sessao__trilha__nome'].split('-')[0] for item in total_por_trilha],
            'y': [item['total'] for item in total_por_trilha.values('total')],
        },
        {
            'title': 'Contatos por Dia',
            'x': [item['sessao__dia'].strftime('%d/%m/%Y') for item in total_por_dia],
            'y': [item['total'] for item in total_por_dia],
        },
    ]
    context['dashboards'] = json.dumps(dashboards)

    context['counters'] = [
        {'title': 'Total de Usuários', 'value': contato_agenda.values('cookie').distinct().count()},
        {'title': 'Total de CheckIns', 'value': contato_agenda.count()}
    ]

    return render(request, 'dashboard_resultados.html', context=context)
