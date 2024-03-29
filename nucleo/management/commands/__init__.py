from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission, User


def create_views_permissions():
    Permission.objects.get_or_create(
        name='Importação Lattes',
        codename='importacao_lattes',
        content_type=ContentType.objects.get_for_model(User)
    )


create_views_permissions()
