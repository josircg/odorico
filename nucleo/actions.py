from nucleo.models import ProducaoAutor, Producao, PesquisadorNomeCitacao, ProjetoPesquisa, \
    PesquisadorProjeto, PesquisadorPrograma, ProfessorLinha, Orientacao, PesquisadorInstituicao, \
    PesquisadorFomento, PesquisadorGrupo, Programa, PesquisadorFormacao, \
    AlunoRegistro

from escola.models import CursoDocente


def merge_pesquisadores(queryset):
    # encontra o mais antigo
    destino = queryset.order_by('id').first()
    tot_pesquisadores = 0
    for obj in queryset.order_by('id')[1:]:
        destino.sexo = destino.sexo if destino.sexo else obj.sexo
        destino.id_cnpq = destino.id_cnpq if destino.id_cnpq else obj.id_cnpq
        if obj.dtupdate:
            destino.dtupdate = obj.dtupdate if destino.dtupdate and obj.dtupdate > destino.dtupdate else destino.dtupdate
        destino.raca = destino.raca if destino.raca else obj.raca
        destino.email = destino.email if destino.email else obj.email
        destino.CPF = destino.CPF if destino.CPF else obj.CPF
        destino.orcid = destino.orcid if destino.orcid else obj.orcid
        tot_pesquisadores += 1
        for citacao in obj.pesquisadornomecitacao_set.all():
            PesquisadorNomeCitacao.objects.get_or_create(pesquisador=destino, nome_citacao=citacao.nome)
        AlunoRegistro.objects.filter(aluno=obj).update(aluno=destino)
        PesquisadorInstituicao.objects.filter(pesquisador=obj).update(pesquisador=destino)
        CursoDocente.objects.filter(docente=obj).update(docente=destino)
        Producao.objects.filter(pesquisador=obj).update(pesquisador=destino)
        ProjetoPesquisa.objects.filter(proponente=obj).update(proponente=destino)
        PesquisadorProjeto.objects.filter(pesquisador=obj).update(pesquisador=destino)
        PesquisadorGrupo.objects.filter(pesquisador=obj).update(pesquisador=destino)
        PesquisadorFormacao.objects.filter(pesquisador=obj).update(pesquisador=destino)
        PesquisadorFomento.objects.filter(pesquisador=obj).update(pesquisador=destino)
        ProfessorLinha.objects.filter(professor=obj).update(professor=destino)
        Orientacao.objects.filter(orientador=obj).update(orientador=destino)
        PesquisadorPrograma.objects.filter(pesquisador=obj).update(pesquisador=destino)

        for autor in obj.producaoautor_set.all():
            if ProducaoAutor.objects.filter(producao=autor.producao, autor=destino):
                autor.delete()
            else:
                autor.autor = destino
                autor.save()

        obj.delete()

    if tot_pesquisadores > 0:
        destino.save()

    return tot_pesquisadores


def merge_instituicoes(queryset):
    # encontra o mais antigo
    destino = queryset.order_by('id').first()
    tot_inst = 0
    for obj in queryset.order_by('id')[1:]:
        destino.sigla = destino.sigla if destino.sigla else obj.sigla
        destino.pais = destino.pais if destino.pais else obj.pais
        tot_inst += 1
        Programa.objects.filter(instituicao=obj).update(instituicao=destino)
        PesquisadorInstituicao.objects.filter(instituicao=obj).update(instituicao=destino)
        PesquisadorFormacao.objects.filter(instituicao=obj).update(instituicao=destino)
        obj.delete()

    if tot_inst > 0:
        destino.save()

    return tot_inst