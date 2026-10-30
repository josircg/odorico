import os
import datetime
import time
import hashlib
import smtplib
import ssl

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
from fpdf import FPDF

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.transaction import set_autocommit, commit

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import matplotlib.font_manager as fontman

from escola.models import Curso, ListaInteresse
from nucleo.models import Instituicao
from utils.models import TipoProcessamento

from utils.apps import log_object


def send_mail_arquivo(conn, remetente, destino, arquivo, subject, reply_to=None):
    # instance of MIMEMultipart
    msg = MIMEMultipart()
    # storing the senders email address
    msg['From'] = remetente
    # storing the receivers email address
    if isinstance(destino, list):
        msg['To'] = destino[0]
    else:
        msg['To'] = destino
    # storing the subject
    msg['Subject'] = subject

    # indica reply-to caso exista
    if reply_to:
        msg['Reply-To'] = reply_to

    # string to store the body of the mail
    body = "Segue em anexo certificado de participação"

    # attach the body with the msg instance
    msg.attach(MIMEText(body, 'plain'))

    # open the file to be sent
    fp = open(arquivo, "rb")
    # instance of MIMEBase and named as p
    p = MIMEBase('application', 'octet-stream')
    # To change the payload into encoded form
    p.set_payload(fp.read())
    fp.close()

    # encode into base64
    encoders.encode_base64(p)
    nome_arquivo = os.path.split(arquivo)[-1]
    p.add_header('Content-Disposition', 'attachment', filename=nome_arquivo)

    # attach the instance 'p' to instance 'msg'
    msg.attach(p)

    # Converts the Multipart msg into a string
    text = msg.as_string()
    # sending the mail
    conn.sendmail(msg['From'], destino, text)
    return


def find_font_file(query):
    matches = []
    for path in fontman.findSystemFonts():
        if query in os.path.basename(path):
            matches.append(path)
    return matches


def tokenize(string):
    return ''.join(e for e in string if e.isalnum())


def connect(login, password):
    if settings.EMAIL_USE_TLS:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        conn = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        conn.ehlo()
        conn.starttls(context=context)
        conn.ehlo()
    else:
        conn = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)

    conn.login(login, password)
    return conn


def gera_pdf(filename_base, nome_requerente, nome_curso, imagem, font, color, linha, autor, hash_certificado,
             replace=False):
    dest_path = os.path.join(settings.BASE_DIR, 'media', 'certificados')
    dest_filename = os.path.join(dest_path, f'{filename_base}.pdf')
    img_filename = os.path.join(dest_path, f'{filename_base}.png')
    if not replace and os.path.exists(dest_filename):
        return dest_filename
    img = Image.open(imagem)
    draw = ImageDraw.Draw(img)
    textwidth = draw.textlength(nome_requerente, font=font)
    draw.text(((img.width - textwidth)/2, linha), nome_requerente, fill=color, font=font)
    img.save(img_filename, optimize=True, quality=50)
    pdf = FPDF(orientation='L', format='A4')
    pdf.add_page()
    pdf.lang = 'pt-br'
    pdf.subject = nome_curso
    pdf.title = f'Certificado {nome_curso}'
    pdf.author = autor
    pdf.creator = hash_certificado
    pdf.creation_date = datetime.datetime.today()
    pdf.image(img_filename, 0, 0, pdf.w, pdf.h)
    pdf.output(dest_filename, 'F')
    # os.rename(f'{filename_base}.pdf', dest_filename)
    os.remove(img_filename)
    return dest_filename


def processa_inscricao_unica(inscricao):

    curso = inscricao.curso
    modelo = None
    if curso.modelo:
        modelo = curso.modelo
    elif curso.modulo and curso.modulo.modelo:
        modelo = curso.modulo.modelo

    if modelo:
        reply_to = modelo.reply_to
    else:
        raise ValueError('Modelo não definido')

    font_path = find_font_file(modelo.font_name)
    if not font_path:
        raise ValueError('Fonte do modelo não encontrada')

    smtp_login = settings.EMAIL_HOST_USER
    password = settings.EMAIL_HOST_PASSWORD
    conn = connect(smtp_login, password)
    if not conn:
        raise ValueError('SMTP connection failed')

    font = ImageFont.truetype(font_path[0], modelo.font_size)
    nome_escola = Instituicao.objects.get(id=settings.ESCOLA).nome

    base = str(inscricao.id) + '-' + settings.SECRET_KEY
    hash_certificado = hashlib.sha1(base.encode()).hexdigest()
    base = str(inscricao.id) + '-' + hash_certificado[:10]
    file_name = gera_pdf(base, inscricao.discente.nome.upper(), curso.nome,
                         curso.certificado.path, font, modelo.color, modelo.linha,
                         nome_escola, hash_certificado)

    if conn and file_name:
        email = inscricao.discente.email.strip().replace(" ", "")
        if email:
            send_mail_arquivo(conn, settings.EMAIL_SENDER, email, file_name, f'Certificado {curso.nome}', reply_to)
        else:
            raise ValueError('Email inexistente')


def processa_curso(id_curso, envio_email):
    curso = Curso.objects.filter(id=id_curso).first()
    if curso:
        print(f'Emitindo certificado do curso: {curso.nome}')
    else:
        print('Curso não encontrado')
        return

    if not os.path.exists(curso.certificado.path):
        print('%s não encontrado' % curso.certificado.path)
        exit(1)

    modelo = None
    if curso.modelo:
        modelo = curso.modelo
    elif curso.modulo and curso.modulo.modelo:
        modelo = curso.modulo.modelo

    if modelo:
        reply_to = modelo.reply_to
    else:
        print('Modelo não definido')
        return

    if envio_email:
        smtp_login = settings.EMAIL_HOST_USER
        password = settings.EMAIL_HOST_PASSWORD
        conn = connect(smtp_login, password)
        if not conn:
            print('SMTP connection failed')
            return
    else:
        conn = None

    font_path = find_font_file(modelo.font_name)
    if not font_path:
        print('Fonte do modelo não encontrada')
        return
    font = ImageFont.truetype(font_path[0], modelo.font_size)
    nome_escola = Instituicao.objects.get(id=settings.ESCOLA).nome
    nome_curso = curso.nome

    set_autocommit(False)
    processamento = TipoProcessamento.objects.get(tipo=TipoProcessamento.ENVIO_CERTIFICADO)
    if processamento.lock_status:
        print('Já existe um processamento em andamento')
        return
    processamento.lock_status = True
    processamento.save()
    commit()

    tot_lidos = 0
    tot_emails = 0
    tot_descartados = 0
    try:
        for inscricao in curso.inscricao_set.filter(presenca=True):
            tot_lidos += 1
            base = str(inscricao.id) + '-' + settings.SECRET_KEY
            hash_certificado = hashlib.sha1(base.encode()).hexdigest()
            base = str(inscricao.id) + '-' + hash_certificado[:10]

            dest_path = os.path.join(settings.BASE_DIR, 'media', 'certificados')
            dest_filename = os.path.join(dest_path, f'{base}.pdf')
            if os.path.exists(dest_filename):
                tot_descartados += 1
                continue

            file_name = gera_pdf(base, inscricao.discente.nome.upper(), nome_curso,
                                 curso.certificado.path, font, modelo.color, modelo.linha,
                                 nome_escola, hash_certificado, not envio_email)
            if conn and file_name:
                email = inscricao.discente.email.strip().replace(" ", "")
                if email:
                    send_mail_arquivo(conn, settings.EMAIL_SENDER, email, file_name, f'Certificado {nome_curso}', reply_to)
                    tot_emails += 1
                    if tot_emails % 50 == 0:
                        print('sent %d' % tot_emails)
                        conn.quit()
                        time.sleep(15)
                        conn = connect(smtp_login, password)
                else:
                    print(f'Email não encontrado na inscrição {inscricao.id}')

        # Marca Certificado Enviado no Curso
        curso.envio_certificado = 'E'
        curso.save()
        log_object(curso, f'Certificados emitidos: {tot_lidos}. Emails enviados: {tot_emails+tot_descartados}')
    except Exception as e:
        log_object(curso, f'Erro na emissão do certificado: {e}')
    finally:
        processamento.lock_status = False
        processamento.save()
        commit()
        print(f'Total de Certificados emitidos: {tot_lidos}')
        print(f'Total de Emails enviados: {tot_emails}')


def processa_lista(lista_id, envio_email):
    lista = ListaInteresse.objects.filter(id=lista_id).first()
    if lista:
        print(f'Emitindo certificados da lista: {lista.titulo}')
    else:
        print('Lista não encontrada')
        return

    if not os.path.exists(lista.arquivo.path):
        print('Arquivo %s não encontrado' % lista.arquivo.path)
        return

    modelo = lista.modelo
    if not modelo:
        print('Modelo não encontrado')
        return

    reply_to = modelo.reply_to

    if envio_email:
        smtp_login = settings.EMAIL_HOST_USER
        password = settings.EMAIL_HOST_PASSWORD
        conn = connect(smtp_login, password)
        if not conn:
            print('SMTP connection failed')
            return
    else:
        conn = None

    font_path = find_font_file(modelo.font_name)
    if not font_path:
        print('Fonte do modelo não encontrada')
        return
    font = ImageFont.truetype(font_path[0], modelo.font_size)
    nome_escola = Instituicao.objects.get(id=settings.ESCOLA).nome
    titulo = lista.titulo

    set_autocommit(False)
    processamento = TipoProcessamento.objects.get(tipo=TipoProcessamento.ENVIO_CERTIFICADO)
    if processamento.lock_status:
        print('Já existe um processamento em andamento')
        return
    processamento.lock_status = True
    processamento.save()
    commit()

    tot_lidos = 0
    tot_emails = 0
    log_result = ''
    try:
        for inscricao in lista.listacontato_set.all():
            tot_lidos += 1
            base = str(lista.id) + '-' + str(inscricao.id) + '-' + settings.SECRET_KEY
            hash_certificado = hashlib.sha1(base.encode()).hexdigest()
            base = str(inscricao.id) + '-' + hash_certificado[:10]
            file_name = gera_pdf(base, inscricao.contato.nome.upper(), titulo,
                                 lista.arquivo.path, font, modelo.color, modelo.linha,
                                 nome_escola, hash_certificado, not envio_email)
            if conn and file_name:
                email = inscricao.contato.email.strip().replace(" ", "")
                if email:
                    send_mail_arquivo(conn, settings.EMAIL_SENDER, email, file_name, f'Certificado {titulo}', reply_to)
                    tot_emails += 1
                    if tot_emails % 50 == 0:
                        print('sent %d' % tot_emails)
                        conn.quit()
                        time.sleep(15)
                        conn = connect(smtp_login, password)
                else:
                    print(f'Email não encontrado na inscrição {inscricao.id}')

        # Marca Certificado Enviado no Curso
        lista.status_envio = 'E'
        lista.save()
        log_result = f'Certificados emitidos: {tot_lidos}. Emails enviados: {tot_emails}'
        log_object(lista, log_result )
    except Exception as e:
        log_object(lista, f'Erro na emissão do certificado: {e}')
        log_result = '{e}'
    finally:
        processamento.lock_status = False
        processamento.save()
        commit()
        print(log_result)


class Command(BaseCommand):
    label = 'Gera e Envia certificados'

    def add_arguments(self, parser):
        parser.add_argument('--curso', type=int, help='Id do Curso', nargs='?', default=None)
        parser.add_argument('--lista', type=int, help='Id da Lista de Interesse', nargs='?', default=None)
        parser.add_argument('--sem-email', help='Sem envio de email', action='store_true')

    # Corrige o status de conclusão do curso dos alunos
    def handle(self, *args, **options):

        id_curso = options['curso']
        id_lista = options['lista']
        envio_email = not options['sem_email']
        if id_curso:
            processa_curso(id_curso, envio_email)
        elif id_lista:
            processa_lista(id_lista, envio_email)
        else:
            tot_registros = 0
            for curso in Curso.objects.filter(envio_certificado='A'):
                processa_curso(curso.id, envio_email)
                tot_registros += 1
            print(f'{tot_registros} cursos processados')

            tot_registros = 0
            for lista in ListaInteresse.objects.filter(status_envio='A'):
                processa_lista(lista.id, envio_email)
                tot_registros += 1
            print(f'{tot_registros} listas processadas')
