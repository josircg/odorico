from django.core.management.base import BaseCommand
from django.apps import apps
from utils.stdlib import nvl
import csv
from datetime import date

from nucleo.models import Aluno, Matricula, Curso, Pesquisador, Professor, Orientacao
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType

headers = [
    {'filename': 'professores.csv', 'app': 'nucleo', 'modelo': 'Professor', 'fields': ['nome', 'email', 'situacao']},
    {'filename': 'alunos.csv', 'app': 'nucleo', 'modelo': 'Aluno',
        'fields': ['nome', 'ano', 'id_lattes', 'situacao', 'status', 'email']},
]


def find_header(filename):
    for header in headers:
        if header['filename'] == filename:
            return header


class Command(BaseCommand):
    label = 'Importação CSV'

    @staticmethod
    def import_aluno(filename):
        loguser = User.objects.get_or_create(username='sys')[0]
        type_id = ContentType.objects.get(model='aluno').id
        pesquisador_id = ContentType.objects.get(model='pesquisador').id
        with open('data/'+filename, mode='r', encoding='utf-8') as csv_file:
            reader = csv.DictReader(csv_file, delimiter=',', quotechar='"')
            line_count = 0
            tot_incluidas = 0
            matriculas_alteradas = 0
            for row in reader:
                line_count += 1
                permite_inclusao = True
                if 'Ano' in row:
                    rotina = 'Importação Inicial'
                elif 'DRE' in row:
                    rotina = 'Importação DRE'
                else:
                    rotina = 'Importação Formulário'
                    permite_inclusao = False

                nome = row['Nome'].upper().strip()
                try:
                    aluno = Aluno.objects.get(nome=nome)
                    flag = CHANGE
                except Aluno.DoesNotExist:
                    if not permite_inclusao:
                        print('Aluno não encontrado: %s' % nome)
                        continue
                    aluno = Aluno()
                    aluno.nome = nome
                    aluno.save()
                    flag = ADDITION
                    LogEntry.objects.log_action(
                        user_id=loguser.id,
                        content_type_id=type_id,
                        object_id=aluno.pk,
                        object_repr=u"%s" % aluno,
                        action_flag=flag,
                        change_message=rotina
                    )
                    LogEntry.objects.log_action(
                        user_id=loguser.id,
                        content_type_id=pesquisador_id,
                        object_id=aluno.pk,
                        object_repr=u"%s" % aluno,
                        action_flag=flag,
                        change_message=rotina
                    )

                if 'Curso' in row:
                    curso_sigla = 'ME' if row['Curso'] == 'M' else 'DO'
                    curso = Curso.objects.get(nivel=curso_sigla)

                if 'Email' in row and row['Email']:
                    aluno.email = nvl(aluno.email, row['Email'])
                    aluno.save()

                if 'ID Lattes' in row:
                    aluno.id_lattes = nvl(aluno.id_lattes, row['ID Lattes'])
                    aluno.save()
                    try:
                        matricula = Matricula.objects.get(pesquisador=aluno, curso=curso)
                        if row['Ano'] != str(matricula.ingresso):
                            matricula.ingresso = row['Ano']
                            matriculas_alteradas += 1
                            matricula.save()
                        nova_matricula = False
                    except Matricula.MultipleObjectsReturned:
                        print('Matrícula duplicada! %s' % aluno.nome)
                    except Matricula.DoesNotExist:
                        nova_matricula = True
                        matricula = Matricula()
                        matricula.pesquisador = aluno
                        matricula.curso = curso
                        matricula.ingresso = row['Ano']
                        tot_incluidas += 1
                        # Se a situação for T, então a pessoa concluiu o curso
                        status = row['Situação']
                        if status == 'T':
                            aluno.situacao = 'M' if (status == 'M' and aluno.situacao != 'D') else 'D'
                            matricula.status = 'C'
                        else:
                            matricula.status = 'A' if status == 'M' else status
                            # Alterar a titulacao para Graduação caso não tenha uma titulação superior
                            aluno.situacao = 'G' if curso_sigla == 'ME' and aluno.situacao != 'M' else 'M'
                        aluno.save()
                        matricula.save()
                        LogEntry.objects.log_action(
                            user_id=loguser.id,
                            content_type_id=type_id,
                            object_id=aluno.pk,
                            object_repr=u"%s" % matricula,
                            action_flag=ADDITION if nova_matricula else CHANGE,
                            change_message=u"Matricula via %s" % rotina
                        )

                if 'CPF' in row:
                    aluno.CPF = row['CPF'].rjust(11,'0')
                    aluno.save()

                if 'DRE' in row:
                    aluno.id_funcional = row['DRE']
                    if not aluno.situacao and curso_sigla == 'DO':
                        aluno.situacao = 'M'
                    aluno.save()
                    try:
                        matricula = Matricula.objects.get(pesquisador=aluno, curso=curso)
                        nova_matricula = False
                    except Matricula.MultipleObjectsReturned:
                        print('Duplicidade na matrícula do aluno %s' % aluno.nome)
                        continue
                    except Matricula.DoesNotExist:
                        nova_matricula = True
                        matricula = Matricula()
                        matricula.pesquisador = aluno
                        matricula.curso = curso
                        matricula.ingresso = 2019
                        matricula.save()
                        tot_incluidas += 1
                        LogEntry.objects.log_action(
                            user_id=loguser.id,
                            content_type_id=type_id,
                            object_id=aluno.pk,
                            object_repr=u"%s" % matricula,
                            action_flag=ADDITION,
                            change_message=rotina
                        )

                    if row['Situação'][0] == 'C' and matricula.status != 'C':  # Concluída
                        matricula.status = 'C'
                        matricula.save()

                    if row['Situação'] == 'Abandono':
                        matricula.status = 'B'
                        matricula.save()

                matricula = None
                if 'mestrado' in row:
                    if len(row['mestrado']) == 4:
                        ano = row['mestrado']
                        curso = Curso.objects.get(nivel='ME')
                        try:
                            matricula = Matricula.objects.get(pesquisador=aluno, curso=curso)
                        except Matricula.DoesNotExist:
                            matricula = Matricula()
                            matricula.pesquisador = aluno
                            matricula.curso = curso
                            matricula.ingresso = int(ano) - 2
                            matricula.status = 'C'
                            matricula.save()
                            tot_incluidas += 1

                        if matricula.status == 'C':
                            dtconclusao = ano+'-12-31'
                            matricula.dtconclusao = date(*map(int, dtconclusao.split('-')))
                            matricula.save()
                        else:
                            print('Conclusão indefinida: %s (%s)' % (aluno.nome, matricula.status))

                    if len(row['doutorado']) == 4:
                        ano = row['doutorado']
                        curso = Curso.objects.get(nivel='DO')
                        try:
                            matricula = Matricula.objects.get(pesquisador=aluno, curso=curso)
                        except Matricula.DoesNotExist:
                            matricula = Matricula()
                            matricula.pesquisador = aluno
                            matricula.curso = curso
                            matricula.ingresso = int(ano) - 4
                            matricula.status = 'C'
                            matricula.save()
                            tot_incluidas += 1

                        if matricula.status == 'C':
                            dtconclusao = ano+'-12-31'
                            matricula.dtconclusao = date(*map(int, dtconclusao.split('-')))
                        matricula.save()

                    if row['orientador']:
                        try:
                            professor = Professor.objects.get(nome=row['orientador'].upper().strip())
                            orientacao, novo = Orientacao.objects.get_or_create(orientador=professor, aluno=aluno,
                                                                                coorientacao=False)
                            if matricula and matricula.status == 'C':
                                orientacao.status = 'I'
                                orientacao.save()
                        except Professor.DoesNotExist:
                            print('Professor %s não encontrado' % row['orientador'].upper())

            print('Linhas: %d' % line_count)
            print('Matriculas incluidas: %d' % tot_incluidas)
            print('Matriculas alteradas: %d' % matriculas_alteradas)

    def add_arguments(self, parser):
        parser.add_argument('tabela', type=str, help='Nome da tabela em formato CSV')

    def handle(self, *args, **options):
        file_name = options['tabela']
        if file_name.find('aluno') >= 0:
            self.import_aluno(file_name)
            return

        classe = find_header(file_name)
        if not classe:
            raise Exception('Classe %s não encontrada' % file_name)
        modelo = apps.get_model(classe['app'], classe['modelo'])
        tot_reg = 0
        with open('data/'+file_name, encoding='utf-8') as csv_file:
            reader = csv.reader(csv_file, delimiter=',', quotechar='"')
            reader.__next__()  # skip header
            header = classe['fields']
            for row in reader:
                _object_dict = {key: value for key, value in zip(header, row)}
                modelo.objects.create(**_object_dict)
                tot_reg += 1
        print('Registros importados: %d' % tot_reg)
