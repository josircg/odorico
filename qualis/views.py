import json

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import MultipleObjectsReturned

from csv import DictReader
from io import TextIOWrapper

from .forms import *
from .models import Periodico, GrandeArea, Area, AreaConhecimento, Assunto, PeriodicoAssunto
from utils import email
from odorico import local


def import_csv(texto, request):
    return True


def import_area_csv(texto, request):
    arquivo = TextIOWrapper(texto, encoding='iso-8859-1')
    dr_table = DictReader(arquivo, delimiter=';', quotechar='"')
    tot_importados = 0
    for row in dr_table:
        if 'NM_AREA_CONHECIMENTO' and 'NM_AREA_AVALIACAO' and \
                'CD_AREA_AVALIACAO' and 'NM_GRANDE_AREA_CONHECIMENTO' in row:
            try:
                grande_area = GrandeArea.objects.get_or_create(nome=row['NM_GRANDE_AREA_CONHECIMENTO'])[0]
            except MultipleObjectsReturned:
                grande_area = GrandeArea.objects.filter(nome=row['NM_GRANDE_AREA_CONHECIMENTO']).first()

            try:
                area = Area.objects.get_or_create(cod_capes=row['CD_AREA_AVALIACAO'],
                                                  defaults={'nome': row['NM_AREA_AVALIACAO'],
                                                            'grande_area': grande_area})[0]
            except MultipleObjectsReturned:
                area = Area.objects.filter(cod_capes=row['CD_AREA_AVALIACAO']).first()

            try:
                area_conhecimento = AreaConhecimento.objects.get_or_create(nome=row['NM_AREA_CONHECIMENTO'],
                                                                            defaults={'area_avaliacao': area})[0]
            except MultipleObjectsReturned:
                area_conhecimento = AreaConhecimento.objects.filter(nome=row['NM_AREA_CONHECIMENTO']).first()
            tot_importados += 1
    messages.info(request, 'Total de areas importadas: %d' % tot_importados)
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


from django.views.decorators.clickjacking import xframe_options_exempt
@login_required
def importacao_area(request):
    if request.method == 'POST':
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            texto = form.cleaned_data['arquivo']
            if import_area_csv(texto, request):
                return redirect('/importacao_area/')
            else:
                messages.error(request, 'ID não encontrado')
                return render(request, 'import_area.html', {'form': form})
    else:
        form = ImportForm()
    return render(request, 'import_area.html', {'form': form})


@xframe_options_exempt
def periodicos(request):
    context = {}

    params = request.GET.copy()
    if len(params):
        if params.get('ordering'):
            params.pop('ordering')
        context['params'] = '?' + '&'.join(['%s=%s' % (key, value) for (key, value) in params.items()])

    if len(params.keys()) > 0:
        area = int(params.get('area', 0))
        from_email = getattr(local, 'DEFAULT_FROM_EMAIL')
        issn = params.get('issn')
        email_usuario = params.get('email')
        issn_search = params.get('issn_search', '').strip()
        revista_search = params.get('revista_search', '')
        assunto = int(params.get('assunto', 0))
        diamound_check =params.get('diamound_check', None)

        if issn:
            email.sendmail('Sugestão para inclusão de ISSN no Odorico', [from_email, email_usuario], {'ISSN': issn},
                           'ISSN %s para inclusão no periódicos da área de %s'% (issn, area))
            messages.success(request, 'Pedido enviado com sucesso!')

        if area > 0 or issn_search or revista_search or assunto > 0:
            filtro = Periodico.objects.all()
            if issn_search:
                filtro = filtro.filter(Q(issn__exact=issn_search) | Q(eissn__exact=issn_search))

            if assunto:
                filtro = filtro.filter(periodicoassunto__assunto_id=assunto)

            if area and not issn_search and not assunto:
                filtro = filtro.filter(area__id__exact=area)

            if diamound_check:
                filtro = filtro.filter(modelo_economico='D')

            if revista_search:
                for termo in revista_search.split():
                    filtro = filtro.filter(nome__icontains=termo)
        else:
            area = Area.objects.all().first().pk
            filtro = Periodico.objects.filter(area__id__exact=area)

        context['area_select'] = area
        context['assunto_select'] = assunto
        context['search_issn'] = issn_search
        context['search_revista'] = revista_search
        context['diamound_check'] = diamound_check
    else:
        filtro = Periodico.objects.filter(area__id__exact=2).order_by('qualis', 'issn')
        context['area_select'] = 2

    if request.GET.get('ordering'):
        context['ordering'] = request.GET.get('ordering')
        filtro = filtro.order_by(request.GET.get('ordering'))
    else:
        filtro = filtro.order_by('qualis', 'issn')

    context['area'] = list(AreaConhecimento.objects.all())
    context['assuntos'] = list(Assunto.objects.filter(schema__sigla='ASJC').
                               values('id', 'descricao').order_by('descricao'))
    context['labels'] = [{'label': 'NOME COMPLETO', 'value': 'nome', },
                         {'label': 'ISSN', 'value': 'issn'},
                         {'label': 'QUALIS', 'value': 'qualis', 'hint': '2017-2021'},
                         {'label': 'E-ISSN', 'value': 'eissn'},
                         {'label': 'MODELO', 'value': 'modelo_economico', 'hint': 'Diamond / Locked / APC'},
                         {'class':'align-right', 'label': 'Google H5', 'value': 'google_h5'},
                         {'class':'align-right', 'label': 'CITESCORE', 'value': 'citescore'},
                         {'class':'align-right', 'label':'SJR', 'value': 'sjr'}
                        ]

    result = []
    dataset = filtro.values_list('nome', 'issn', 'qualis', 'url', 'eissn', 'status', 'google_h5', 'google_code',
                                 'modelo_economico', 'citescore', 'sjr', 'scopus_code')
    for reg in dataset:
        result.append({
            'nome': reg[0],
            'issn': reg[1],
            'qualis': reg[2],
            'url': reg[3],
            'eissn': reg[4],
            'status': reg[5],
            'h5': reg[6],
            'google_code': reg[7],
            'modelo_economico': reg[8],
            'citescore': reg[9],
            'sjr': reg[10],
            'scopus_code': reg[11]
        })

    context['values'] = result
    context['soma'] = filtro.count()
    return render(request, 'periodicos_ci.html', {'result': context})


def get_issn(request, issn):
    periodico = Periodico.objects.filter(Q(issn=issn) | Q(eissn=issn)).first()

    if periodico:
        data = {
            'nome': periodico.nome,
            'issn': periodico.issn,
            'eissn': periodico.eissn,
            'url': periodico.url,
            'status': periodico.status,
            'qualis': periodico.qualis,
            'area': str(periodico.area),
            'pais': periodico.pais,
            'sistema': periodico.sistema,
            'referencia': periodico.referencia,
            'dt_validacao': str(periodico.dtvalidacao),
            'assuntos': [],
        }

        periodicos_assuntos = PeriodicoAssunto.objects.filter(periodico_id=periodico.id)
        if periodicos_assuntos.exists():
            assuntos_dict = []
            for periodicos_assunto in periodicos_assuntos:
                assuntos_dict.append({
                    'cod_externo': periodicos_assunto.assunto.cod_externo,
                    'descricao': periodicos_assunto.assunto.descricao.strip() if periodicos_assunto.assunto.descricao else None
                })
            data['assuntos'] = assuntos_dict

    else:
        data = {'error': 404}

    return HttpResponse(json.dumps(data), content_type='application/json')

