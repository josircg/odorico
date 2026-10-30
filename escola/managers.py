from django.apps import apps as django_apps
from django.db import models
from django.db.models import Q, OuterRef, Exists

from utils.stdlib import EMPTY_VALUES


class ModuloTrilhaQuerySet(models.QuerySet):

    def sessao_dias(self):
        """Retorna o distinct dos dias de ModuloSessao para uso em choices"""
        qs = (
            self.filter(modulosessao__dia__isnull=False)
            .values_list('modulosessao__dia', flat=True)
            .distinct()
            .order_by('modulosessao__dia')
        )
        return ((dia.isoformat(), dia) for dia in qs)

    def trilhas(self):
        """Retorna a lista de trilhas"""
        return self.values_list('pk', 'nome')


class ModuloSessaoQuerySet(models.QuerySet):

    def busca(self, **kwargs):
        fargs = ()
        fkwargs = {k: v for k, v in kwargs.items() if v not in EMPTY_VALUES}

        if 'sessao_trabalho' in fkwargs:
            sessao_trabalho = fkwargs.pop('sessao_trabalho')
            fargs += (Q(busca__icontains=sessao_trabalho),)

        return self.filter(*fargs, **fkwargs).distinct()

    def annotate_agenda(self, cookie):
        """
        Anota o QuerySet com a flag booleana 'tem_contato_agenda'.
        A flag é True se houver um registro de ContatoAgenda correlacionado
        à sessão e ao cookie de usuário fornecido.
        :param cookie: O valor do cookie (str) para identificação do usuário.
        :return: QuerySet anotado com o campo 'tem_contato_agenda'.
        """
        contatoagenda_cls = django_apps.get_model('escola.ContatoAgenda')
        subquery_contato_agenda = contatoagenda_cls.objects.filter(
            sessao=OuterRef('pk'),
            cookie=cookie
        )

        return self.annotate(
            tem_contato_agenda=Exists(subquery_contato_agenda)
        )


class ListaContatoQuerySet(models.QuerySet):

    def listacontato_agendamento_banca(self):
        """Retorna os itens cadastrados para a lista de insteresse Destinatários de Agendamento de Bancas"""
        return (
            self.filter(lista__titulo='Destinatários de Agendamento de Bancas', contato__email_invalido=False)
            .exclude(contato__email__isnull=True).exclude(contato__email='')
        )
