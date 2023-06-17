from django.contrib.admin.views.main import PAGE_VAR
from django.template.defaulttags import register


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.simple_tag(takes_context=True)
def page_parameters(context, pagenum, page_var=None):
    """Retorna a url com o número página mantendo os outros parâmetros do request"""
    if page_var is None:
        page_var = PAGE_VAR

    params = context['request'].GET.copy()
    params[page_var] = pagenum

    return '?%s' % params.urlencode()
