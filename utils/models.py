from django.db import models
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.contrib.auth.models import User


STATUS_EMAIL = (
    ("A", u"Aguardando envio manual"),
    ("R", u"Re-enviando"),
    ("E", u"Erro ao enviar"),
    ("K", u"Enviado"),
)


class UserPerson(User):
    class Meta:
        verbose_name = u'Usuário Final'
        verbose_name_plural = u'Usuários Finais'
        proxy = True


class EmailAgendado(models.Model):
    class Meta:
        ordering = ('-date', )

    subject = models.CharField(max_length=200, default="")
    status = models.CharField(max_length=1, choices=STATUS_EMAIL, default="A")
    date = models.DateTimeField(auto_now_add=True)
    to = models.TextField()
    html = models.TextField()

    def send(self):
        try:
            if settings.REPLY_TO_EMAIL:
                headers = {'Reply-To': settings.REPLY_TO_EMAIL, }
            else:
                headers = None
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

    class Tipo(models.IntegerChoices):
        CONVITE_ALUNO = 1, 'Convite ao Aluno'
        CONVITE_PROFESSOR = 2,  'Convite ao Professor'
        CONVITE_CORRECAO = 3, 'Solicitação de correção'
        AVISO_APROVACAO = 4, 'Aviso de Aprovação'
        ENVIO_CERTIFICADO = 5, 'Envio de Certificado'
        EDITAL_AVISO = 6, 'Inscrição em Edital'
        EDITAL_CONFIRMACAO = 7, 'Confirmação de Inscrição em Edital'
        EDITAL_HOMOLOGACAO = 8, 'Homologação de Inscrição'

    tipo = models.PositiveSmallIntegerField(choices=Tipo.choices)
    documentacao = models.TextField('Documentação', blank=True, null=True)
    template_email = models.TextField('Template do Email', blank=True, null=True)
    lock_status = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Tipo de Processamento'
        verbose_name_plural = 'Tipos de Processamento'

    def __unicode__(self):
        return self.tipo
