# -*- coding: utf-8 -*-
from django.db import models
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

STATUS_EMAIL = (
    ("A", u"Aguardando envio manual"),
    ("R", u"Re-enviando"),
    ("E", u"Erro ao enviar"),
    ("K", u"Enviado"),
)


class EmailAgendado(models.Model):
    class Meta:
        ordering = ('-date', )

    subject = models.CharField(max_length=90, default="")
    status = models.CharField(max_length=1, choices=STATUS_EMAIL, default="A")
    date = models.DateTimeField(auto_now_add=True)
    to = models.TextField()
    html = models.TextField()

    def send(self):
        try:
            headers = {'Reply-To': settings.REPLY_TO_EMAIL, }
            msg = EmailMultiAlternatives(self.subject, self.html, settings.DEFAULT_FROM_EMAIL,
                                         to=self.to.split(','),
                                         headers=headers)
            msg.attach_alternative(self.html, 'text/html; charset=UTF-8')
            msg.send()
            self.status = 'K'
        except Exception as e:
            print(e)
            self.status = 'E'
        self.save()

    def __unicode__(self):
        return u"%s" % self.id


class TipoProcessamento(models.Model):

    CONVITE_ALUNO = 1
    CONVITE_PROFESSOR = 2
    CONVITE_CORRECAO = 3

    tipo = models.PositiveSmallIntegerField(
        choices=((CONVITE_ALUNO, 'Convite ao Aluno'),
                 (CONVITE_PROFESSOR, 'Convite ao Professor'),
                 (CONVITE_CORRECAO, 'Solicitação de correção')))
    template_email = models.TextField('Template do Email', blank=True, null=True)

    class Meta:
        verbose_name = 'Tipo de Processamento'

    def __unicode__(self):
        return

