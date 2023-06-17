from django.conf.urls import url
from .views import *

urlpatterns = [
    url(r'^importacao_periodicos/', importacao_periodicos, name='importacao_periodicos'),
    url(r'^importacao_area/', importacao_area, name='importacao_area'),
    url(r'periodicos/', periodicos, name='periodicos'),
    url(r'get_issn/(?P<issn>[\w\-]+)/', get_issn, name='get_issn'),
]
