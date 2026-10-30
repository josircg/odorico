import os
import subprocess

from django.conf import settings
from django.apps import AppConfig
from django.core.exceptions import ValidationError

from nucleo.apps import log_object


class UtilsConfig(AppConfig):
    name = 'utils'


def pdf_to_png(filename, obj=None):
    dest_filename, dest_fileext = os.path.splitext(filename)
    command = 'pdftoppm %s %s -png -r 150 -singlefile' % (filename, dest_filename)
    try:
        returned_output = subprocess.check_output(command, shell=True)
        dest_filename += '.png'
        if obj:
            obj.certificado.name = dest_filename.replace(settings.MEDIA_ROOT+'/','')
            obj.save()
        message = f'PDF convertido: {dest_filename}'
    except subprocess.CalledProcessError as e:
        message = f'{e}'
    if obj:
        log_object(obj, message)
    else:
        print(message)


# Executa um comando no SO e retorna a mensagem de sucesso
# command: em forma de lista ou string
# halt: boolean: True - levanta um erro e não retorna o log
# timeout: int
# cwd: str - em que diretório o comando será executado
# env: dict - variáveis de ambiente para o processo (None usa o ambiente atual)
#
def os_run(command, halt=True, timeout=None, cwd=None, env=None):
    stderr = None
    out = ''
    try:
        if not isinstance(command, list):
            command = command.split(" ")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                                cwd=cwd, env=env)
        if result.stdout:
            out += '%s\n' % result.stdout.decode('utf-8')
        if result.returncode != 0:
            stderr = '%s\n Code:(%d)\n' % (result.stderr.decode('utf-8'), result.returncode)
    except Exception as err:
        stderr = "Error: {0}\n".format(err)

    if stderr:
        if halt:
            raise ValidationError(stderr)
        else:
            out += stderr

    return out
