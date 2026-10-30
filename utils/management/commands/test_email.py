import smtplib
from utils.email import sendmail

from django.conf import settings
from django.core.files.storage import get_storage_class
from django.core.management import BaseCommand, CommandError

import poplib
import email

def decode_header(header):
    decoded_bytes, charset = email.header.decode_header(header)[0]
    if charset is None:
        return str(decoded_bytes)
    else:
        return decoded_bytes.decode(charset)

def get_messages():
    user = 'enacin.web@ibict.br'
    mailbox = poplib.POP3_SSL('pop.gmail.com', '995')
    mailbox.user(user)
    mailbox.pass_(settings.EMAIL_HOST_PASSWORD)
    (num_messages, totalSize) = mailbox.stat()
    print(num_messages)
    for index in range(num_messages):
        raw_email = b"\n".join(mailbox.retr(index + 1)[1])
        parsed_email = email.message_from_bytes(raw_email)
        print(f'=========== email #{index} ============')
        print('From:', parsed_email['From'])
        print('To:', parsed_email['To'])
        print('Date:', parsed_email['Date'])
        print('Subject:', decode_header(parsed_email['Subject']))
    mailbox.quit()

class Command(BaseCommand):
    help = 'Teste de envio de email'

    def handle(self, **options):
        get_messages()
        # sendmail(subject='Teste', to=['josircg@gmail.com'], message='Teste')

'''
receivers = ['josircg@gmail.com']

header='To:'+destinatario+'\n'+'From:'+remetente+'\n'+'subject:testmail\n'
with smtplib.SMTP('smtp.umbler.com', port) as server:
    server.ehlo()
    server.starttls()
    server.login(remetente, '###')
    server.sendmail(remetente, receivers, content)
    print("Successfully sent email")
'''