import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.1/howto/deployment/checklist/

DEBUG = False

ALLOWED_HOSTS = []
SITE_NAME = 'Odorico'

# Application definition

INSTALLED_APPS = [
    'admin_tools',
    'admin_tools.dashboard',
    'poweradmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.humanize',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'utils',
    'nucleo',
    'escola',
    'qualis',
    'editais',
    'captcha',
    'storages',
    'crispy_forms',
    'crispy_bootstrap4',
    'django_select2',
    'smart_selects',
    'ckeditor',
    'ckeditor_uploader',
    'qrcode',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'nucleo.middleware.AdminLoginRedirectMiddleware',
]

if os.path.isdir(os.path.join(BASE_DIR, 'tema')):
    INSTALLED_APPS += [
        'tema',
    ]

SQLEXPLORER = os.path.exists(os.path.join(BASE_DIR, 'logs', 'explorer'))
if SQLEXPLORER:
    INSTALLED_APPS += ("explorer",)
    EXPLORER_CONNECTIONS = {
        'Default': 'default'
    }
    EXPLORER_DEFAULT_CONNECTION = 'default'
    EXPLORER_SQL_BLACKLIST = ['DROP']  # Comandos SQL proibidos

ROOT_URLCONF = 'odorico.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + '/templates',
            BASE_DIR + '/escola/templates',
        ],
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                'admin_tools.template_loaders.Loader',
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',

            ]
        },
    },
]

LOGIN_URL = 'login'

if os.path.isdir(os.path.join(BASE_DIR, 'tema')):
    TEMPLATES[0]['DIRS'].insert(0, BASE_DIR + '/tema/templates')

CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_BASEPATH = "/static/ckeditor/ckeditor/"
CKEDITOR_REQUIRE_STAFF = False

CKEDITOR_CONFIGS = {
    'default': {
        'removePlugins': 'exportpdf',
        'toolbar': 'default_custom',
        'toolbar_default_custom': [
            {'name': 'basicstyles',
             'items': ['Bold', 'Italic', 'Underline', 'Subscript', 'Superscript', '-', 'RemoveFormat']},
            {'name': 'paragraph',
             'items': ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-', 'Blockquote', 'CreateDiv', '-',
                       'JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock', '-', 'BidiLtr', 'BidiRtl',
                       'Source']},
            {'name': 'links', 'items': ['Link', 'Unlink', 'Anchor']},
            {'name': 'insert', 'items': ['Image']},
            '/',
            {'name': 'styles', 'items': ['Styles', 'Format', 'FontSize']},
            {'name': 'colors', 'items': ['TextColor', 'BGColor']},
        ],
    },
    'frontpage': {
        'toolbar': 'Custom',
        'toolbar_Custom': [
            ['Bold', 'Italic', 'Underline'],
            ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent',
             '-', 'JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock'],
            ['Link', 'Unlink'],
            ['RemoveFormat']
        ]
    },
}

WSGI_APPLICATION = 'odorico.wsgi.application'

# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    "select2": {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'select2_cache',
        'TIMEOUT': 7200,
     }
}

# Tell select2 which cache configuration to use:
SELECT2_CACHE_BACKEND = "select2"

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

TIME_ZONE = 'America/Sao_Paulo'
LANGUAGE_CODE = 'pt-BR'
USE_I18N = True
USE_TZ = False
USE_L10N = False
DATE_FORMAT = 'd/m/Y'
DATETIME_FORMAT = 'd/m/Y H:i:s'
DATE_INPUT_FORMATS = (
    '%d/%m/%Y',
)

from django.conf.locale.pt_BR import formats as br_formats
br_formats.DATE_FORMAT = 'd/m/Y'

# Decimal format
DECIMAL_SEPARATOR = ','
THOUSAND_SEPARATOR = '.'
NUMBER_GROUPING = True
USE_THOUSAND_SEPARATOR = True

ADMIN_TOOLS_INDEX_DASHBOARD = 'dashboard.CustomIndexDashboard'
ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'dashboard.CustomAppIndexDashboard'

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATIC_URL = '/static/'
USE_CAPTCHA = True

API_SCOPUS_KEY = ''
API_MOODLE = None
API_IDENTIFIER = 'Odorico'
VERSION = '1.8'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
# needed to use crispy-forms
CRISPY_TEMPLATE_PACK = 'bootstrap4'
# admin input classes
CRISPY_CLASS_CONVERTERS = {
    'textinput': 'vTextField',
    'emailinput': 'vTextField',
    'textarea': 'vLargeTextField'
}

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue'
        },
    },
    'formatters': {
        'django.server': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(server_time)s] %(message)s',
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': False
        },
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
        },
        'django.server': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'django.server',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins', 'console'],
            'propagate': True,
        },
        'django.server': {
            'handlers': ['django.server'],
            'level': 'INFO',
            'propagate': False,
        }
    }
}
