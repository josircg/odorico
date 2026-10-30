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
        subject = loader.render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())
        link = '%s://%s/reset/%s/%s/' % (context['protocol'], context['domain'], context['uid'], context['token'])
        sendmail(
            subject=subject,
            dest_list=[to_email],
            params={'site_name': 'Odorico', 'link': link, 'nome': context['user']},
            template='email.html',
        )
