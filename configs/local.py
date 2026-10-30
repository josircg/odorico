from .settings import *

DEBUG = True

SITE_NAME = 'Odorico'
SITE_URL = 'http://localhost:8000'
ALLOWED_HOSTS = ['localhost']
# Command to create a new secret key:
# $ python -c "import secrets; print(secrets.token_urlsafe())"
SECRET_KEY = ''

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

LANGUAGE_CODE = 'pt-BR'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_L10N = True
USE_TZ = False

SILENCED_SYSTEM_CHECKS = ['captcha.recaptcha_test_key_error', ]
NOCAPTCHA = True
RECAPTCHA_USE_SSL = True

SEND_EMAIL = False
EMAIL_PREFIX = '[ODORICO]'
EMAIL_HOST = 'smtp.xxx.com'
EMAIL_USE_TLS = False
EMAIL_PORT = 587
EMAIL_HOST_USER = 'webmaster@irdx.com.br'
EMAIL_HOST_PASSWORD = 'xxxxx'
EMAIL_SENDER = 'Nome da Instituição'

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
REPLY_TO_EMAIL = EMAIL_HOST_USER

# Chave do Google Maps para a visualização do mapa de presença
GEO_API = ''

# Caso a sua instituição tenha acesso ao proxy do CNPQ, incluir a URL aqui
PROXY_LATTES_URL = ''

RECAPTCHA_DOMAIN = 'www.recaptcha.net'
RECAPTCHA_PUBLIC_KEY = ''
RECAPTCHA_PRIVATE_KEY = ''

API_MOODLE = None
URL_MOODLE = None

# django-storages settings
AWS_ACCESS_KEY_ID = ''
AWS_SECRET_ACCESS_KEY = ''
AWS_STORAGE_BUCKET_NAME = 'iesp-bucket'
AWS_S3_REGION_NAME = ''
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
