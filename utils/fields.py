import difflib
import re

import requests
from django.db.models import TextChoices
from django.db.models.fields import CharField
from django.utils.translation import gettext_lazy as _

from utils.stdlib import nvl
from . import forms
from .validators import BRCPFValidator, BRCNPJValidator, BRPostalCodeValidator


class DiaSemana(TextChoices):
    DOMINGO = '1', 'Domingo'
    SEGUNDA = 2, 'Segunda-feira'
    TERCA = 3, 'Terça-feira'
    QUARTA = 4, 'Quarta-feira'
    QUINTA = 5, 'Quinta-feira'
    SEXTA = 6, 'Sexta-feira'
    SABADO = 7, 'Sábado'


def get_orcid_name(_id):
    r = requests.get(f'https://pub.orcid.org/v3.0/expanded-search/?start=0&rows=10&q=orcid:{_id}',
                     headers={'User-Agent': 'Mozilla/5.0', 'accept': 'application/json'}, timeout=15)
    response = r.json()
    record = response.get('expanded-result')
    if record and len(record) > 0:
        return nvl(record[0]['given-names'], '') + ' ' + nvl(record[0]['family-names'], '')
    else:
        return


'''
def getORCID(code):
    try:
        response = requests.get(f'https://pub.orcid.org/v3.0/{code}/person', timeout=10)
        if response.status_code == 200:
            root = etree.fromstring(response.text.encode())
            name_tree = root.find('{http://www.orcid.org/ns/person}name')
            name = name_tree.find('{http://www.orcid.org/ns/personal-details}given-names')
            if name is not None:
                given_names = name.text
            else:
                given_names = ''
            name = name_tree.find('{http://www.orcid.org/ns/personal-details}family-name')
            if name is not None:
                return f'{given_names} {name.text}'
            else:
                return f'{given_names}'
        elif response.status_code == 404:
            return None
        else:
            return ''
    except:
        # TODO: Incluir um log para indicar o erro
        return ''
'''

orcid_re = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]{1}$')


def validate_orcid(orcid, researcher_name):
    if not orcid_re.match(orcid):
        return False, "ORCID Inválido"

    try:
        researcher_name_by_orcid = get_orcid_name(orcid)
    except:
        return True, 'Base ORCID fora do ar'
    if not researcher_name_by_orcid:
        return False, "ORCID não encontrado"

    if difflib.SequenceMatcher(None, researcher_name.lower(), researcher_name_by_orcid.lower()).ratio() < 0.5:
        return False, f"Nome incompatível com o nome existente no ORCID: {researcher_name_by_orcid}"

    return True, None


class BRCPFField(CharField):
    """
    A model field for the brazilian document named of CPF (Cadastro de Pessoa Física)

    Forms represent it as a :class:`~localflavor.br.forms.BRCPFField` field.

    .. versionadded:: 2.2
    """

    description = _("CPF Document")

    default_error_messages = {
        'invalid': _("Invalid CPF number."),
        'max_digits': _("This field requires at most 11 digits or 14 characters."),
    }

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 14
        super().__init__(*args, **kwargs)
        self.validators.append(BRCPFValidator())

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.BRCPFField}
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return value
        return ''.join(re.findall(r'\d', value))  # Remove tudo que não for dígito antes de salvar

    def contribute_to_class(self, cls, name, private_only=False):
        """
        Adiciona a função get_NOME_DO_CAMPO_display ao modelo automaticamente.
        """
        super().contribute_to_class(cls, name, private_only)

        method_name = f'get_{name}_display'

        def get_display(instance):
            value = getattr(instance, name)
            if not value:
                return ''

            digits = ''.join(re.findall(r'\d', str(value)))
            if len(digits) == 11:
                return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
            return value

        if not hasattr(cls, method_name):
            setattr(cls, method_name, get_display)


class BRCNPJField(CharField):
    """
    A model field for the brazilian document named of CNPJ (Cadastro Nacional de Pessoa Jurídica)

    Forms represent it as a :class:`~localflavor.br.forms.BRCNPJField` field.

    .. versionadded:: 2.2
    """

    description = _("CNPJ Document")

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 18
        super().__init__(*args, **kwargs)
        self.validators.append(BRCNPJValidator())

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.BRCNPJField}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class BRPostalCodeField(CharField):
    """
    A model field for the brazilian zip code

    Forms represent it as a :class:`~localflavor.br.forms.BRZipCOdeField` field.

    .. versionadded:: 2.2
    """

    description = _("Postal Code")

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 9
        super().__init__(*args, **kwargs)
        self.validators.append(BRPostalCodeValidator())

    def formfield(self, **kwargs):
        defaults = {'form_class': forms.BRZipCodeField}
        defaults.update(kwargs)
        return super().formfield(**defaults)
