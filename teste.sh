# Rotina de testes unitários de funções do sistema
# Não existe ainda um teste integrado para a base de dados
python manage.py test --testrunner=tests.test_apps.NoDbTestRunner
