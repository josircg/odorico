from django.apps import apps as django_apps


def aluno_post_save(sender, instance, created, **kwargs):
    """Adiciona AlunoRegistro ao adiciona um Aluno"""
    if created:
        alunoregistro_cls = django_apps.get_model('nucleo.AlunoRegistro')
        alunoregistro_cls.objects.create(aluno=instance)
