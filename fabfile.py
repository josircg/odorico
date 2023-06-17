# Precisa digitar a chave privada do git em producao #
# coding: utf-8
import socket

from fabric import task, Connection
from io import BytesIO
from datetime import datetime


@task
def deploy_ppgci(context):
    connection = Connection('webapp@odorico.irdx.com.br')
    with connection.cd('/var/webapp/odorico35/odorico/'):
        connection.run('git pull')
        connection.run('../bin/python manage.py migrate')
        connection.run('../bin/python manage.py collectstatic --noinput')
        connection.run('supervisorctl restart odorico')
        print('Atualização efetuada')

@task
def deploy_iesp(context):
    connection = Connection('webapp@iesp.irdx.com.br')
    # Está utilizando o branch hml
    with connection.cd('/var/webapp/odorico/odorico/'):
        connection.run('git pull')
        connection.run('../bin/python manage.py migrate')
        connection.run('../bin/python manage.py collectstatic --noinput')
        connection.run('supervisorctl restart odorico')
        print('Atualização efetuada')

@task
def deploy_teste(context):
    connection = Connection('webapp@teste-iesp.irdx.com.br')
    with connection.cd('/var/webapp/odorico-django-3.2.x/odorico/'):
        connection.run('git pull')
        connection.run('../bin/python manage.py migrate')
        connection.run('../bin/python manage.py collectstatic --noinput')
        connection.run('supervisorctl restart odorico')
        print('Atualização efetuada')


@task
def connect(context):
    server = Connection('webapp@iesp.irdx.com.br')
    with server.cd('/var/webapp/'):
        result = server.run('ls', hide=True)
    msg = "Ran {0.command!r} on {0.connection.host}, got stdout:\n{0.stdout}"
    print(msg.format(result))


def read_var(connection, file_path, encoding='utf-8'):
    io_obj = BytesIO()
    connection.get(file_path, io_obj)
    return io_obj.getvalue().decode(encoding).strip()
    # except socket.gaierror:
    #    print(f'Password file {file_path} not found')


def backup(connection, path, database_name):
    with connection.cd(path):
        senha = read_var(connection, path+'mysql.pwd')
        if not senha:
            exit(-1)
        path += 'odorico/media/'
        filename = path + database_name + '%s.gz' % datetime.strftime(datetime.now(),'%Y%m%d')
        connection.run('mysqldump -u odorico -p"%s" %s --no-tablespaces | gzip > %s' % (senha, database_name, filename))
        print(filename)
        connection.get(filename)
        # connection.run('rm %s' % filename)


@task
def backup_teste(context):
    backup(Connection('webapp@teste-iesp.irdx.com.br'), '/var/webapp/odorico-django-3.2.x/odorico/', 'odorico_teste')

@task
def backup_ppgci(context):
    backup(Connection('webapp@odorico.irdx.com.br'), '/var/webapp/odorico32/', 'odorico')

@task
def backup_iesp(context):
    backup(Connection('webapp@iesp.irdx.com.br'), '/var/webapp/odorico/', 'odorico')

