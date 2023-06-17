from django.conf import settings
from django.core.files.storage import get_storage_class
from django.core.management import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Teste de upload de arquivo para o S3. Pega qualquer arquivo em MEDIA_ROOT e tenta fazer o upload.'

    def handle(self, **options):
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
        # Armazena o arquivo na raiz do bucket
        with lfs.open(file, 'rb') as f:
            self.stdout.write(f'Enviando arquivo {f.name}')
            # Utilizar o nome base para evitar a exceção
            # django.core.exceptions.SuspiciousFileOperation: Detected path traversal attempt
            fname = rfs.save(file, f)

        self.stdout.write(self.style.SUCCESS(f'Arquivo enviado. Url: {rfs.url(fname)}'))
