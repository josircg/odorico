import re

from django import forms


class CPFInput(forms.TextInput):
    """
    Widget personalizado para campos de CPF com máscara JavaScript em tempo real.

    Este widget herda de `forms.TextInput` e injeta um evento 'oninput' no HTML
    para formatar automaticamente a entrada do usuário no padrão 000.000.000-00.

    A formatação ocorre da seguinte forma:
    1. Remove qualquer caractere não numérico.
    2. Aplica pontos após o 3º e 6º dígitos.
    3. Aplica um hífen antes dos últimos 2 dígitos.

    Atributos padrão incluídos:
        - class: 'form-control' (compatível com Bootstrap) e 'vTextField' (compatível com django admin).
        - placeholder: '000.000.000-00'.
        - oninput: Expressões regulares para formatação dinâmica.
    """

    def build_attrs(self, base_attrs, extra_attrs=None):
        defaults = {
            'class': 'form-control vTextField',
            'placeholder': '000.000.000-00',
            'oninput': (
                'this.value = this.value.replace(/\\D/g, "")'
                '.replace(/(\\d{3})(\\d)/, "$1.$2")'
                '.replace(/(\\d{3})(\\d)/, "$1.$2")'
                '.replace(/(\\d{3})(\\d{1,2})$/, "$1-$2");'
            )
        }

        attrs = super().build_attrs(base_attrs, extra_attrs)

        return defaults | attrs

    def format_value(self, value):
        """Prepara o valor vindo do banco/Python para o campo de texto."""
        if value is None:
            return None
        # Garante que temos apenas os dígitos para aplicar a máscara
        digits = ''.join(re.findall(r'\d', str(value)))

        if len(digits) == 11:
            return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'

        return value


class TelefoneInput(forms.TextInput):
    """
    Widget para campos de telefone com máscara JavaScript em tempo real.

    Formata a entrada do usuário no padrão (00) 00000-0000 ou (00) 0000-0000:
    1. Remove qualquer caractere não numérico.
    2. Aplica parênteses no DDD.
    3. Aplica hífen antes dos últimos 4 dígitos.

    Atributos padrão:
        - class: 'form-control telefone'
        - placeholder: '(00) 00000-0000'
        - oninput: expressões regulares para formatação dinâmica.
    """

    def build_attrs(self, base_attrs, extra_attrs=None):
        defaults = {
            'class': 'form-control telefone',
            'placeholder': '(00) 00000-0000',
            'oninput': (
                'this.value = this.value.replace(/\\D/g, "")'
                '.replace(/(\\d{2})(\\d)/, "($1) $2")'
                '.replace(/(\\d{5})(\\d{1,4})$/, "$1-$2");'
            )
        }

        attrs = super().build_attrs(base_attrs, extra_attrs)

        return defaults | attrs
