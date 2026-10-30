import re

from django.forms import ValidationError, CharField

from .validators import BRPostalCodeValidator, BRCPFValidator, BRCNPJValidator
from .widgets import CPFInput

process_digits_re = re.compile(
    r'^(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})$'
)


class BRZipCodeField(CharField):
    """
    A form field that validates input as a Brazilian zip code, with the format 00000-000.

    .. versionchanged:: 2.2
        Use BRPostalCodeValidator to centralize validation logic and share with equivalent model field.
        More details at: https://github.com/django/django-localflavor/issues/334
    """

    def __init__(self, max_length=9, min_length=8, **kwargs):
        super().__init__(max_length=max_length, min_length=min_length, **kwargs)
        self.validators.append(BRPostalCodeValidator())


class BRCPFField(CharField):
    """
    A form field that validates a CPF number or a CPF string.

    A CPF number is compounded by XXX.XXX.XXX-VD. The two last digits are check digits.

    More information:
    http://en.wikipedia.org/wiki/Cadastro_de_Pessoas_F%C3%ADsicas

    .. versionchanged:: 2.2
        Use BRCPFValidator to centralize validation logic and share with equivalent model field.
        More details at: https://github.com/django/django-localflavor/issues/334
    """

    default_error_messages = {
        'invalid': 'Digite um CPF válido.',
        'max_digits': 'Este campo requer no máximo 11 dígitos ou 14 caracteres.',
    }

    def __init__(self, max_length=14, min_length=11, **kwargs):
        kwargs['widget'] = CPFInput
        super().__init__(max_length=max_length, min_length=min_length, **kwargs)
        self.validators.append(BRCPFValidator())

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return None
        return ''.join(re.findall(r'\d', value))


class BRCNPJField(CharField):
    """
    A form field that validates input as `Brazilian CNPJ`_.

    Input can either be of the format XX.XXX.XXX/XXXX-XX or be a group of 14
    digits.

    If you want to use the long format only, you can specify:
        brcnpj_field = BRCNPJField(min_length=16)

    If you want to use the short format, you can specify:
        brcnpj_field = BRCNPJField(max_length=14)

    Otherwise both formats will be valid.

    .. _Brazilian CNPJ: http://en.wikipedia.org/wiki/National_identification_number#Brazil
    """

    default_error_messages = {
        'invalid': 'Digite um CNPJ válido.',
        'max_digits': 'Este campo requer pelo menos 14 dígitos.',
    }

    def __init__(self, min_length=14, max_length=18, **kwargs):
        super().__init__(max_length=max_length, min_length=min_length, **kwargs)
        self.validators.append(BRCNPJValidator())


def mod_97_base10(value):
    return 98 - ((value * 100 % 97) % 97)


class BRProcessoField(CharField):
    """
    A form field that validates a Legal Process(Processo) number or a Legal Process string.

    A Processo number is compounded by NNNNNNN-DD.AAAA.J.TR.OOOO. The two DD digits are check digits.
    More information:
    http://www.cnj.jus.br/busca-atos-adm?documento=2748
    """

    default_error_messages = {'invalid': 'Número de Processo inválido'}

    def __init__(self, max_length=25, min_length=20, **kwargs):
        super().__init__(max_length=max_length, min_length=min_length, **kwargs)

    def clean(self, value):
        """Value can be either a string in the format NNNNNNN-DD.AAAA.J.TR.OOOO or an 20-digit number."""
        value = super().clean(value)
        if value in self.empty_values:
            return value

        orig_value = value[:]
        if not value.isdigit():
            process_number = process_digits_re.search(value)
            if process_number:
                value = ''.join(process_number.groups())
            else:
                raise ValidationError(self.error_messages['invalid'], code='invalid')

        orig_dv = value[7:9]

        value_without_digits = int(value[0:7] + value[9:])

        if str(mod_97_base10(value_without_digits)).zfill(2) != orig_dv:
            raise ValidationError(self.error_messages['invalid'], code='invalid')

        return orig_value
