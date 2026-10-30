import os

from django.conf import settings
from django.core.files.storage import get_storage_class
from django.core.management import BaseCommand, CommandError


def cria_diretorio(diretorio):
    diretorio = os.path.join(settings.BASE_DIR, diretorio)
    if not os.path.exists(diretorio):
        os.mkdir(diretorio)


def test_s3_config():
    for attr in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_STORAGE_BUCKET_NAME', 'AWS_S3_REGION_NAME',
                 'DEFAULT_FILE_STORAGE']:
        if not getattr(settings, attr):
            raise CommandError(f'Parâmetro {attr} não definido')
    # Classe de armazenamento local
    lfs = get_storage_class('django.core.files.storage.FileSystemStorage')()
    # Classe de armazenamento remota (S3)
    rfs = get_storage_class('storages.backends.s3boto3.S3Boto3Storage')()
    rfs.file_overwrite = True
    # Retorna o primeiro arquivo que está em MEDIA_ROOT
    file = lfs.listdir(lfs.location)[1][0]
    if not file:
        raise CommandError(f'{lfs.location} vazio')
    file_remote = rfs.listdir(file)
    if not file_remote:
        raise CommandError(f'Arquivo remoto {file} não encontrado')


def cria_diretorios():
    cria_diretorio('media')
    cria_diretorio('media/fotos')
    cria_diretorio('media/images')
    cria_diretorio('media/uploads')
    cria_diretorio('media/uploads/lattes')


class Command(BaseCommand):
    help = 'Cria diretórios necessários na pasta media'

    def handle(self, **options):
        test_s3_config()
        # cria_diretorios()