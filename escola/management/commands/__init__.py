from django.db.utils import OperationalError, ProgrammingError

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission, User


def create_views_permissions():
    Permission.objects.get_or_create(
        name='Importação Lattes',
        codename='importacao_lattes',
        content_type=ContentType.objects.get_for_model(User)
    )


try:
    # Executado no import do módulo. Protegido contra bancos ainda não migrados
    # (ex.: primeiro deploy antes do migrate, ou SQLite em memória nos testes),
    # quando as tabelas de ContentType/Permission ainda não existem.
    create_views_permissions()
except (OperationalError, ProgrammingError):
    pass
