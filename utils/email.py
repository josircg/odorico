# coding:utf-8
import datetime
from django.conf import settings
from django.template.loader import get_template

from threading import Thread
from .models import EmailAgendado
from odorico import local


def sendmail(subject='', to=[], params={}, template=''):
    """
    Método para envio de e-mail:
    - subject: string contendo assunto do e-mail
    - to: lista dos e-mails dos destinatários
    - params: dicionário com os parâmetros para renderizar o e-mail
    """
    def send_thread_email(assunto='', to=[], params={}, template=''):

        email = EmailAgendado.objects.create(
            subject=assunto,
            to=','.join(to)
        )

        try:
            template_content = get_template(template)
            html_content = template_content.render(params)
            email.html = html_content
        except Exception as e:
            email.html = u'%s' % e

        mail_active = getattr(local,'SEND_EMAIL', 'False')
        if mail_active:
            email.send()
        else:
            email.save()

    th = Thread(target=send_thread_email, args=(subject, to, params, template))
    th.start()
