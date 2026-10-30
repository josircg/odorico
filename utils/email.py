import datetime
from django.conf import settings
from django.template.loader import get_template

from threading import Thread
from .models import EmailAgendado


def sendmail(subject, dest_list, params={}, template='', message=None, thread=True):
    """
    Rotina para envio de e-mail:
    - subject: string contendo assunto do e-mail
    - to: lista dos e-mails dos destinatários
    - params: dicionário com os parâmetros para renderizar o e-mail
    - message: texto da mensagem sem a necessidade de utilizar um template
    """
    def send_thread_email(assunto, dest_list, params={}, template='', message=None):
        try:
            prefix = settings.EMAIL_PREFIX
            email = EmailAgendado.objects.create(
                subject=f'{prefix} {assunto}'[:89],
                to=','.join(dest_list)
            )

            if message:
                email.html = message
            else:
                if template:
                    template_content = get_template(template)
                    email.html = template_content.render(params)
                else:
                    email.html = 'Empty message'

            mail_active = settings.SEND_EMAIL
            if mail_active:
                email.send()
            else:
                email.save()

        except Exception as e:
            email = EmailAgendado.objects.create(
                subject='Erro enviando e-mail', to=settings.REPLY_TO_EMAIL, html=f'{assunto}\n{e}'
            )
            email.save()

    if thread:
        th = Thread(target=send_thread_email, args=(subject, dest_list, params, template, message))
        th.start()
    else:
        send_thread_email(subject, dest_list, params, template, message)
