"""
Settings de teste: herda a configuração real (odorico.local, o módulo de
settings de entrada apontado pelo manage.py) e sobrescreve apenas o banco de
dados para SQLite em memória.

Herda de odorico.local porque é lá que ficam SECRET_KEY e as configurações
específicas do ambiente; odorico.settings é apenas a base importada pelo local.

Permite rodar a suíte sem depender do MySQL nem de permissão para criar o banco
de teste (test_ppgci_*), de forma rápida, isolada e portável entre máquinas.

Uso:
    "$WORKON_HOME/odorico310/bin/python" manage.py test tests.test_painel_docente \
        --settings=tests.settings_test
"""
from odorico.local import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# local.py roda com DEBUG=True e ativa o Django Debug Toolbar. Em testes, isso
# faz os templates referenciarem o namespace 'djdt', que não está registrado,
# quebrando a renderização. Desliga DEBUG e remove o toolbar do ambiente de teste.
DEBUG = False

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']  # noqa: F405
MIDDLEWARE = [mw for mw in MIDDLEWARE if 'debug_toolbar' not in mw]  # noqa: F405

# Hash rápido e sem dependências externas para acelerar a criação de usuários nos testes.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


class _DisableMigrations:
    """
    Desabilita todas as migrações nos testes: o schema é criado diretamente a
    partir dos modelos (create_all), sem executar data migrations antigas que
    assumem registros pré-existentes (ex.: qualis/0028 busca Schema 'CAPES-AA').

    Isso torna a suíte independente do histórico de migrações e de um banco
    pré-populado, sem alterar as migrações de produção.
    """
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _DisableMigrations()
