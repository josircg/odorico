import os

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, reverse

from utils.decorators import superuser_required
from .models import Inscricao, Matricula, Pesquisador, Turma
from .models import MatriculaEvento


@staff_member_required
def turma_completa(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id)
    cursos = [record.curso for record in turma.turmacurso_set.all()]
    count = 0
    for matricula in Matricula.objects.filter(curso__in=cursos, status='A'):
        inscricao, nova = Inscricao.objects.get_or_create(turma=turma, matricula=matricula, aluno=matricula.pesquisador,
                                                          defaults={'status': Inscricao.Status.MATRICULADO})
        inscricao.save()
        if nova:
            count += 1
    if count > 0:
        messages.success(request, f'{count} alunos inscritos')
    return redirect(reverse('admin:nucleo_turma_change', args=[turma_id]))


@staff_member_required
def reenvia_email_banca_agendada(request, matricula_evento_id):
    evento = get_object_or_404(MatriculaEvento, id=matricula_evento_id)
    qtd = evento.notifica_banca_agendada()
    if qtd:
        messages.success(request, f'E-mail de banca agendada enviado para {qtd} destinatário(s)')
    else:
        messages.warning(request, 'Nenhum destinatário na lista de agendamento de bancas')
    return redirect(reverse('admin:nucleo_matriculaevento_change', args=[matricula_evento_id]))


@superuser_required
def baixar_xml_lattes(request, pesquisador_id):
    pesquisador = get_object_or_404(Pesquisador, id=pesquisador_id)
    change_url = reverse('admin:nucleo_pesquisador_change', args=[pesquisador_id])

    if not pesquisador.id_cnpq:
        messages.error(request, 'Pesquisador sem id_cnpq cadastrado')
        return redirect(change_url)

    filename = os.path.join(settings.BASE_DIR, 'data', f'{pesquisador.id_cnpq}.xml')
    if not os.path.exists(filename):
        messages.error(request, 'Arquivo XML do Lattes não encontrado')
        return redirect(change_url)

    with open(filename, 'rb') as f:
        conteudo = f.read()
    response = HttpResponse(conteudo, content_type='application/xml')
    response['Content-Disposition'] = f'attachment; filename="{pesquisador.id_cnpq}.xml"'
    return response
