from django.conf.urls import url
from .views import *

urlpatterns = [
    url(r'^importacao_periodicos/', importacao_periodicos,
        name='importacao_periodicos'),
    url(r'^periodicos/', periodicos, name='periodicos'),
    url(r'^dashboard-periodicos/', dashboard_periodicos,
        name='dashboard_periodicos'),
    url(r'^dash-filters/', dashboard_periodicos_filter,
        name='dashboard_periodicos_filter'),
    url(r'^dash-topicos/', dashboard_periodicos_topicos,
        name='dashboard_periodicos_topicos'),
    url(r'get_issn/(?P<issn>[\w\-]+)/', get_issn, name='get_issn'),
]
