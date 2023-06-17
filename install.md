# Instalação

1. Criar virtualenv
> virtualenv odorico

Outra opção é utilizar: mkvirtualenv odorico -p python3

2. Ativar virtualenv
```
cd odorico
source bin/activate
mkdir logs
```

3. Clonar o repositório
> git clone git@github.com:larhud/odorico.git

4. Entrar no repositório
> cd odorico

5. Instalar as libs
> pip install -r requirements.txt

6. Preparar o Banco de Dados. A base default está em sqlite e é mais que suficiente para que você possa testar a ferramenta.

7. Copie o local.py de configs/local.py para a pasta onde se encontra o settings.py e altere
os parâmetros necessários, como nome do site, domínio, secret_key, senha do banco de dados

8. Teste se a configuração do local.py está ok:
> python manage.py check
> python manage.py migrate
> python manage.py collectstatic

9. Caso queira instalar o odorico em servidor externo, recomendamos que utilize o servidor NGINX e o supervisord
* Copie o arquivo /configs/nginx.conf para /etc/nginx/sites-available
* Copie supervisor.conf para a pasta /etc/supervisor/conf.d/
* Nos 2 arquivos, altere os parâmetros necessários para configurar o seu servidor.
* Instale também os pacotes específicos para produção: pip install -r req-prod.txt 

10. Cria o superuser
> python manage.py createsuperuser

11. Rode o servidor
> python manage.py runserver

Geralmente, para uma nova instalação, faz-se uma carga de uma base de dados já existente para que se possa aproveitar a base Qualis/Periódicos.
Nesse caso, é importante limpar a base atual através do script abaixo:

````
from nucleo.models import *
ProducaoAutor.objects.all().delete()
Producao.objects.all().delete()
PesquisadorFomento.objects.all().delete()
Orientacao.objects.all().delete()
Matricula.objects.all().delete()
PesquisadorProjeto.objects.all().delete()
PesquisadorTitulacao.objects.all().delete()
ProjetoPesquisa.objects.all().delete()
AlunoLinha.objects.all().delete()
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
