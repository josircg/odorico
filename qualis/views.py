import json
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import MultipleObjectsReturned
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.clickjacking import xframe_options_exempt

from odorico import local
from utils import email
from .forms import *
from .models import Periodico, AreaConhecimento, Assunto, PeriodicoAssunto


def import_csv(texto, request):
    return True


@login_required
def importacao_periodicos(request):
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            texto = form.cleaned_data['arquivo']
            if import_csv(texto, request):
                return redirect('/importacao_periodicos/')
            else:
                messages.error(request, 'ID não encontrado')
                return render(request, 'importacao_periodicos.html', {'form': form})

    else:
        form = ImportForm()

    return render(request, 'import_periodicos.html', {'form': form})


@xframe_options_exempt
def periodicos(request):

    if request.method == 'POST':
        form_data = request.POST
        from_email = getattr(local, 'DEFAULT_FROM_EMAIL')
        email_usuario = form_data.get('email')
        sugestao = form_data.get('sugestao')
        email.sendmail('Sugestão de Periódicos', [
                       from_email, email_usuario], message=sugestao)
        messages.success(request, 'Pedido enviado com sucesso!')
        return redirect('/periodicos')

    context = {}

    area = int(request.GET.get('area', 0))
    issn_search = request.GET.get('issn_search', '').replace(" ", "")
    revista_search = request.GET.get('revista_search', '')
    assunto = int(request.GET.get('assunto', 0))
    diamond_check = request.GET.get('diamond_check', None)
    keyword_check = request.GET.get('keyword_check', None)
    area_manual = request.GET.get('area_manual') == '1'
    initial_load = request.method == 'GET' and not request.GET

    if not area_manual and area == 2 and (issn_search or revista_search or assunto or diamond_check or keyword_check):
        area = 0

    has_filters = bool(issn_search or revista_search or area or assunto or diamond_check or keyword_check)

    if has_filters:
        if issn_search:
            dataset = Periodico.objects.filter(Q(issn__exact=issn_search) | Q(eissn__exact=issn_search))
        else:
            if assunto:
                dataset = Periodico.objects.filter(periodicoassunto__assunto_id=assunto)
            else:
                dataset = Periodico.objects.all()

            if area:
                dataset = dataset.filter(area__id__exact=area)

            if diamond_check:
                dataset = dataset.filter(modelo_economico='D')

            if revista_search:
                # primeiro procure por palavras dentro das aspas
                palavras = re.findall(r'"([^"]*)"', revista_search)
                palavras += re.sub(r'"([^"]*)"', '', revista_search).split()
                for termo in palavras:
                    if termo[0] == '-':
                        if keyword_check:
                            dataset = dataset.exclude(Q(keywords__icontains=termo[1:]) | Q(nome__icontains=termo[1:]))
                        else:
                            dataset = dataset.exclude(nome__icontains=termo[1:])
                    else:
                        if keyword_check:
                            dataset = dataset.filter(Q(keywords__icontains=termo) | Q(nome__icontains=termo))
                        else:
                            dataset = dataset.filter(nome__icontains=termo)

        context['area_select'] = area
        context['area_manual'] = area_manual
    else:
        if initial_load:
            dataset = Periodico.objects.filter(area__id__exact=2).order_by('qualis', 'issn')
            context['area_select'] = 2
            context['area_manual'] = False
        else:
            dataset = Periodico.objects.all()
            context['area_select'] = 0
            context['area_manual'] = False

    context['assunto_select'] = assunto
    context['search_issn'] = issn_search
    context['search_revista'] = revista_search
    context['diamond_check'] = diamond_check
    context['keyword_check'] = keyword_check

    ordering = request.GET.get('ordering', [])

    if ordering:
        ordering = ordering.split('.')
        dataset = dataset.order_by(*ordering)
    else:
        dataset = dataset.order_by('qualis', 'issn')

    per_page_raw = (request.GET.get('per_page', '25') or '25').strip().lower()

    context['area'] = list(AreaConhecimento.objects.filter(id__in=(1, 2, 3, 9)))
    context['assuntos'] = list(Assunto.objects.filter(schema__sigla='ASJC').
                               values('id', 'descricao').order_by('descricao'))
    labels = [
        {'label': 'NOME COMPLETO', 'value': 'nome', 'hint': None},
        {'label': 'ISSN', 'value': 'issn', 'hint': None},
        {'label': 'QUALIS', 'value': 'qualis', 'hint': '2021-2024'},
        {'label': 'E-ISSN', 'value': 'eissn'},
        {'label': 'MODELO', 'value': 'modelo_economico',
            'hint': 'Diamond, APC or Locked'},
        {'label': 'OpenAlex H5', 'class': 'align-right',
            'value': 'oalex_h5', 'hint': '2024'},
        {'label': 'Google H5', 'class': 'align-right',
            'value': 'google_h5', 'hint': '2020'},
        {'label': 'CITESCORE', 'class': 'align-right',
            'value': 'citescore', 'hint': '2022'},
        {'label': 'SJR', 'class': 'align-right', 'value': 'sjr', 'hint': '2024'}
    ]

    sort_params = request.GET.copy()
    if 'ordering' in sort_params:
        sort_params.pop('ordering')
    if 'page' in sort_params:
        sort_params.pop('page')
    extra_params = sort_params.urlencode()
    # Monta o order by mantendo os parâmetros extras da querystring
    for i in labels:
        current_field = i.get('value')
        sort_field = None
        sort_list = []
        # Monta a lista de campos sem o campo atual
        for field in ordering:
            if current_field != field and f'-{current_field}' != field:
                sort_list.append(field)
            else:
                sort_field = field
        # 1 - adiciona desc, 2 - adiciona asc, 3 - não insere no order by
        if sort_field is None:
            sort_list.insert(0, f'-{current_field}')
        elif sort_field == f'-{current_field}':
            sort_list.insert(0, current_field)

        if sort_list and extra_params:
            i['order'] = extra_params + '&ordering=' + '.'.join(sort_list)
        elif sort_list:
            i['order'] = 'ordering=' + '.'.join(sort_list)
        else:
            i['order'] = extra_params

    context['labels'] = labels
    result = []
    total_items = dataset.count()
    if per_page_raw == 'all':
        per_page = max(total_items, 1)
        selected_per_page = 'all'
    else:
        try:
            per_page = int(per_page_raw)
        except (TypeError, ValueError):
            per_page = 25
        if per_page <= 0:
            per_page = 25
        per_page = min(per_page, 200)
        selected_per_page = str(per_page)

    paginator = Paginator(dataset, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    qualis_rank = {
        'A1': 1,
        'A2': 2,
        'A3': 3,
        'A4': 4,
        'B1': 5,
        'B2': 6,
        'B3': 7,
        'B4': 8,
        'C': 9,
        'ND': 10,
    }
    page_data = page_obj.object_list
    for reg in page_data:
        current_qualis = reg.qualis or 'ND'
        previous_qualis = reg.qualis_ant or 'ND'

        if previous_qualis == 'ND' and current_qualis != 'ND':
            qualis_indicator = 'new'
        else:
            current_rank = qualis_rank.get(current_qualis)
            previous_rank = qualis_rank.get(previous_qualis)
            if current_rank is None or previous_rank is None or current_rank == previous_rank:
                qualis_indicator = 'same'
            elif current_rank < previous_rank:
                qualis_indicator = 'up'
            else:
                qualis_indicator = 'down'

        result.append({
            'nome': reg.nome,
            'issn': reg.issn,
            'qualis': current_qualis,
            'qualis_ant': previous_qualis,
            'qualis_indicator': qualis_indicator,
            'url': reg.url,
            'eissn': reg.eissn,
            'status': reg.status,
            'oalex_h5': reg.oalex_h5,
            'h5': reg.google_h5,
            'modelo_economico': reg.modelo_economico,
            'citescore': reg.citescore,
            'sjr': reg.sjr,
            'oalex_code': reg.oalex_code,
            'google_code': reg.google_code,
            'scopus_code': reg.scopus_code
        })

    current_page = page_obj.number
    # Compact page list: 1 2 3 ... N
    page_items = []
    if paginator.num_pages <= 7:
        page_items = list(range(1, paginator.num_pages + 1))
    else:
        core = {1, paginator.num_pages, current_page - 1, current_page, current_page + 1}
        core = sorted([n for n in core if 1 <= n <= paginator.num_pages])
        prev_num = None
        for n in core:
            if prev_num and n - prev_num > 1:
                page_items.append('...')
            page_items.append(n)
            prev_num = n
    query_no_page = request.GET.copy()
    if 'page' in query_no_page:
        query_no_page.pop('page')
    query_no_page_per_page = query_no_page.copy()
    if 'per_page' in query_no_page_per_page:
        query_no_page_per_page.pop('per_page')

    context['values'] = result
    context['soma'] = total_items
    context['page_obj'] = page_obj
    context['per_page'] = per_page
    context['selected_per_page'] = selected_per_page
    context['per_page_options'] = [
        ('25', '25'),
        ('50', '50'),
        ('100', '100'),
        ('all', 'Todos'),
    ]
    context['page_items'] = page_items
    context['query_string_no_page'] = query_no_page.urlencode()
    context['query_items_no_page_per_page'] = list(query_no_page_per_page.items())
    return render(request, 'periodicos_ci.html', {'result': context})


def get_issn(request, issn):
    periodico = Periodico.objects.filter(Q(issn=issn) | Q(eissn=issn)).first()

    if periodico:
        assuntos_asjc = []
        assuntos_openalex = []
        periodicos_assuntos = PeriodicoAssunto.objects.filter(
            periodico_id=periodico.id
        ).select_related('assunto', 'assunto__schema').order_by('ordem', 'id')

        if periodicos_assuntos.exists():
            for periodicos_assunto in periodicos_assuntos:
                descricao = periodicos_assunto.assunto.descricao.strip() if periodicos_assunto.assunto.descricao else None
                if not descricao:
                    continue

                schema_sigla = periodicos_assunto.assunto.schema.sigla if periodicos_assunto.assunto.schema else None
                if schema_sigla == 'ASJC':
                    assuntos_asjc.append(descricao)
                elif schema_sigla == 'OALEXS':
                    assuntos_openalex.append(descricao)

            # OALEXF is the current source. Use it when OALEXS subfields are not available.
            if not assuntos_openalex:
                assuntos_openalex = [
                    periodicos_assunto.assunto.descricao.strip()
                    for periodicos_assunto in periodicos_assuntos
                    if periodicos_assunto.assunto and periodicos_assunto.assunto.descricao
                    and periodicos_assunto.assunto.schema
                    and periodicos_assunto.assunto.schema.sigla == 'OALEXF'
                ]

        data = {
            'nome': periodico.nome,
            'issn': periodico.issn,
            'eissn': periodico.eissn,
            'url': periodico.url,
            'status': periodico.status,
            'qualis': periodico.qualis,
            'area': str(periodico.area),
            'pais': periodico.pais,
            'editora': periodico.editora,
            'modelo_economico': periodico.modelo_economico,
            'keywords': periodico.keywords,
            'sjr': str(periodico.sjr) if periodico.sjr is not None else None,
            'scopus_code': periodico.scopus_code,
            'sistema': periodico.sistema,
            'referencia': periodico.referencia,
            'dt_validacao': str(periodico.dtvalidacao),
            'qualis_ant': periodico.qualis_ant,
            'areas_asjc': assuntos_asjc,
            'openalex_subareas': assuntos_openalex,
            'qualis_chart_values': periodico.qualis_evolucao(),
        }

    else:
        data = {'error': 404}

    return HttpResponse(json.dumps(data), content_type='application/json')


def dashboard_periodicos(request):
    context = {}
    context['areas_cnpq'] = list(AreaConhecimento.objects.values('id', 'nome').order_by('nome'))
    context['assuntos'] = list(Assunto.objects.filter(schema__sigla='ASJC').
                               values('id', 'descricao').order_by('descricao'))

    return render(request, 'dashboard_periodicos.html', {'result': context})


def dashboard_periodicos_filter(request):
    data = {
        'counters': []
    }
    periodicos = Periodico.objects.filter(status='A')
    assunto_id = request.GET.get('area')
    area_cnpq_id = request.GET.get('area_cnpq')
    topico_id = request.GET.get('topico')

    if area_cnpq_id:
        periodicos = periodicos.filter(area_id=area_cnpq_id)

    if assunto_id:
        asjc_match = PeriodicoAssunto.objects.filter(
            assunto_id=assunto_id,
            schema__sigla='ASJC',
        ).values('periodico_id')
        periodicos = periodicos.filter(pk__in=asjc_match)

    if topico_id:
        topico_match = PeriodicoAssunto.objects.filter(
            assunto_id=topico_id,
            schema__sigla='OALEXF',
        ).values('periodico_id')
        periodicos = periodicos.filter(pk__in=topico_match)

    data['counters'] = [
        {
            'title': 'Total de Periódicos',
            'value': periodicos.count()
        },
        {
            'title': 'Periódicos Diamond',
            'value': periodicos.filter(modelo_economico='D').count()
        },
        {
            'title': 'Com Qualis',
            'value': periodicos.exclude(qualis='ND').count(),
        },
        {
            'title': 'Periódicos sem a identificação de país',
            'value': periodicos.filter(pais__isnull=True).count()
        }
    ]

    qualis_data = periodicos.exclude(qualis='ND').values('qualis', 'modelo_economico').annotate(
        frequency=Count('qualis')).order_by('qualis')

    data['dashboards'] = {
        'qualis_dash': {
            'traces': [
                {
                    'name': 'Diamond',
                    'x': list(map(lambda header: header['qualis'], qualis_data.filter(modelo_economico='D'))),
                    'y': list(map(lambda header: header['frequency'], qualis_data.filter(modelo_economico='D'))),
                },
                {
                    'name': 'APC/Locked',
                    'x': list(map(lambda header: header['qualis'], qualis_data.exclude(modelo_economico='D'))),
                    'y': list(map(lambda header: header['frequency'], qualis_data.exclude(modelo_economico='D'))),
                },
            ]
        }
    }

    pais_data = periodicos.values('pais', 'modelo_economico').annotate(
        frequency=Count('pais')).filter(frequency__gt=0).order_by('-frequency')

    data['dashboards']['pais_dash'] = {
        'traces': [
            {
                'name': 'Diamond',
                'x': list(map(lambda header: header['pais'], pais_data.filter(modelo_economico='D'))),
                'y': list(map(lambda header: header['frequency'], pais_data.filter(modelo_economico='D'))),
            },
            {
                'name': 'APC/Locked',
                'x': list(map(lambda header: header['pais'], pais_data.exclude(modelo_economico='D'))),
                'y': list(map(lambda header: header['frequency'], pais_data.exclude(modelo_economico='D'))),
            },
        ]
    }

    return HttpResponse(json.dumps(data), content_type='application/json')


def dashboard_periodicos_topicos(request):
    termo = (request.GET.get('q') or '').strip()
    queryset = Assunto.objects.filter(schema__sigla='OALEXF')
    if termo:
        queryset = queryset.filter(descricao__icontains=termo)
    queryset = queryset.values('id', 'descricao').order_by('descricao')[:30]
    data = {
        'results': [{'id': row['id'], 'text': row['descricao']} for row in queryset]
    }
    return HttpResponse(json.dumps(data), content_type='application/json')
