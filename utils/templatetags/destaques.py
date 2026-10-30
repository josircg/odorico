import re
from html import unescape
from django.template.library import Library
from django.template.defaultfilters import stringfilter

register = Library()


@register.filter
def destacar_termo(texto_principal, termo_busca='', tag_inicio="<span class='destaque'>", tag_fim="</span>"):
    """
    Busca um termo (case-insensitive) e o envolve com tags de destaque.

    Args:
        texto_principal (str): A string onde a busca e o destaque serão realizados.
        termo_busca (str): A substring a ser destacada.
        tag_inicio (str): O marcador de início (ex: '<b>', '<span>').
        tag_fim (str): O marcador de fim (ex: '</b>', '</span>').

    Returns:
        str: O texto modificado com o termo de busca destacado.
    """

    if termo_busca == '':
        return texto_principal

    texto_principal = unescape(texto_principal)

    # Padrão de substituição: A string de substituição deve incluir a tag de início,
    # seguida do termo encontrado (\g<0>), e a tag de fim.
    substituicao = f"{tag_inicio}\\g<0>{tag_fim}"

    # 2. Usar re.sub() para substituir o termo em todo o texto:
    # re.sub(padrao, substituicao, texto, flags)
    # - termo_busca é o padrão.
    # - re.IGNORECASE garante que a busca seja case-insensitive.
    texto_destacado = re.sub(
        termo_busca,
        substituicao,
        texto_principal,
        flags=re.IGNORECASE
    )
    return texto_destacado
