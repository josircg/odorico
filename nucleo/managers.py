from django.db import models


class PesquisadorQuerySet(models.QuerySet):

    def com_lattes(self):
        """Retorna somente pesquisadores com currículo Lattes identificado (ID CNPq preenchido)"""
        return self.exclude(id_cnpq__isnull=True).exclude(id_cnpq='')
