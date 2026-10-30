# Instalação

## 0. Pré-requisitos

	sudo apt install libmysqlclient-dev python3-venv python3-pip gettext python-is-python3 libjpeg-dev zlib1g-dev  libpangocairo-1.0-0 libpangoft2-1.0-0 libcairo2 libffi-dev libjpeg-dev libxml2 libgdk-pixbuf2.0-0 libxslt1.1


## 1. Criar virtualenv

	virtualenv odorico

Outra opção é utilizar: mkvirtualenv odorico -p python3

## 2. Ativar virtualenv

	cd odorico
	source bin/activate
	mkdir logs

## 3. Clonar o repositório
	git clone git@github.com:josircg/odorico.git odorico-git

## 4. Entrar no repositório
	cd odorico

## 5. Instalar as libs

	pip install -r requirements.txt

## 6. Preparar o Banco de Dados. A base default está em sqlite e é mais que suficiente para que você possa testar a ferramenta.

## 7. Copie o local.py de configs/local.py para a pasta onde se encontra o settings.py e altere os parâmetros necessários, como nome do site, domínio, secret_key, senha do banco de dados e senha do repositório de arquivos

## 8. Teste se a configuração do local.py está ok:

	python manage.py check
	python manage.py migrate
	python manage.py collectstatic
	python manage.py createcachetable
    python manage.py createpaths

## 9. Caso queira instalar o odorico em servidor externo, recomendamos que utilize o servidor NGINX e o supervisord

	* Copie o arquivo /configs/nginx.conf para /etc/nginx/sites-available
	* Copie supervisor.conf para a pasta /etc/supervisor/conf.d/
	* Nos 2 arquivos, altere os parâmetros necessários para configurar o seu servidor.
	* Instale também os pacotes específicos para produção: pip install -r req-prod.txt

# 10. Cria o superuser

	python manage.py createsuperuser

# 11. Para testar se o sistema está funcionando:

	python manage.py runserver

Para uma nova base de dados, importe as tabelas de apoio.

````
python manage.py loaddata configs/fixtures/paises.json
python manage.py loaddata configs/fixtures/qualis.json
python manage.py loaddata configs/fixtures/tipo_ocorrencia.json
python manage.py loaddata configs/fixtures/tipoprocessamento.json
python manage.py loaddata configs/fixtures/area_impacto.json
````

Caso você já tenha uma base de dados populada com o Qualis/Periódicos, é importante limpar a base atual através do script abaixo:

````
from nucleo.models import *
ProducaoAutor.objects.all().delete()
Producao.objects.all().delete()
PesquisadorFomento.objects.all().delete()
Orientacao.objects.all().delete()
Matricula.objects.all().delete()
PesquisadorProjeto.objects.all().delete()
PesquisadorFormacao.objects.all().delete()
ProjetoPesquisa.objects.all().delete()
ProfessorLinha.objects.all().delete()
Professor.objects.all().delete()
Aluno.objects.all().delete()
PesquisadorNomeCitacao.objects.all().delete()
PesquisadorPrograma.objects.all().delete()
Pesquisador.objects.all().delete()
Curso.objects.all().delete()
LinhaPesquisa.objects.all().delete()
Programa.objects.all().delete()

from django.contrib.admin.models import LogEntry
LogEntry.objects.all().delete()

from utils.models import EmailAgendado
EmailAgendado.objects.all().delete()
````
