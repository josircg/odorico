from django.core.management.base import BaseCommand

from nucleo.models import TipoNotificacao, TipoOcorrencia

NOTIFICACOES = [
    {
        'descricao': 'Edital - CPF Duplicado',
        'texto': (
            "Olá {inscricao.nome},\n\n"
            "Identificamos que já existe uma inscrição sua para o edital {edital.descricao}.\n"
            "Reenviamos este e-mail para que você consiga acessá-la e fazer ajustes se necessário.\n\n"
            "Se tiver dificuldades, entre em contato com a secretaria.\n\n"
            "Atenciosamente,\nEquipe Enacin"
        ),
    },
    {
        'descricao': 'Edital - Confirmação de Inscrição',
        'texto': (
            "Sua inscrição para o edital {edital.descricao} está confirmada.\n"
            "Seu número de inscrição é {inscricao.id}.\n\n"
            "Atenciosamente,\nEquipe"
        ),
    },
]


class Command(BaseCommand):
    label = 'Cria TipoOcorrencia e TipoNotificacao para o app editais'

    def handle(self, *args, **options):
        for item in NOTIFICACOES:
            ocorrencia, created = TipoOcorrencia.objects.get_or_create(
                descricao=item['descricao'],
                defaults={'status': TipoOcorrencia.Status.ATIVO}
            )
            TipoNotificacao.objects.get_or_create(
                tipo_ocorrencia=ocorrencia,
                destinatario=TipoNotificacao.Fluxo.CRIACAO,
                defaults={'texto': item['texto']}
            )
            status = 'criado' if created else 'já existia'
            self.stdout.write(f"{item['descricao']}: {status}")
