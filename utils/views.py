import os

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .apps import os_run


def _run_deploy_script(extra_env=None):
    """
    Invoca o script de deploy versionado (deploy.sh) na raiz do projeto e
    retorna a saída. Centraliza os passos de deploy em um único lugar
    (git pull do projeto e do tema, migrate, collectstatic, restart), evitando
    reimplementá-los na view. Em DEBUG o restart é pulado (SKIP_RESTART=1).

    Levanta ValidationError (via os_run) quando o script retorna código != 0.
    """
    script = os.path.join(settings.BASE_DIR, 'deploy.sh')
    env = os.environ.copy()
    if settings.DEBUG:
        env['SKIP_RESTART'] = '1'
    if extra_env:
        env.update(extra_env)
    return os_run(['bash', script], cwd=settings.BASE_DIR, env=env)


@staff_member_required
def system_update(request):
    log = ''
    try:
        log = _run_deploy_script().replace('\n', '<br/>')
        messages.success(request, 'Update realizado com sucesso')
    except Exception as e:
        log += f'{e}'.replace('\n', '<br/>')
        messages.error(request, 'Erro durante o deploy. Verifique o log abaixo.')
    return render(request, 'deploy.html', {'result': log})


@staff_member_required
def execute_deploy_tema(request):
    if request.method == 'GET':
        result = ''
    else:
        # Reutiliza o mesmo script de deploy (fonte única de verdade dos passos).
        try:
            result = _run_deploy_script().replace('\n', '<br/>')
            messages.success(request, 'Deploy executado com sucesso!')
        except Exception as e:
            result = f'{e}'.replace('\n', '<br/>')
            messages.error(request, 'Ocorreu um erro ao executar o deploy.')

    return render(request, 'deploy.html', {'result': result})
