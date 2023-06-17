# -*- coding: utf-8 -*-
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template import loader

from utils.email import sendmail


class EmailValidationOnForgotPassword(PasswordResetForm):

    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email__iexact=email, is_active=True).exists():
            msg = "Não existe nenhum usuário com esse email."
            self.add_error('email', msg)
        return email

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        """
        Sends a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        #body = loader.render_to_string(email_template_name, context)
        link = '%s://%s/reset/%s/%s/' % (context['protocol'], context['domain'], context['uid'].decode(), context['token'])
        sendmail(
            subject=subject,
            to=[to_email],
            params={'site_name': 'Odorico', 'link': link, 'nome': context['user']},
            template='email.html',
        )
        # email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        # if html_email_template_name is not None:
        #     html_email = loader.render_to_string(html_email_template_name, context)
        #     email_message.attach_alternative(html_email, 'text/html')
        #
        # email_message.send()