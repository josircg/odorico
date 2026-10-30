
import json

from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, redirect, get_object_or_404

from .apps import get_doi_record

from .models import DisciplinaCurso, ProfessorLinha, Periodo, Turma


# Retorna um JSON com os dados do DOI
def doi_record(request, doi):
    data = get_doi_record(doi, fast=True)
    return HttpResponse(json.dumps(data), content_type='application/json')


def disciplinas(request, curso_id):
    result = []
    for record in (DisciplinaCurso.objects.filter(
            curso_id=curso_id, disciplina__status='A').select_related('disciplina').order_by(
                'disciplina__tipo', 'linhapesquisa_id', 'disciplina__titulo')):
        if record.linhapesquisa_id:
            tipo = 'Optativas da '+record.linhapesquisa.descricao
        else:
            if record.disciplina.tipo == 'P':
                tipo = 'Optativas Comuns'
            else:
                tipo = record.disciplina.get_tipo_display()+'s'
        result.append({
            'tipo': tipo,
            'disciplina': record.disciplina.titulo,
            'codigo': record.codigo or record.disciplina.codigo,
            'ementa': record.disciplina.ementa,
            'carga_horaria': record.disciplina.carga_horaria,
            'creditos': record.disciplina.creditos
        })
    return HttpResponse(json.dumps(result), content_type='application/json')


def periodo_ativo(request):
    result = []
    periodo = Periodo.objects.filter(status=Periodo.Status.ATIVO).order_by('id').last()
    for record in Turma.objects.filter(periodo=periodo, externa=True).select_related('disciplina'):
        codigos = []
        if record.disciplina.codigo:
            codigos.append(f'{record.disciplina.codigo}')
        for dc in DisciplinaCurso.objects.filter(disciplina=record.disciplina):
            if dc.codigo:
                codigos.append(f'{dc.codigo} ({dc.curso.descricao})')

        result.append({
            'tipo': record.disciplina.get_tipo_display(),
            'disciplina': record.disciplina.titulo,
            'titulo': record.titulo or record.disciplina.titulo,
            'docente': record.docentes(),
            'codigo': ','.join(codigos),
            'ementa': record.disciplina.ementa,
            'calendario': record.calendario(),
            'info': record.info_matricula,
            'carga_horaria': record.disciplina.carga_horaria,
            'creditos': record.disciplina.creditos,
        })

        result = sorted(result, key=lambda item: item['titulo'])

    return HttpResponse(json.dumps(result), content_type='application/json')


def docentes_linha(request, linha_id):
    result = []
    for registro in ProfessorLinha.objects.filter(linha_id=linha_id,
                                                  dtsaida__isnull=True).select_related('professor').order_by('professor__nome'):
        result.append({
            'id': registro.professor.id,
            'nome': registro.professor.nome,
            'tipo': 'Permanente' if registro.permanente else 'Colaborador',
            'mini_bio': registro.professor.mini_bio,
            'url_foto': registro.professor.fotografia_url(),
            'id_cnpq': registro.professor.id_cnpq,
            'orcid': registro.professor.orcid,
        })

    return HttpResponse(json.dumps(result), content_type='application/json')


